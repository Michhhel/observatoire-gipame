#!/usr/bin/env bash
# Sauvegarde complète de la base (connexion PROPRIÉTAIRE) dans un fichier daté, format pg_dump « custom »
# (compressé, restaurable avec pg_restore). Usage : scripts/sauvegarde.sh [dossier]
# Variables : GIPAME_DB_NAME/USER/PASSWORD/HOST/PORT (comme l'application). Pour un hébergeur : GIPAME_DB_URL=postgres://…
set -euo pipefail
dossier="${1:-sauvegardes}"; mkdir -p "$dossier"
fichier="$dossier/gipame_$(date +%Y-%m-%d_%H%M).dump"
if [ -n "${GIPAME_DB_URL:-}" ]; then pg_dump --format=custom --no-owner --file="$fichier" "$GIPAME_DB_URL"
else PGPASSWORD="${GIPAME_DB_PASSWORD:-dev}" pg_dump --format=custom --no-owner --file="$fichier" \
  -h "${GIPAME_DB_HOST:-127.0.0.1}" -p "${GIPAME_DB_PORT:-5432}" -U "${GIPAME_DB_USER:-gipame_dev}" "${GIPAME_DB_NAME:-gipame}"; fi
echo "Sauvegarde écrite : $fichier ($(du -h "$fichier" | cut -f1))"
echo "Restauration locale : createdb gipame_local && pg_restore --no-owner -d gipame_local $fichier"
