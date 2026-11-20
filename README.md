# Observatoire GIPAME

Plateforme de collecte mensuelle des ventes de véhicules neufs des membres du GIPAME (Côte d'Ivoire) :
gabarits Excel signés, dépôt contrôlé, stockage PostgreSQL sécurisé par rôle, publication de totaux
avec seuils de confidentialité, portail web.

**Pour installer, mettre en ligne (Neon + Render) et faire la recette : `GUIDE_DEMARRAGE_ET_RECETTE.md`.**
Ce fichier ne donne que le démarrage rapide. **Démonstration publique (données fictives) : https://observatoire-gipame-demo.onrender.com — mise en place décrite dans `MISE_EN_LIGNE_DEMO.md`.** Le document de passation complet (`PROJET_GIPAME.md` : contexte,
décisions, architecture, feuille de route) est tenu **hors du dépôt**, car il cite des constats tirés du fichier réel du client.

## Démarrage rapide

Prérequis : Python 3.13 et PostgreSQL 16 à 18 (le compte utilisé pour migrer doit pouvoir créer des rôles). Sous Windows, l'environnement virtuel se place à côté du code : `py -3.13 -m venv D:\GIPAME\venv_gipame`.

```bash
# 1. base de développement (Linux : scripts/dev_postgres.sh ; sinon, dans psql :)
#    CREATE ROLE gipame_dev SUPERUSER LOGIN PASSWORD 'dev';  CREATE DATABASE gipame OWNER gipame_dev;
pip install -r requirements.txt
python manage.py migrate
python manage.py test                        # 238 tests
python manage.py seed_demo                   # données fictives (6 membres, 22 mois)
python manage.py appliquer_droits_techniques
python manage.py verifier_installation       # doit répondre « Installation conforme »
python manage.py comptes_demo                # mots de passe de démonstration (DEBUG seulement)
```

Portail, avec la connexion non privilégiée comme en production (`ALTER ROLE gipame_app LOGIN PASSWORD 'app'` une fois) :

```bash
GIPAME_DB_USER=gipame_app GIPAME_DB_PASSWORD=app python manage.py runserver
```
```powershell
$env:GIPAME_DB_USER = "gipame_app"; $env:GIPAME_DB_PASSWORD = "app"; python manage.py runserver
```

Puis http://127.0.0.1:8000/ (page de présentation publique, puis « Accéder au portail ») : `user_a1@demo.gipame.ci` (membre), `gestionnaire@demo.gipame.ci` (gestion),
`president@demo.gipame.ci` (bureau) — mot de passe `demo-2026`. Galerie des composants : `/_galerie/`.

Comptes réels : **une seule fois**, avec la connexion propriétaire, créer l'administrateur de l'Observatoire
`python manage.py gerer_compte creer --email admin@… --prenom … --nom … --role TECHNIQUE` (le lien d'activation s'affiche) ;
ensuite tous les comptes (membres, gestion, bureau) se créent depuis l'écran **Comptes** du portail, sans ligne de commande.

Sauvegarde complète / export pour analyse locale : `scripts/sauvegarde.ps1` (Windows) ou `scripts/sauvegarde.sh`, puis
`createdb gipame_local` et `pg_restore --no-owner -d gipame_local <fichier.dump>`.

## Documents

| Fichier | Pour quoi faire |
|---|---|
| `README.md` | ce fichier : présentation et démarrage rapide |
| `GUIDE_DEMARRAGE_ET_RECETTE.md` | installation pas à pas, recette de sécurité, mise en ligne de la version réelle, exploitation, dépannage |
| `MISE_EN_LIGNE_DEMO.md` | la démonstration publique (Neon + Render, données fictives) et sa remise à zéro |
| `PLAN_DE_TESTS.md` | tests automatiques, balayage navigateur, scénarios de tests profonds et modèle de retour |
| `CAHIER_DE_TEST.md` / `.xlsx` | cahier de test complet (contexte, comptes, consignes pour un testeur humain ou IA, cas, suivi) |
| `ROUE_DE_SECOURS.md` | l'assistant d'aide : principe de sécurité, configuration, entretien mensuel, points d'attention |
| `PROJET_GIPAME.md` | document de passation complet (**hors dépôt**, sur le poste de Michel) |

## Organisation

| Dossier | Contenu |
|---|---|
| `collecte/` | modèle de données, SQL de sécurité (`sql/`), fichiers Excel (`excel/`), services, 110 tests |
| `portail/` | portail web (page de présentation, mode démonstration, vues, gabarits, CSS/JS auto-hébergés), 76 tests dont non-fuite |
| `roue_de_secours/` | assistant d'aide « Roue de Secours » (module autonome) : fiches d'aide (`connaissances/`), recherche, IA optionnelle, 52 tests dont non-fuite |
| `docs/identite/` | logo et charte (générateur `generer_logos.py`) ; `docs/captures/` : rendus vérifiés |
| `exemples/` | fichiers Excel fictifs produits par `demo_cycle` |
| `scripts/` | préparation PostgreSQL, essai complet (Linux), sauvegarde complète (`sauvegarde.ps1` / `.sh`), rôles avant restauration (`creer_roles.sql`), **balayage navigateur** de toutes les pages (`balayage.py`) |
| `render.yaml`, `render-demo.yaml`, `.github/workflows/` | déploiement Render (réel / démonstration), rappels quotidiens et contrôle mensuel de l'aide (GitHub Actions) |

## Règles non négociables

- Le membre vient **toujours** de `request.user` ; toute lecture/écriture passe par les services de `collecte`.
- Aucune quantité dans une URL, un titre, un message ou un journal ; la gestion ne voit aucune quantité individuelle.
- Les règles d'intégrité et de sécurité vivent dans la base (migrations SQL) et sont testées ; rien ne se supprime.
- Aucune donnée réelle dans le dépôt.
