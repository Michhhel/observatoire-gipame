#!/bin/bash
# Prépare PostgreSQL pour le DÉVELOPPEMENT (Linux/Ubuntu, à lancer avec les droits root) :
#   - un compte propriétaire de développement (superutilisateur : PAS pour l'exploitation)
#   - une base "gipame"
# Les rôles gipame_* sont créés par la migration collecte.0002 (le compte qui migre doit pouvoir créer des rôles).
set -e
su postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='gipame_dev'\"" | grep -q 1 || \
  su postgres -c "psql -c \"CREATE ROLE gipame_dev SUPERUSER LOGIN PASSWORD 'dev'\""
su postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname='gipame'\"" | grep -q 1 || \
  su postgres -c "createdb -O gipame_dev gipame"
echo "OK : base 'gipame', compte 'gipame_dev' (mot de passe 'dev')."
echo "Ensuite : pip install -r requirements.txt && python manage.py migrate && python manage.py test collecte"
