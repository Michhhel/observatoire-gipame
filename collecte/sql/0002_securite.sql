--@@
-- ============================================================================
-- GIPAME - règles que l'ORM ne sait pas exprimer : rôles, triggers, sécurité par
-- ligne (RLS), vues, fonctions. Appliqué par la migration 0002 (blocs séparés par
-- une ligne "--@@"). Prérequis : PostgreSQL >= 15.
--
-- Modèle de confiance
--   * Le COMPTE PROPRIÉTAIRE (celui qui lance les migrations) contourne la RLS : il est
--     "sous scellés", jamais utilisé en exploitation, sa réactivation = accès exceptionnel.
--   * L'application se connecte avec gipame_app, qui n'a AUCUN privilège direct sur les
--     tables métier : à chaque requête, elle bascule (SET LOCAL ROLE) vers gipame_membre,
--     gipame_gestion ou gipame_bureau. Oubli de bascule = accès refusé (échec sûr).
--   * Les quantités individuelles ne sont lisibles que : par le membre (les siennes),
--     par le rôle de calcul (batch des agrégats) et par la fonction d'accès exceptionnel.
-- ============================================================================

--@@
-- 1. Rôles (sans connexion ; le DBA active la connexion de gipame_app avec un mot de passe)
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['gipame_membre','gipame_gestion','gipame_bureau','gipame_calcul','gipame_app','gipame_purge'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN', r);
    END IF;
  END LOOP;
  ALTER ROLE gipame_app NOINHERIT;
  GRANT gipame_membre, gipame_gestion, gipame_bureau, gipame_calcul TO gipame_app;
END $$;

--@@
-- 2. Contexte de session posé par l'application (SET LOCAL dans la transaction)
CREATE OR REPLACE FUNCTION gipame_membre_courant() RETURNS bigint
LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.membre_id', true), '')::bigint $$;

--@@
CREATE OR REPLACE FUNCTION gipame_utilisateur_courant() RETURNS bigint
LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.utilisateur_id', true), '')::bigint $$;

--@@
-- 3a. Colonnes immuables (codes publics, clés d'une déclaration)
CREATE OR REPLACE FUNCTION gipame_colonnes_immuables() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE c text;
BEGIN
  FOREACH c IN ARRAY TG_ARGV LOOP
    IF (to_jsonb(NEW) -> c) IS DISTINCT FROM (to_jsonb(OLD) -> c) THEN
      RAISE EXCEPTION 'La colonne % de % est immuable', c, TG_TABLE_NAME
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

--@@
-- 3b. Aucune suppression physique (sauf purge de conservation : rôle gipame_purge + drapeau)
CREATE OR REPLACE FUNCTION gipame_interdit_suppression() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF COALESCE(current_setting('gipame.purge', true), '') = 'on' AND pg_has_role(current_user, 'gipame_purge', 'member') THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'Suppression physique interdite sur % : utiliser un statut ou une date de fin', TG_TABLE_NAME
    USING ERRCODE = 'integrity_constraint_violation';
END $$;

--@@
-- 3c. Tables en ajout seulement (journaux, approbations, publications figées)
CREATE OR REPLACE FUNCTION gipame_ajout_seulement() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF COALESCE(current_setting('gipame.purge', true), '') = 'on' AND pg_has_role(current_user, 'gipame_purge', 'member') THEN
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
  END IF;
  RAISE EXCEPTION 'La table % est en ajout seulement (aucune modification ni suppression)', TG_TABLE_NAME
    USING ERRCODE = 'integrity_constraint_violation';
END $$;

--@@
-- 3d. Piste d'audit : ancien/nouvel état de chaque ligne modifiée, avec l'utilisateur
CREATE OR REPLACE FUNCTION gipame_audit() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_id text;
BEGIN
  v_id := CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ->> 'id' ELSE to_jsonb(NEW) ->> 'id' END;
  INSERT INTO collecte_journalmodification (table_nom, objet_id, operation, ancien, nouveau, utilisateur_id, role_db)
  VALUES (TG_TABLE_NAME, v_id, TG_OP,
          CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN to_jsonb(OLD) END,
          CASE WHEN TG_OP IN ('INSERT','UPDATE') THEN to_jsonb(NEW) END,
          gipame_utilisateur_courant(), current_setting('role'));
  RETURN NULL;
END $$;

--@@
-- 3e. Déclarations : naissance en brouillon, pas de mois futur, version suivante, transitions
--     autorisées, contrôles bloquants à la soumission, remplacement automatique de la version
--     précédente. Une déclaration soumise est figée.
CREATE OR REPLACE FUNCTION gipame_declaration_regles() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_max integer; v_nb integer; v_total bigint; v_prec bigint;
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.statut <> 'BROUILLON' THEN
      RAISE EXCEPTION 'Une déclaration naît en BROUILLON' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NEW.mois > date_trunc('month', current_date)::date THEN
      RAISE EXCEPTION 'Déclaration d''un mois futur interdite (%)', NEW.mois USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT COALESCE(max(version), 0) INTO v_max FROM collecte_declaration
      WHERE membre_id = NEW.membre_id AND mois = NEW.mois;
    IF NEW.version <> v_max + 1 THEN
      RAISE EXCEPTION 'Version attendue : % (reçu %)', v_max + 1, NEW.version USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;

  IF OLD.statut = NEW.statut THEN
    IF OLD.statut <> 'BROUILLON'
       AND (to_jsonb(NEW) - 'modifie_le') IS DISTINCT FROM (to_jsonb(OLD) - 'modifie_le') THEN
      RAISE EXCEPTION 'Déclaration figée (statut %)', OLD.statut USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
  END IF;

  IF OLD.statut = 'BROUILLON' AND NEW.statut = 'ANNULEE' THEN
    RETURN NEW;
  END IF;

  IF OLD.statut = 'SOUMISE' AND NEW.statut = 'REMPLACEE' AND pg_trigger_depth() > 1 THEN
    RETURN NEW;  -- uniquement déclenché par la soumission d'une correction
  END IF;

  IF OLD.statut = 'BROUILLON' AND NEW.statut = 'SOUMISE' THEN
    IF NOT NEW.attestation_complete THEN
      RAISE EXCEPTION 'Attestation de complétude requise' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT count(*), COALESCE(sum(quantite), 0) INTO v_nb, v_total
      FROM collecte_lignevente WHERE declaration_id = NEW.id;
    IF v_nb = 0 THEN
      RAISE EXCEPTION 'Déclaration sans aucune ligne' USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF v_total = 0 AND NOT NEW.aucune_vente_confirmee THEN
      RAISE EXCEPTION 'Toutes les quantités sont à zéro : confirmer « aucune vente ce mois-ci »'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    SELECT id INTO v_prec FROM collecte_declaration
      WHERE membre_id = NEW.membre_id AND mois = NEW.mois AND statut = 'SOUMISE';
    IF v_prec IS NOT NULL THEN
      IF btrim(NEW.motif_correction) = '' THEN
        RAISE EXCEPTION 'Motif de correction requis' USING ERRCODE = 'integrity_constraint_violation';
      END IF;
      UPDATE collecte_declaration SET statut = 'REMPLACEE' WHERE id = v_prec;
      NEW.precedente_id := v_prec;
    END IF;
    NEW.soumise_le := now();
    NEW.soumise_par_id := gipame_utilisateur_courant();
    RETURN NEW;
  END IF;

  RAISE EXCEPTION 'Transition de statut interdite : % -> %', OLD.statut, NEW.statut
    USING ERRCODE = 'integrity_constraint_violation';
END $$;

--@@
-- 3f. Lignes de vente : modifiables seulement tant que la déclaration est un brouillon ;
--     jamais sur un produit rejeté ou fusionné
CREATE OR REPLACE FUNCTION gipame_lignevente_regles() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_decl bigint; v_statut text; v_pstatut text;
BEGIN
  v_decl := CASE WHEN TG_OP = 'DELETE' THEN OLD.declaration_id ELSE NEW.declaration_id END;
  SELECT statut INTO v_statut FROM collecte_declaration WHERE id = v_decl;
  IF v_statut IS DISTINCT FROM 'BROUILLON'
     AND NOT (COALESCE(current_setting('gipame.purge', true), '') = 'on' AND pg_has_role(current_user, 'gipame_purge', 'member')) THEN
    RAISE EXCEPTION 'Les lignes d''une déclaration au statut % ne sont plus modifiables', v_statut
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF TG_OP <> 'DELETE' THEN
    SELECT statut INTO v_pstatut FROM collecte_produit WHERE id = NEW.produit_id;
    IF v_pstatut IN ('REJETE', 'FUSIONNE') THEN
      RAISE EXCEPTION 'Produit non déclarable (statut %)', v_pstatut USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END $$;

--@@
-- 3g. Produits : code automatique, une proposition exige une concession active sur la marque,
--     horodatage de la décision de la gestion
CREATE OR REPLACE FUNCTION gipame_produit_regles() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_marque bigint;
BEGIN
  IF TG_OP = 'INSERT' AND COALESCE(NEW.code, '') = '' THEN
    NEW.code := 'PRD-' || lpad(NEW.id::text, 6, '0');
  END IF;
  IF NEW.statut = 'PROPOSE' THEN
    SELECT marque_id INTO v_marque FROM collecte_modele WHERE id = NEW.modele_id;
    v_marque := COALESCE(v_marque, NEW.marque_proposee_id);
    IF v_marque IS NULL THEN
      RAISE EXCEPTION 'Une proposition doit indiquer un modèle existant ou une marque'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM collecte_concession c
      WHERE c.membre_id = NEW.propose_par_id AND c.marque_id = v_marque
        AND c.date_debut <= current_date AND (c.date_fin IS NULL OR c.date_fin >= current_date)
    ) THEN
      RAISE EXCEPTION 'Le membre n''a pas de concession active pour cette marque'
        USING ERRCODE = 'integrity_constraint_violation';
    END IF;
  END IF;
  IF TG_OP = 'UPDATE' AND OLD.statut = 'PROPOSE' AND NEW.statut <> 'PROPOSE' THEN
    NEW.decide_le := now();
    NEW.decide_par_id := gipame_utilisateur_courant();
  END IF;
  RETURN NEW;
END $$;

--@@
-- 3h. Classement : le segment doit appartenir à la segmentation indiquée
CREATE OR REPLACE FUNCTION gipame_classement_regles() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_seg bigint;
BEGIN
  SELECT c.segmentation_id INTO v_seg
    FROM collecte_segment s JOIN collecte_categorie c ON c.id = s.categorie_id WHERE s.id = NEW.segment_id;
  IF v_seg IS DISTINCT FROM NEW.segmentation_id THEN
    RAISE EXCEPTION 'Le segment n''appartient pas à cette segmentation' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END $$;

--@@
-- 3i. Approbations d'accès exceptionnel : pas d'usurpation, pas d'auto-approbation, le poste
--     doit être réellement tenu par l'approbateur ; horodatage par le serveur
CREATE OR REPLACE FUNCTION gipame_approbation_regles() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_dem bigint;
BEGIN
  IF NEW.approbateur_id IS DISTINCT FROM gipame_utilisateur_courant() THEN
    RAISE EXCEPTION 'Approbation au nom d''un autre utilisateur interdite' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  SELECT demandeur_id INTO v_dem FROM collecte_demandeaccesexceptionnel WHERE id = NEW.demande_id;
  IF v_dem = NEW.approbateur_id THEN
    RAISE EXCEPTION 'Le demandeur ne peut pas approuver sa propre demande' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM collecte_titulaireposte t
    WHERE t.poste_id = NEW.poste_id AND t.utilisateur_id = NEW.approbateur_id
      AND t.date_debut <= current_date AND (t.date_fin IS NULL OR t.date_fin >= current_date)
  ) THEN
    RAISE EXCEPTION 'L''utilisateur ne détient pas ce poste' USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  NEW.decide_le := now();
  RETURN NEW;
END $$;

--@@
-- 4. Pose des triggers
CREATE TRIGGER trg_immuable BEFORE UPDATE ON collecte_membre
  FOR EACH ROW EXECUTE FUNCTION gipame_colonnes_immuables('code');
CREATE TRIGGER trg_immuable BEFORE UPDATE ON collecte_marque
  FOR EACH ROW EXECUTE FUNCTION gipame_colonnes_immuables('code');
CREATE TRIGGER trg_immuable BEFORE UPDATE ON collecte_modele
  FOR EACH ROW EXECUTE FUNCTION gipame_colonnes_immuables('code');
CREATE TRIGGER trg_immuable BEFORE UPDATE ON collecte_produit
  FOR EACH ROW EXECUTE FUNCTION gipame_colonnes_immuables('code');
CREATE TRIGGER trg_immuable BEFORE UPDATE ON collecte_declaration
  FOR EACH ROW EXECUTE FUNCTION gipame_colonnes_immuables('membre_id', 'mois', 'version');
CREATE TRIGGER trg_immuable BEFORE UPDATE ON collecte_lignevente
  FOR EACH ROW EXECUTE FUNCTION gipame_colonnes_immuables('declaration_id', 'produit_id');
CREATE TRIGGER trg_declaration BEFORE INSERT OR UPDATE ON collecte_declaration
  FOR EACH ROW EXECUTE FUNCTION gipame_declaration_regles();
CREATE TRIGGER trg_lignevente BEFORE INSERT OR UPDATE OR DELETE ON collecte_lignevente
  FOR EACH ROW EXECUTE FUNCTION gipame_lignevente_regles();
CREATE TRIGGER trg_produit BEFORE INSERT OR UPDATE ON collecte_produit
  FOR EACH ROW EXECUTE FUNCTION gipame_produit_regles();
CREATE TRIGGER trg_classement BEFORE INSERT OR UPDATE ON collecte_classementproduit
  FOR EACH ROW EXECUTE FUNCTION gipame_classement_regles();
CREATE TRIGGER trg_approbation BEFORE INSERT ON collecte_approbationacces
  FOR EACH ROW EXECUTE FUNCTION gipame_approbation_regles();

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'collecte_membre','collecte_groupeeconomique','collecte_periodeadhesion','collecte_marque',
    'collecte_concession','collecte_modele','collecte_produit','collecte_classementproduit',
    'collecte_aliasproduit','collecte_produitmembre','collecte_segmentation','collecte_categorie',
    'collecte_segment','collecte_declaration','collecte_poste','collecte_titulaireposte',
    'collecte_demandeaccesexceptionnel','collecte_origine','collecte_energie','collecte_boite',
    'collecte_parametresysteme'] LOOP
    EXECUTE format('CREATE TRIGGER trg_pas_de_suppression BEFORE DELETE ON %I FOR EACH ROW EXECUTE FUNCTION gipame_interdit_suppression()', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY[
    'collecte_journalmodification','collecte_journalacces','collecte_approbationacces',
    'collecte_publication','collecte_celluleagregat'] LOOP
    EXECUTE format('CREATE TRIGGER trg_ajout_seulement BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION gipame_ajout_seulement()', t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY[
    'collecte_membre','collecte_groupeeconomique','collecte_periodeadhesion','collecte_marque',
    'collecte_concession','collecte_modele','collecte_produit','collecte_classementproduit',
    'collecte_aliasproduit','collecte_produitmembre','collecte_segmentation','collecte_categorie',
    'collecte_segment','collecte_declaration','collecte_titulaireposte','collecte_parametresysteme'] LOOP
    EXECUTE format('CREATE TRIGGER trg_audit AFTER INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION gipame_audit()', t);
  END LOOP;
END $$;
CREATE TRIGGER trg_audit AFTER UPDATE OR DELETE ON collecte_lignevente
  FOR EACH ROW EXECUTE FUNCTION gipame_audit();

--@@
-- 5. Sécurité par ligne (RLS). Le propriétaire de la table la contourne (compte sous scellés).
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'collecte_declaration','collecte_lignevente','collecte_produit','collecte_concession',
    'collecte_periodeadhesion','collecte_produitmembre','collecte_aliasproduit',
    'collecte_parametresysteme','collecte_demandeaccesexceptionnel','collecte_approbationacces',
    'collecte_journalmodification'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;

-- déclarations : le membre ne voit et n'écrit que les siennes
CREATE POLICY decl_membre_select ON collecte_declaration FOR SELECT TO gipame_membre
  USING (membre_id = gipame_membre_courant());
CREATE POLICY decl_membre_insert ON collecte_declaration FOR INSERT TO gipame_membre
  WITH CHECK (membre_id = gipame_membre_courant());
CREATE POLICY decl_membre_update ON collecte_declaration FOR UPDATE TO gipame_membre
  USING (membre_id = gipame_membre_courant()) WITH CHECK (membre_id = gipame_membre_courant());
CREATE POLICY decl_gestion_select ON collecte_declaration FOR SELECT TO gipame_gestion USING (true);
CREATE POLICY decl_calcul_select ON collecte_declaration FOR SELECT TO gipame_calcul USING (true);

-- lignes de vente : seulement celles de ses propres déclarations (la gestion n'a AUCUN droit)
CREATE POLICY lv_membre ON collecte_lignevente FOR ALL TO gipame_membre
  USING (EXISTS (SELECT 1 FROM collecte_declaration d WHERE d.id = declaration_id AND d.membre_id = gipame_membre_courant()))
  WITH CHECK (EXISTS (SELECT 1 FROM collecte_declaration d WHERE d.id = declaration_id AND d.membre_id = gipame_membre_courant()));
CREATE POLICY lv_calcul_select ON collecte_lignevente FOR SELECT TO gipame_calcul USING (true);

-- produits : une proposition n'est visible que de son auteur (et de la gestion) jusqu'à validation
CREATE POLICY prod_membre_select ON collecte_produit FOR SELECT TO gipame_membre
  USING (statut IN ('ACTIF','ARCHIVE') OR propose_par_id = gipame_membre_courant());
CREATE POLICY prod_membre_insert ON collecte_produit FOR INSERT TO gipame_membre
  WITH CHECK (statut = 'PROPOSE' AND propose_par_id = gipame_membre_courant());
CREATE POLICY prod_membre_update ON collecte_produit FOR UPDATE TO gipame_membre
  USING (statut = 'PROPOSE' AND propose_par_id = gipame_membre_courant())
  WITH CHECK (statut = 'PROPOSE' AND propose_par_id = gipame_membre_courant());
CREATE POLICY prod_gestion ON collecte_produit FOR ALL TO gipame_gestion USING (true) WITH CHECK (true);
CREATE POLICY prod_calcul_select ON collecte_produit FOR SELECT TO gipame_calcul USING (true);

-- concessions, périodes, alias, exceptions d'affichage
CREATE POLICY conc_membre_select ON collecte_concession FOR SELECT TO gipame_membre
  USING (membre_id = gipame_membre_courant());
CREATE POLICY conc_gestion ON collecte_concession FOR ALL TO gipame_gestion USING (true) WITH CHECK (true);
CREATE POLICY conc_calcul_select ON collecte_concession FOR SELECT TO gipame_calcul USING (true);

CREATE POLICY per_membre_select ON collecte_periodeadhesion FOR SELECT TO gipame_membre
  USING (membre_id = gipame_membre_courant());
CREATE POLICY per_gestion ON collecte_periodeadhesion FOR ALL TO gipame_gestion USING (true) WITH CHECK (true);
CREATE POLICY per_calcul_select ON collecte_periodeadhesion FOR SELECT TO gipame_calcul USING (true);

CREATE POLICY alias_membre_select ON collecte_aliasproduit FOR SELECT TO gipame_membre
  USING (membre_id = gipame_membre_courant() OR membre_id IS NULL);
CREATE POLICY alias_gestion ON collecte_aliasproduit FOR ALL TO gipame_gestion USING (true) WITH CHECK (true);
CREATE POLICY alias_calcul_select ON collecte_aliasproduit FOR SELECT TO gipame_calcul USING (true);

CREATE POLICY pm_membre ON collecte_produitmembre FOR ALL TO gipame_membre
  USING (membre_id = gipame_membre_courant()) WITH CHECK (membre_id = gipame_membre_courant());
CREATE POLICY pm_gestion ON collecte_produitmembre FOR ALL TO gipame_gestion USING (true) WITH CHECK (true);
CREATE POLICY pm_calcul_select ON collecte_produitmembre FOR SELECT TO gipame_calcul USING (true);

-- paramètres : la gestion ne modifie que la catégorie OPERATIONNEL (jamais les seuils de sécurité)
CREATE POLICY param_lecture ON collecte_parametresysteme FOR SELECT TO gipame_gestion, gipame_bureau, gipame_calcul
  USING (true);
CREATE POLICY param_maj_gestion ON collecte_parametresysteme FOR UPDATE TO gipame_gestion
  USING (categorie = 'OPERATIONNEL') WITH CHECK (categorie = 'OPERATIONNEL');

-- accès exceptionnel : le demandeur voit sa demande, le bureau voit tout et approuve
CREATE POLICY dem_gestion_select ON collecte_demandeaccesexceptionnel FOR SELECT TO gipame_gestion
  USING (demandeur_id = gipame_utilisateur_courant());
CREATE POLICY dem_gestion_insert ON collecte_demandeaccesexceptionnel FOR INSERT TO gipame_gestion
  WITH CHECK (demandeur_id = gipame_utilisateur_courant());
CREATE POLICY dem_bureau_select ON collecte_demandeaccesexceptionnel FOR SELECT TO gipame_bureau USING (true);
CREATE POLICY appr_bureau_select ON collecte_approbationacces FOR SELECT TO gipame_bureau USING (true);
CREATE POLICY appr_bureau_insert ON collecte_approbationacces FOR INSERT TO gipame_bureau
  WITH CHECK (approbateur_id = gipame_utilisateur_courant());
CREATE POLICY appr_gestion_select ON collecte_approbationacces FOR SELECT TO gipame_gestion
  USING (EXISTS (SELECT 1 FROM collecte_demandeaccesexceptionnel d
                 WHERE d.id = demande_id AND d.demandeur_id = gipame_utilisateur_courant()));

-- journal d'audit : les anciennes/nouvelles valeurs des lignes de vente contiennent des quantités
CREATE POLICY jm_gestion ON collecte_journalmodification FOR SELECT TO gipame_gestion
  USING (table_nom <> 'collecte_lignevente');

--@@
-- 6. Privilèges (principe du moindre droit ; aucun privilège pour gipame_app lui-même)
GRANT SELECT ON collecte_origine, collecte_energie, collecte_boite, collecte_marque, collecte_modele,
  collecte_segmentation, collecte_categorie, collecte_segment, collecte_classementproduit,
  collecte_membre, collecte_groupeeconomique TO gipame_membre, gipame_bureau, gipame_calcul;
GRANT SELECT, INSERT, UPDATE ON collecte_origine, collecte_energie, collecte_boite, collecte_marque,
  collecte_modele, collecte_segmentation, collecte_categorie, collecte_segment, collecte_classementproduit,
  collecte_membre, collecte_groupeeconomique, collecte_periodeadhesion, collecte_concession,
  collecte_aliasproduit, collecte_produitmembre, collecte_produit TO gipame_gestion;
GRANT SELECT ON collecte_declaration, collecte_poste, collecte_titulaireposte TO gipame_gestion;
GRANT SELECT ON collecte_poste, collecte_titulaireposte TO gipame_bureau, gipame_calcul;
GRANT SELECT ON collecte_parametresysteme TO gipame_gestion, gipame_bureau, gipame_calcul;
GRANT UPDATE (valeur) ON collecte_parametresysteme TO gipame_gestion;
GRANT SELECT, INSERT ON collecte_demandeaccesexceptionnel TO gipame_gestion;
GRANT SELECT ON collecte_demandeaccesexceptionnel TO gipame_bureau;
GRANT SELECT ON collecte_approbationacces TO gipame_gestion;
GRANT SELECT, INSERT ON collecte_approbationacces TO gipame_bureau;
GRANT SELECT ON collecte_journalmodification TO gipame_gestion;
GRANT SELECT ON collecte_journalacces TO gipame_gestion, gipame_bureau;

-- le membre : ses déclarations et lignes, ses propositions de produits, ses exceptions d'affichage
GRANT SELECT, INSERT ON collecte_declaration TO gipame_membre;
GRANT UPDATE (statut, attestation_complete, aucune_vente_confirmee, motif_correction,
              version_gabarit, empreinte_fichier, modifie_le) ON collecte_declaration TO gipame_membre;
GRANT SELECT, INSERT, UPDATE, DELETE ON collecte_lignevente TO gipame_membre;
GRANT SELECT, INSERT ON collecte_produit TO gipame_membre;
GRANT UPDATE (modele_id, finition, energie_id, boite_id, cylindree_cm3, puissance_fiscale_cv,
              charge_utile_kg, ptac_kg, nb_places, motricite, libelle_affiche, marque_proposee_id,
              modele_propose, segment_propose, note_proposition, modifie_le) ON collecte_produit TO gipame_membre;
GRANT SELECT ON collecte_concession, collecte_periodeadhesion, collecte_aliasproduit TO gipame_membre;
GRANT SELECT, INSERT, UPDATE ON collecte_produitmembre TO gipame_membre;

-- le calcul des agrégats : lecture des données individuelles, écriture des publications
GRANT SELECT ON collecte_declaration, collecte_lignevente, collecte_produit, collecte_concession,
  collecte_periodeadhesion, collecte_produitmembre, collecte_aliasproduit TO gipame_calcul;
GRANT SELECT, INSERT ON collecte_publication, collecte_celluleagregat TO gipame_calcul;
GRANT SELECT ON collecte_publication TO gipame_membre, gipame_bureau, gipame_gestion;
GRANT SELECT (id, publication_id, dimension, cle, total, supprime) ON collecte_celluleagregat
  TO gipame_membre, gipame_bureau;
GRANT SELECT ON collecte_celluleagregat TO gipame_gestion;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public
  TO gipame_membre, gipame_gestion, gipame_bureau, gipame_calcul;

--@@
-- 7. Gabarit mensuel d'un membre : lignes affichées = produits actifs des marques qu'il détient
--    (ou tous les produits actifs si le paramètre gabarit_toutes_lignes = 'oui'), moins les
--    produits masqués, plus ses propres propositions en attente.
CREATE OR REPLACE FUNCTION gipame_lignes_gabarit(p_mois date)
RETURNS TABLE (l_produit_id bigint, l_code varchar, l_libelle varchar, l_statut varchar)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_membre bigint := gipame_membre_courant(); v_tout boolean;
BEGIN
  IF v_membre IS NULL THEN RETURN; END IF;
  SELECT COALESCE((SELECT valeur FROM collecte_parametresysteme WHERE cle = 'gabarit_toutes_lignes'), 'non') = 'oui'
    INTO v_tout;
  RETURN QUERY
  SELECT p.id, p.code::varchar, p.libelle_affiche::varchar, p.statut::varchar
  FROM collecte_produit p
  LEFT JOIN collecte_modele mo ON mo.id = p.modele_id
  WHERE (
      p.statut = 'ACTIF'
      AND (v_tout OR EXISTS (
            SELECT 1 FROM collecte_concession c
            WHERE c.membre_id = v_membre AND c.marque_id = mo.marque_id
              AND c.date_debut <= ((date_trunc('month', p_mois) + interval '1 month')::date - 1)
              AND (c.date_fin IS NULL OR c.date_fin >= date_trunc('month', p_mois)::date)))
      AND NOT EXISTS (
            SELECT 1 FROM collecte_produitmembre pm
            WHERE pm.membre_id = v_membre AND pm.produit_id = p.id AND pm.etat = 'MASQUE')
    )
    OR (p.statut = 'PROPOSE' AND p.propose_par_id = v_membre)
  ORDER BY mo.marque_id, p.code;
END $$;

--@@
-- 8. Lecture exceptionnelle des données individuelles : accord d'au moins N postes distincts
--    (paramètre seuil_approbations_acces, modifiable seulement par le propriétaire), fenêtre
--    limitée à partir du N-ième accord, usage réservé au demandeur, chaque lecture journalisée.
CREATE OR REPLACE FUNCTION gipame_lecture_exceptionnelle(p_demande bigint)
RETURNS TABLE (r_membre_code varchar, r_mois date, r_produit_code varchar, r_quantite integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE d record; v_seuil integer; v_ok integer; v_accordee timestamptz; v_n integer;
BEGIN
  SELECT * INTO d FROM collecte_demandeaccesexceptionnel WHERE id = p_demande;
  IF NOT FOUND THEN RAISE EXCEPTION 'Demande inconnue'; END IF;
  IF d.demandeur_id IS DISTINCT FROM gipame_utilisateur_courant() THEN
    RAISE EXCEPTION 'Seul le demandeur peut utiliser cet accès';
  END IF;
  SELECT valeur::integer INTO v_seuil FROM collecte_parametresysteme WHERE cle = 'seuil_approbations_acces';
  v_seuil := COALESCE(v_seuil, 2);
  SELECT count(*) INTO v_ok FROM collecte_approbationacces WHERE demande_id = d.id AND decision = 'APPROUVEE';
  IF v_ok < v_seuil THEN
    RAISE EXCEPTION 'Accord insuffisant : % sur % requis', v_ok, v_seuil;
  END IF;
  SELECT a.decide_le INTO v_accordee FROM collecte_approbationacces a
    WHERE a.demande_id = d.id AND a.decision = 'APPROUVEE'
    ORDER BY a.decide_le OFFSET (v_seuil - 1) LIMIT 1;
  IF now() > v_accordee + make_interval(mins => d.duree_minutes) THEN
    RAISE EXCEPTION 'Accès expiré';
  END IF;
  SELECT count(*) INTO v_n
    FROM collecte_lignevente l
    JOIN collecte_declaration dc ON dc.id = l.declaration_id AND dc.statut = 'SOUMISE'
    WHERE (d.membre_cible_id IS NULL OR dc.membre_id = d.membre_cible_id)
      AND dc.mois BETWEEN d.mois_debut AND d.mois_fin;
  INSERT INTO collecte_journalacces (utilisateur_id, demande_id, action, details, nb_lignes)
  VALUES (d.demandeur_id, d.id, 'LECTURE_EXCEPTIONNELLE',
          jsonb_build_object('membre_cible_id', d.membre_cible_id, 'mois_debut', d.mois_debut, 'mois_fin', d.mois_fin),
          v_n);
  RETURN QUERY
    SELECT m.code::varchar, dc.mois, p.code::varchar, l.quantite::integer
    FROM collecte_lignevente l
    JOIN collecte_declaration dc ON dc.id = l.declaration_id AND dc.statut = 'SOUMISE'
    JOIN collecte_membre m ON m.id = dc.membre_id
    JOIN collecte_produit p ON p.id = l.produit_id
    WHERE (d.membre_cible_id IS NULL OR dc.membre_id = d.membre_cible_id)
      AND dc.mois BETWEEN d.mois_debut AND d.mois_fin
    ORDER BY m.code, dc.mois, p.code;
END $$;

--@@
REVOKE ALL ON FUNCTION gipame_lecture_exceptionnelle(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION gipame_lecture_exceptionnelle(bigint) TO gipame_gestion;
REVOKE ALL ON FUNCTION gipame_lignes_gabarit(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION gipame_lignes_gabarit(date) TO gipame_membre;

--@@
-- 9. Vue de suivi des dépôts (alertes de retard) : statut et dates seulement, jamais de quantités.
--    Le délai de grâce après la fin du mois est le paramètre jours_grace_depot.
CREATE OR REPLACE VIEW collecte_v_suivi_depots AS
WITH grace AS (
  SELECT COALESCE((SELECT valeur::integer FROM collecte_parametresysteme WHERE cle = 'jours_grace_depot'), 10) AS jours
), mois AS (
  SELECT generate_series(date_trunc('month', current_date) - interval '12 months',
                         date_trunc('month', current_date), interval '1 month')::date AS mois
)
SELECT m.id AS membre_id, m.code AS membre_code, mo.mois,
       d.statut AS statut_depot, d.version, d.soumise_le,
       ((mo.mois + interval '1 month')::date + g.jours) AS date_limite,
       (d.id IS NULL AND current_date > ((mo.mois + interval '1 month')::date + g.jours)) AS en_retard
FROM mois mo
CROSS JOIN grace g
JOIN collecte_periodeadhesion pa ON pa.declaration_obligatoire
     AND pa.date_debut <= ((mo.mois + interval '1 month')::date - 1)
     AND (pa.date_fin IS NULL OR pa.date_fin >= mo.mois)
JOIN collecte_membre m ON m.id = pa.membre_id AND m.famille = 'VEHICULES'
LEFT JOIN collecte_declaration d ON d.membre_id = m.id AND d.mois = mo.mois AND d.statut = 'SOUMISE';

--@@
-- 10. Produits sans vente depuis N mois (paramètre mois_inactivite_masquage) : candidats au
--     masquage. On ne supprime jamais : on masque (ProduitMembre) ou on archive (Produit).
CREATE OR REPLACE VIEW collecte_v_produits_sans_vente AS
WITH seuil AS (
  SELECT (date_trunc('month', current_date)
          - make_interval(months => COALESCE((SELECT valeur::integer FROM collecte_parametresysteme
                                              WHERE cle = 'mois_inactivite_masquage'), 12)))::date AS limite
), dernier AS (
  SELECT l.produit_id, max(d.mois) AS dernier_mois_vendu
  FROM collecte_lignevente l
  JOIN collecte_declaration d ON d.id = l.declaration_id AND d.statut = 'SOUMISE'
  WHERE l.quantite > 0 GROUP BY l.produit_id
)
SELECT p.id AS produit_id, p.code, p.libelle_affiche, dr.dernier_mois_vendu
FROM collecte_produit p
CROSS JOIN seuil s
LEFT JOIN dernier dr ON dr.produit_id = p.id
WHERE p.statut = 'ACTIF' AND (dr.dernier_mois_vendu IS NULL OR dr.dernier_mois_vendu < s.limite);

--@@
GRANT SELECT ON collecte_v_suivi_depots, collecte_v_produits_sans_vente TO gipame_gestion;
