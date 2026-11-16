--@@
-- Gestion des comptes depuis le portail (décision D21 révisée, 12/11/2026).
-- Le compte « administrateur du GIPAME » (rôle métier TECHNIQUE, rôle PostgreSQL gipame_gestion) n'a aucun
-- droit direct sur la table des comptes : il passe par ces fonctions SECURITY DEFINER qui vérifient
-- elles-mêmes qui appelle (TECHNIQUE actif) et journalisent chaque opération. La connexion propriétaire
-- (commande gerer_compte) peut les appeler aussi : elle n'est pas gipame_app, on ne lui impose pas le contexte.

CREATE OR REPLACE FUNCTION gipame_exiger_administrateur() RETURNS void
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_role text; v_actif boolean;
BEGIN
  -- connexion propriétaire de la base (commande gerer_compte, superutilisateur de développement) : pas de contexte exigé
  IF session_user = (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database())
     OR (SELECT rolsuper FROM pg_roles WHERE rolname = session_user) THEN RETURN; END IF;
  SELECT role_metier, is_active INTO v_role, v_actif FROM collecte_utilisateur WHERE id = gipame_utilisateur_courant();
  IF NOT FOUND OR NOT v_actif OR v_role <> 'TECHNIQUE' THEN
    RAISE EXCEPTION 'Réservé au compte administrateur de l''Observatoire';
  END IF;
END $$;

--@@
-- Création : mot de passe « inutilisable » (préfixe « ! », convention Django) ; la personne le choisit via le
-- lien d'activation. Renvoie l'identifiant et la valeur du mot de passe inutilisable (sert à signer le jeton).
CREATE OR REPLACE FUNCTION gipame_compte_creer(p_email text, p_prenom text, p_nom text, p_role text,
                                               p_membre_id bigint, p_poste_code text)
RETURNS TABLE (r_id bigint, r_mot_de_passe text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_email text := lower(trim(p_email)); v_id bigint; v_mdp text; v_poste bigint; v_debut date; v_fin date;
BEGIN
  PERFORM gipame_exiger_administrateur();
  IF v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' THEN RAISE EXCEPTION 'Adresse e-mail invalide'; END IF;
  IF p_role NOT IN ('MEMBRE', 'GESTION', 'BUREAU', 'TECHNIQUE') THEN RAISE EXCEPTION 'Rôle inconnu : %', p_role; END IF;
  IF p_role = 'MEMBRE' AND p_membre_id IS NULL THEN RAISE EXCEPTION 'Un compte MEMBRE doit être rattaché à une société'; END IF;
  IF p_role <> 'MEMBRE' AND p_membre_id IS NOT NULL THEN RAISE EXCEPTION 'Seul un compte MEMBRE est rattaché à une société'; END IF;
  IF p_poste_code IS NOT NULL AND p_role <> 'BUREAU' THEN RAISE EXCEPTION 'Seul un compte BUREAU tient un poste'; END IF;
  IF EXISTS (SELECT 1 FROM collecte_utilisateur WHERE username = v_email) THEN
    RAISE EXCEPTION 'Un compte existe déjà pour %', v_email;
  END IF;
  v_mdp := '!' || substr(md5(random()::text || clock_timestamp()::text) || md5(random()::text), 1, 40);
  INSERT INTO collecte_utilisateur (password, is_superuser, username, first_name, last_name, email, is_staff,
                                    is_active, date_joined, role_metier, membre_id)
  VALUES (v_mdp, false, v_email, trim(coalesce(p_prenom, '')), trim(coalesce(p_nom, '')), v_email, false,
          true, now(), p_role, p_membre_id)
  RETURNING id INTO v_id;
  IF p_poste_code IS NOT NULL THEN
    SELECT id INTO v_poste FROM collecte_poste WHERE code = p_poste_code;
    IF v_poste IS NULL THEN RAISE EXCEPTION 'Poste inconnu : %', p_poste_code; END IF;
    IF EXISTS (SELECT 1 FROM collecte_titulaireposte WHERE poste_id = v_poste AND date_fin IS NULL) THEN
      RAISE EXCEPTION 'Le poste % a déjà un titulaire : clore son mandat d''abord', p_poste_code;
    END IF;
    SELECT max(date_fin) INTO v_fin FROM collecte_titulaireposte WHERE poste_id = v_poste;
    v_debut := greatest(current_date, coalesce(v_fin + 1, current_date));
    INSERT INTO collecte_titulaireposte (poste_id, utilisateur_id, date_debut, date_fin, cree_le, modifie_le)
    VALUES (v_poste, v_id, v_debut, NULL, now(), now());
  END IF;
  INSERT INTO collecte_journalacces (utilisateur_id, action, details, nb_lignes)
  VALUES (v_id, 'COMPTE_CREE', jsonb_build_object('email', v_email, 'role', p_role, 'membre_id', p_membre_id,
          'poste', p_poste_code, 'par', gipame_utilisateur_courant()), 0);
  RETURN QUERY SELECT v_id, v_mdp;
END $$;

--@@
-- Activation / désactivation (jamais de suppression). La désactivation clôt les mandats au bureau.
CREATE OR REPLACE FUNCTION gipame_compte_etat(p_id bigint, p_actif boolean, p_motif text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_email text;
BEGIN
  PERFORM gipame_exiger_administrateur();
  IF NOT p_actif AND coalesce(trim(p_motif), '') = '' THEN RAISE EXCEPTION 'Un motif est obligatoire pour désactiver un compte'; END IF;
  IF p_id = gipame_utilisateur_courant() AND NOT p_actif THEN RAISE EXCEPTION 'Vous ne pouvez pas désactiver votre propre compte'; END IF;
  UPDATE collecte_utilisateur SET is_active = p_actif WHERE id = p_id RETURNING email INTO v_email;
  IF NOT FOUND THEN RAISE EXCEPTION 'Compte inconnu'; END IF;
  IF NOT p_actif THEN
    UPDATE collecte_titulaireposte SET date_fin = current_date, modifie_le = now()
    WHERE utilisateur_id = p_id AND date_fin IS NULL AND date_debut <= current_date;
  END IF;
  INSERT INTO collecte_journalacces (utilisateur_id, action, details, nb_lignes)
  VALUES (p_id, CASE WHEN p_actif THEN 'COMPTE_REACTIVE' ELSE 'COMPTE_DESACTIVE' END,
          jsonb_build_object('email', v_email, 'motif', p_motif, 'par', gipame_utilisateur_courant()), 0);
END $$;

--@@
-- Modification de l'identité (prénom, nom) et de l'adresse (= identifiant) d'un compte.
CREATE OR REPLACE FUNCTION gipame_compte_modifier(p_id bigint, p_email text, p_prenom text, p_nom text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_email text := lower(trim(p_email));
BEGIN
  PERFORM gipame_exiger_administrateur();
  IF v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' THEN RAISE EXCEPTION 'Adresse e-mail invalide'; END IF;
  IF EXISTS (SELECT 1 FROM collecte_utilisateur WHERE username = v_email AND id <> p_id) THEN
    RAISE EXCEPTION 'Un autre compte utilise déjà %', v_email;
  END IF;
  UPDATE collecte_utilisateur SET username = v_email, email = v_email, first_name = trim(coalesce(p_prenom, '')),
         last_name = trim(coalesce(p_nom, '')) WHERE id = p_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Compte inconnu'; END IF;
  INSERT INTO collecte_journalacces (utilisateur_id, action, details, nb_lignes)
  VALUES (p_id, 'COMPTE_MODIFIE', jsonb_build_object('email', v_email, 'par', gipame_utilisateur_courant()), 0);
END $$;

--@@
-- Éléments nécessaires pour (re)générer un lien d'activation : seulement tant que le compte n'a jamais
-- choisi de mot de passe (préfixe « ! »). Ensuite, la personne passe par « mot de passe oublié ».
CREATE OR REPLACE FUNCTION gipame_compte_pour_activation(p_id bigint)
RETURNS TABLE (r_email text, r_mot_de_passe text, r_derniere_connexion timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE u record;
BEGIN
  PERFORM gipame_exiger_administrateur();
  SELECT * INTO u FROM collecte_utilisateur WHERE id = p_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'Compte inconnu'; END IF;
  IF NOT u.is_active THEN RAISE EXCEPTION 'Compte désactivé : le réactiver d''abord'; END IF;
  IF left(u.password, 1) <> '!' THEN
    RAISE EXCEPTION 'Ce compte est déjà activé : la personne peut utiliser « Mot de passe oublié »';
  END IF;
  INSERT INTO collecte_journalacces (utilisateur_id, action, details, nb_lignes)
  VALUES (p_id, 'LIEN_ACTIVATION', jsonb_build_object('email', u.email, 'par', gipame_utilisateur_courant()), 0);
  RETURN QUERY SELECT u.email::text, u.password::text, u.last_login;
END $$;

--@@
REVOKE ALL ON FUNCTION gipame_exiger_administrateur() FROM PUBLIC;
REVOKE ALL ON FUNCTION gipame_compte_creer(text, text, text, text, bigint, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION gipame_compte_etat(bigint, boolean, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION gipame_compte_modifier(bigint, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION gipame_compte_pour_activation(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION gipame_compte_creer(text, text, text, text, bigint, text) TO gipame_gestion;
GRANT EXECUTE ON FUNCTION gipame_compte_etat(bigint, boolean, text) TO gipame_gestion;
GRANT EXECUTE ON FUNCTION gipame_compte_modifier(bigint, text, text, text) TO gipame_gestion;
GRANT EXECUTE ON FUNCTION gipame_compte_pour_activation(bigint) TO gipame_gestion;

--@@
-- L'annuaire indique désormais si le compte a été activé et la dernière connexion (jamais le mot de passe).
DROP VIEW IF EXISTS collecte_v_profil_utilisateur;
CREATE VIEW collecte_v_profil_utilisateur AS
SELECT id, username, first_name, last_name, email, role_metier, membre_id, is_active,
       (left(password, 1) <> '!') AS compte_active, last_login AS derniere_connexion, date_joined AS cree_le
FROM collecte_utilisateur;
GRANT SELECT ON collecte_v_profil_utilisateur TO gipame_gestion, gipame_bureau, gipame_membre;
