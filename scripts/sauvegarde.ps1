# Sauvegarde complète de la base (connexion PROPRIÉTAIRE) — Windows PowerShell 5.1 ou 7.
# Nécessite pg_dump dans le PATH (livré avec PostgreSQL : C:\Program Files\PostgreSQL\16\bin).
# Usage : .\scripts\sauvegarde.ps1 [-Dossier sauvegardes]
# Base en ligne (Neon) : $env:GIPAME_DB_URL = "postgresql://neondb_owner:MOTDEPASSE@HOTE/neondb?sslmode=require"
# ATTENTION : le fichier produit contient TOUTES les données individuelles. Le garder sur un disque chiffré.
param([string]$Dossier = "sauvegardes")
function Valeur($nom, $defaut) { $v = [Environment]::GetEnvironmentVariable($nom); if ($v) { $v } else { $defaut } }
New-Item -ItemType Directory -Force -Path $Dossier | Out-Null
$fichier = Join-Path $Dossier ("gipame_" + (Get-Date -Format "yyyy-MM-dd_HHmm") + ".dump")
if ($env:GIPAME_DB_URL) {
  pg_dump --format=custom --no-owner --file=$fichier $env:GIPAME_DB_URL
} else {
  $env:PGPASSWORD = Valeur "GIPAME_DB_PASSWORD" "dev"
  pg_dump --format=custom --no-owner --file=$fichier -h (Valeur "GIPAME_DB_HOST" "127.0.0.1") -p (Valeur "GIPAME_DB_PORT" "5432") `
    -U (Valeur "GIPAME_DB_USER" "gipame_dev") (Valeur "GIPAME_DB_NAME" "gipame")
}
if ($LASTEXITCODE -ne 0) { Write-Error "Échec de la sauvegarde (voir le message de pg_dump ci-dessus)."; exit 1 }
$taille = [math]::Round((Get-Item $fichier).Length / 1KB)
Write-Host "Sauvegarde écrite : $fichier ($taille Ko)"
Write-Host "Restauration locale : createdb -U postgres -O gipame_dev gipame_local ; pg_restore --no-owner -U gipame_dev -d gipame_local $fichier"
