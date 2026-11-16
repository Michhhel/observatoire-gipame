#!/bin/bash
# Essai complet sur une base de démonstration, avec la connexion NON privilégiée gipame_app (aucun superutilisateur).
# Prérequis : scripts/dev_postgres.sh déjà lancé. ATTENTION : détruit et recrée la base "gipame".
set -e
su postgres -c "psql -q -c 'DROP DATABASE IF EXISTS gipame'"
su postgres -c "createdb -O gipame_dev gipame"
python manage.py migrate
python manage.py seed_demo
python manage.py appliquer_droits_techniques
python manage.py verifier_installation
su postgres -c "psql -q -c \"ALTER ROLE gipame_app LOGIN PASSWORD 'app'\""
GIPAME_DB_USER=gipame_app GIPAME_DB_PASSWORD=app python manage.py demo_cycle --sortie sortie_demo
python manage.py exemple_historique --annee 2024 --sortie sortie_demo/historique
python manage.py historique_analyser --fichier sortie_demo/historique/MTM_2024_fictif.xlsx --sortie sortie_demo/historique
python manage.py historique_charger --fichier sortie_demo/historique/MTM_2024_fictif.xlsx --rapprochement sortie_demo/historique/rapprochement_2024.xlsx --a-blanc
echo "Fichiers Excel à ouvrir : sortie_demo/"
