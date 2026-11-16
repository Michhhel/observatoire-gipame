-- Rôles de l'Observatoire, à créer AVANT un pg_restore dans une instance PostgreSQL neuve (nouveau projet Neon,
-- poste d'analyse vierge). Les rôles appartiennent à l'instance, pas à la base : une sauvegarde ne les contient pas.
-- Identique au bloc 1 de collecte/sql/0002_securite.sql. Sans effet s'ils existent déjà.
-- Usage : psql "<adresse propriétaire>" -f scripts/creer_roles.sql
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
