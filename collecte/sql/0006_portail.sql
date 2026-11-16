--@@
-- Portail web (P0.1).
-- 1. Le membre peut expliquer les alertes de son dépôt depuis la page du portail (colonne
--    commentaire_portail, ajoutée par l'ORM dans cette même migration). Modifiable tant que la
--    déclaration est en BROUILLON ; figée ensuite par le trigger gipame_declaration_regles.
GRANT UPDATE (commentaire_portail) ON collecte_declaration TO gipame_membre;

--@@
-- 2. Les comptes ne se suppriment jamais (on les désactive : is_active = false). Jusqu'ici la
--    table des comptes n'était pas couverte par le trigger d'interdiction de suppression.
DROP TRIGGER IF EXISTS trg_pas_de_suppression ON collecte_utilisateur;
CREATE TRIGGER trg_pas_de_suppression BEFORE DELETE ON collecte_utilisateur
  FOR EACH ROW EXECUTE FUNCTION gipame_interdit_suppression();

--@@
-- 3. Annuaire minimal des comptes pour la gestion et le bureau (nom affiché d'un demandeur, d'un
--    approbateur) : jamais le mot de passe ni les champs techniques. Lecture seule.
CREATE OR REPLACE VIEW collecte_v_profil_utilisateur AS
SELECT id, username, first_name, last_name, email, role_metier, membre_id, is_active
FROM collecte_utilisateur;
GRANT SELECT ON collecte_v_profil_utilisateur TO gipame_gestion, gipame_bureau, gipame_membre;
