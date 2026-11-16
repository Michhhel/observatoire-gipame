--@@
-- Rappels de dépôt (12/11/2026). La gestion n'a aucun droit sur la table des comptes : cette fonction lui
-- donne, pour un mois, les destinataires d'un rappel (comptes MEMBRE actifs et activés des membres attendus
-- qui n'ont pas soumis). Un membre attendu sans compte utilisable sort avec r_email NULL (à relancer par
-- téléphone). Aucune quantité n'est lue. Chaque appel est journalisé (visible du bureau).
CREATE OR REPLACE FUNCTION gipame_destinataires_rappel(p_mois date)
RETURNS TABLE (r_membre_id bigint, r_raison_sociale text, r_email text, r_prenom text, r_date_limite date)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE v_mois date := date_trunc('month', p_mois)::date; v_grace integer; v_n integer;
BEGIN
  SELECT COALESCE((SELECT valeur::integer FROM collecte_parametresysteme WHERE cle = 'jours_grace_depot'), 10) INTO v_grace;
  SELECT count(DISTINCT m.id) INTO v_n
    FROM collecte_membre m
    JOIN collecte_periodeadhesion pa ON pa.membre_id = m.id AND pa.declaration_obligatoire
         AND pa.date_debut <= ((v_mois + interval '1 month')::date - 1) AND (pa.date_fin IS NULL OR pa.date_fin >= v_mois)
    WHERE m.famille = 'VEHICULES'
      AND NOT EXISTS (SELECT 1 FROM collecte_declaration d WHERE d.membre_id = m.id AND d.mois = v_mois AND d.statut = 'SOUMISE');
  INSERT INTO collecte_journalacces (utilisateur_id, action, details, nb_lignes)
  VALUES (gipame_utilisateur_courant(), 'RAPPELS_PREPARES', jsonb_build_object('mois', v_mois), v_n);
  RETURN QUERY
  SELECT m.id, m.raison_sociale::text, u.email::text, u.first_name::text,
         ((v_mois + interval '1 month')::date + v_grace)
  FROM (SELECT DISTINCT m0.id, m0.raison_sociale FROM collecte_membre m0
        JOIN collecte_periodeadhesion pa ON pa.membre_id = m0.id AND pa.declaration_obligatoire
             AND pa.date_debut <= ((v_mois + interval '1 month')::date - 1) AND (pa.date_fin IS NULL OR pa.date_fin >= v_mois)
        WHERE m0.famille = 'VEHICULES'
          AND NOT EXISTS (SELECT 1 FROM collecte_declaration d WHERE d.membre_id = m0.id AND d.mois = v_mois AND d.statut = 'SOUMISE')) m
  LEFT JOIN collecte_utilisateur u ON u.membre_id = m.id AND u.role_metier = 'MEMBRE' AND u.is_active
       AND u.password NOT LIKE '!%' AND u.email <> ''
  ORDER BY m.raison_sociale, u.email;
END $$;

--@@
REVOKE ALL ON FUNCTION gipame_destinataires_rappel(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION gipame_destinataires_rappel(date) TO gipame_gestion;
