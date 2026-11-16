--@@
-- Fichiers Excel déposés : chaque membre ne voit que ses dépôts ; la gestion voit les métadonnées
-- (jamais le rapport, qui peut citer des quantités) ; tables en ajout seulement.
ALTER TABLE collecte_depotfichier ENABLE ROW LEVEL SECURITY;
CREATE POLICY depot_membre_select ON collecte_depotfichier FOR SELECT TO gipame_membre
  USING (membre_id = gipame_membre_courant());
CREATE POLICY depot_membre_insert ON collecte_depotfichier FOR INSERT TO gipame_membre
  WITH CHECK (membre_id = gipame_membre_courant() AND type_depot = 'DECLARATION');
CREATE POLICY depot_gestion_select ON collecte_depotfichier FOR SELECT TO gipame_gestion USING (true);
GRANT SELECT, INSERT ON collecte_depotfichier TO gipame_membre;
GRANT SELECT (id, membre_id, mois, type_depot, nom_fichier, taille_octets, empreinte_sha256, resultat,
              nb_erreurs, nb_alertes, declaration_id, depose_par_id, cree_le, modifie_le)
  ON collecte_depotfichier TO gipame_gestion;
CREATE TRIGGER trg_ajout_seulement BEFORE UPDATE OR DELETE ON collecte_depotfichier
  FOR EACH ROW EXECUTE FUNCTION gipame_ajout_seulement();
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public
  TO gipame_membre, gipame_gestion, gipame_bureau, gipame_calcul;

--@@
-- Paramètres lisibles par tous les rôles métier (liste blanche : jamais les seuils de sécurité)
CREATE OR REPLACE FUNCTION gipame_parametres_publics()
RETURNS TABLE (p_cle text, p_valeur text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp AS $$
  SELECT cle::text, valeur::text FROM collecte_parametresysteme
  WHERE cle IN ('jours_grace_depot', 'definition_vente', 'contact_gipame', 'import_variation_alerte_pct',
                'import_variation_min_unites', 'import_quantite_max', 'import_max_ajouts', 'import_taille_max_ko')
$$;

--@@
REVOKE ALL ON FUNCTION gipame_parametres_publics() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION gipame_parametres_publics()
  TO gipame_membre, gipame_gestion, gipame_bureau, gipame_calcul;
