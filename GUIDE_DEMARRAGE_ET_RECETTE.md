# Observatoire GIPAME — Guide de démarrage et de recette

> **À qui s'adresse ce guide** : à Michel, puis à toute personne qui reprend l'installation (pas besoin d'être
> développeur, mais il faut savoir ouvrir PowerShell et copier-coller une commande).
> **Ce qu'il couvre** : installer le projet sur un poste Windows, vérifier pas à pas qu'il est sûr, le mettre en
> ligne sur **Neon (base) + Render (application)**, charger les vraies données, mener le pilote, et décider si
> l'outil est prêt à être proposé plus largement.
> **Ce qu'il ne couvre pas** : l'architecture et les décisions (voir `PROJET_GIPAME.md`).
>
> Version du 17/11/2026 · 182 tests automatiques · Python 3.13 · PostgreSQL 16 (Neon) / 16 à 18 en local · Django 6.1.
>
> **Démonstration publique (données fictives)** : `https://observatoire-gipame-demo.onrender.com`, mise en ligne
> le 17/11/2026 selon `MISE_EN_LIGNE_DEMO.md`. Ce guide-ci concerne la **version réelle**.

**Comment lire les tests.** Chaque test indique ce qu'on fait, ce qu'on doit obtenir, et ce que vaut un échec :
- 🔴 **Bloquant** : on ne va pas plus loin tant que ce n'est pas corrigé (risque de fuite de données ou de perte).
- 🟠 **Important** : à corriger avant le pilote.
- 🟢 **Confort** : à noter, peut attendre.

Cochez au fur et à mesure (`[x]`) et gardez ce fichier rempli : c'est votre **procès-verbal de recette**.

---

## Sommaire

0. Ce qu'il faut avant de commencer
1. Installer le projet sur votre poste
2. Recette locale : les tests sensibles (avant toute mise en ligne)
3. Préparer les comptes en ligne (GitHub, Neon, Render, messagerie)
4. Mettre la base en ligne (Neon)
5. Mettre l'application en ligne (Render)
6. Premier compte administrateur et référentiel
7. Recette en ligne
8. Charger l'historique réel
9. Pilote avec quelques membres
10. Décision « prêt à être proposé » (go / no-go)
11. Routine d'exploitation (mois, semaine, trimestre, année)
12. En cas de problème

---

## 0. Ce qu'il faut avant de commencer

**Sur le poste Windows** (une seule fois) :

| Logiciel | Où | Remarque |
|---|---|---|
| Python **3.13** | python.org → Downloads → Windows installer (64-bit), dernière 3.13.x | « Customize installation », **sans** « Add python.exe to PATH » : on l'appelle avec `py -3.13` |
| PostgreSQL **16 à 18** | enterprisedb.com (Windows) | noter le mot de passe de `postgres` ; ajouter `C:\Program Files\PostgreSQL\<version>\bin` au PATH (voir ci-dessous). Les outils 18 fonctionnent avec la base Neon en 16 |
| Git | git-scm.com | options par défaut |
| Un gestionnaire de mots de passe | Bitwarden (gratuit) ou KeePassXC | **tous** les secrets de ce guide y vont |

Rendre `psql` disponible dans toutes les fenêtres PowerShell (une seule fois ; remplacer 18 par votre version) :
```powershell
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";C:\Program Files\PostgreSQL\18\bin", "User")
```
Vérification dans une **nouvelle** fenêtre PowerShell :
```powershell
py --list ; py -3.13 --version ; psql --version ; pg_dump --version ; git --version
```
Attendu : une ligne `-V:3.13` dans la liste, Python 3.13.x, psql/pg_dump 16 à 18, git 2.x.

**Le poste doit être chiffré** (BitLocker activé : Paramètres → Confidentialité et sécurité → Chiffrement de
l'appareil). Les sauvegardes de la base contiennent toutes les ventes de tous les membres.

**Une adresse e-mail institutionnelle du GIPAME** (ex. `observatoire@gipame.ci`) : c'est avec elle, et non avec
une adresse personnelle, que l'on crée les comptes GitHub, Neon, Render et messagerie (§3). Sinon, le jour du départ
de Michel, plus personne n'a la main sur l'hébergement.

---

## 1. Installer le projet sur votre poste

Toutes les commandes se lancent dans PowerShell, **dans le dossier du projet** (`D:\GIPAME\Application_GIPAME`).

### 1.1 Environnement Python
L'environnement virtuel vit **à côté** du code (`D:\GIPAME\venv_gipame`), pas dedans : il ne part ni dans Git ni
dans les copies du projet.
```powershell
cd D:\GIPAME
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned      # une fois, pour autoriser l'activation ci-dessous
py -3.13 -m venv venv_gipame
D:\GIPAME\venv_gipame\Scripts\Activate.ps1              # le début de ligne affiche (venv_gipame)
python -m pip install --upgrade pip
cd D:\GIPAME\Application_GIPAME
pip install -r requirements.txt -r requirements-dev.txt
playwright install chromium                                # seulement pour les captures d'écran
```
À chaque nouvelle fenêtre PowerShell : `D:\GIPAME\venv_gipame\Scripts\Activate.ps1 ; cd D:\GIPAME\Application_GIPAME`.
VS Code : « Python: Select Interpreter » → `D:\GIPAME\venv_gipame\Scripts\python.exe`.

### 1.2 Base de développement (sur votre poste)
Sans variable `GIPAME_DB_*`, l'application se connecte avec `gipame_dev` / `dev` sur la base `gipame` : ce compte
doit donc exister (sinon : « authentification par mot de passe échouée pour l'utilisateur gipame_dev »).
pgAdmin n'est pas nécessaire : `psql` suffit.
```powershell
psql -h 127.0.0.1 -U postgres -c "CREATE ROLE gipame_dev SUPERUSER LOGIN PASSWORD 'dev'"
createdb -h 127.0.0.1 -U postgres -O gipame_dev gipame
python manage.py migrate
python manage.py appliquer_droits_techniques
psql -U gipame_dev -d gipame -c "ALTER ROLE gipame_app LOGIN PASSWORD 'app'"
python manage.py seed_demo          # 6 membres fictifs, 22 mois de ventes et de publications
python manage.py comptes_demo
python manage.py verifier_installation
```
Attendu : la dernière commande se termine par **« Installation conforme. »** (une ligne INFO signale que `gipame_dev`
est superutilisateur : c'est normal en développement, interdit en production).

### 1.3 Lancer le portail comme en production
```powershell
$env:GIPAME_DB_USER = "gipame_app" ; $env:GIPAME_DB_PASSWORD = "app"
python manage.py runserver
```
Ouvrir http://127.0.0.1:8000/. Comptes de démonstration (mot de passe **`demo-2026`**) :

| Compte | Rôle |
|---|---|
| `user_a1@demo.gipame.ci`, `user_b1@…` … | déclarants (membres A1 à B3, fictifs) |
| `gestionnaire@demo.gipame.ci` | secrétariat (gestion) |
| `technicien@demo.gipame.ci` | administrateur de l'Observatoire (gestion + écran Comptes) |
| `president@demo.gipame.ci`, `vice_president@…`, `delegue_general@…` | bureau |

Fermer le serveur : `Ctrl + C`. Pour revenir à la connexion de développement : fermer la fenêtre PowerShell.

---

## 2. Recette locale : les tests sensibles

> Tout se fait sur la base de **démonstration** (§1.2). Pour repartir d'une base propre à tout moment :
> `dropdb -U postgres gipame` puis refaire §1.2.

### 2.1 Tests automatiques — 🔴 bloquant

- [ ] **T01 – Suite complète.** Fenêtre neuve (connexion de développement), puis `python manage.py test`.
  Attendu : `Ran 169 tests … OK`. Ces tests vérifient entre autres, **dans la vraie base PostgreSQL** : qu'un
  membre ne voit jamais les chiffres d'un autre (pages, exports, URL forgées), que la gestion ne lit aucune quantité,
  que le bureau ne voit ni le nombre de contributeurs ni le motif d'un masquage, que rien ne se supprime, que les
  rappels ne contiennent aucun chiffre.
- [ ] **T02 – Cycle complet avec la connexion non privilégiée.**
  ```powershell
  $env:GIPAME_DB_USER = "gipame_app" ; $env:GIPAME_DB_PASSWORD = "app"
  python manage.py demo_cycle --sortie sortie_demo
  ```
  Attendu : le cycle va jusqu'au bout (gabarits, dépôts, publication, exports) ; les fichiers sont dans `sortie_demo\`.
  Un échec ici = la matrice de droits est cassée.
- [ ] **T03 – Contrôle d'installation.** `python manage.py verifier_installation` → « Installation conforme ».

### 2.2 La base se défend toute seule — 🔴 bloquant

On vérifie que la sécurité est **dans la base**, pas seulement dans les écrans. Dans PowerShell :
```powershell
$env:PGPASSWORD = "app"
psql -h 127.0.0.1 -U gipame_app -d gipame
```
Puis, dans `psql`, taper chaque ligne et comparer :

| # | Commande | Résultat attendu |
|---|---|---|
| T04 | `SELECT count(*) FROM collecte_lignevente;` | `permission denied` (l'application seule ne lit rien) |
| T05 | `SET ROLE gipame_membre; SELECT count(*) FROM collecte_lignevente;` | `0` (aucun membre désigné → rien) |
| T06 | `SELECT set_config('app.membre_id','1',false); SELECT count(DISTINCT d.membre_id) FROM collecte_lignevente l JOIN collecte_declaration d ON d.id=l.declaration_id;` | `1` (on ne voit que **son** membre) |
| T07 | `RESET ROLE; SET ROLE gipame_gestion; SELECT count(*) FROM collecte_lignevente;` | `permission denied` (la gestion ne lit aucune quantité) |
| T08 | `RESET ROLE; SET ROLE gipame_bureau; SELECT n_contributeurs FROM collecte_celluleagregat LIMIT 1;` | `permission denied` (le bureau ne voit pas le nombre de contributeurs) |
| T09 | `RESET ROLE; SET ROLE gipame_gestion; DELETE FROM collecte_membre WHERE code='B3';` | `permission denied` |

Quitter : `\q`. Puis, avec la connexion **propriétaire** (même le propriétaire ne peut ni effacer ni falsifier) :
```powershell
$env:PGPASSWORD = "dev"
psql -h 127.0.0.1 -U gipame_dev -d gipame -c "BEGIN; DELETE FROM collecte_declaration WHERE id=(SELECT min(id) FROM collecte_declaration); ROLLBACK"
psql -h 127.0.0.1 -U gipame_dev -d gipame -c "BEGIN; UPDATE collecte_lignevente SET quantite=quantite+1 WHERE id=(SELECT min(id) FROM collecte_lignevente); ROLLBACK"
```
- [ ] **T10** – Attendu : « Suppression physique interdite… » puis « Les lignes d'une déclaration au statut SOUMISE ne sont plus modifiables ».

### 2.3 Cloisonnement entre membres, à la main — 🔴 bloquant

Portail lancé comme au §1.3. Utiliser **deux navigateurs** (ou une fenêtre normale + une fenêtre privée).

- [ ] **T11 – Déclaration complète.** En `user_a1` : Déclarer → télécharger le gabarit du mois précédent → saisir
  des quantités **reconnaissables** (ex. 7 777 et 4 321) → déposer → rapport vert → cocher l'attestation → Soumettre.
  Attendu : page de confirmation ; la déclaration apparaît dans Historique. Noter l'adresse (URL) de la page du rapport.
- [ ] **T12 – URL forgée.** En `user_b1` (autre navigateur) : coller l'URL du rapport d'A1, puis modifier le numéro
  dans l'URL (±1, ±2). Attendu : « Page introuvable » à chaque fois, jamais les chiffres d'A1.
- [ ] **T13 – Fichier d'un autre.** En `user_b1` : déposer le **fichier d'A1** (celui de T11).
  Attendu : refusé, « Ce fichier n'a pas été généré pour votre compte ».
- [ ] **T14 – Recherche des chiffres d'A1.** Connecté successivement en `user_b1`, `gestionnaire`, `president` :
  parcourir **toutes** les pages du menu et faire `Ctrl + F` → `7777`, `7 777`, `4321`, `4 321`. Attendu : **aucune occurrence**.
  Exporter « Mon année » de B1 (Excel) et chercher pareil : aucune occurrence.

### 2.4 Fichiers piégés — 🟠 important

En `user_a1`, déposer successivement (chaque fois : un message lisible en français, **jamais** une page « Erreur serveur ») :
- [ ] **T15** un gabarit où l'on a modifié une cellule grise (libellé d'un produit) → « Fichier modifié ou non reconnu » ;
- [ ] **T16** le gabarit enregistré en `.xlsm` (avec macros) ou en `.csv` renommé en `.xlsx` → « Fichier illisible » ;
- [ ] **T17** un gabarit avec une ligne supprimée, puis un autre avec une quantité `12,5` ou `-3` → message précis avec la ligne ;
- [ ] **T18** toutes les quantités à 0 sans répondre OUI à « Aucune vente » → l'erreur l'explique ; avec OUI → accepté ;
- [ ] **T19** une correction : retélécharger le mois déjà soumis, changer une quantité, déposer → le motif est demandé ; après
  soumission, l'historique montre deux versions.

### 2.5 Comptes et connexion — 🔴 bloquant

- [ ] **T20 – Création sans ligne de commande.** En `technicien` : Comptes → Créer un compte (rôle Membre, société B2) →
  le lien d'activation s'affiche. L'ouvrir dans une fenêtre privée → choisir un mot de passe → connexion réussie.
- [ ] **T21 – Lien à usage unique.** Rouvrir le même lien : il est refusé.
- [ ] **T22 – Blocage.** Sur la page de connexion, 5 mauvais mots de passe pour un même e-mail → message de blocage de
  15 minutes ; le bon mot de passe est refusé pendant ce délai.
- [ ] **T23 – Désactivation.** En `technicien` : désactiver le compte de T20 (motif obligatoire) → la personne ne peut
  plus se connecter ; le Journal des accès du bureau le montre.
- [ ] **T24 – Rôles.** En `gestionnaire`, ouvrir `http://127.0.0.1:8000/administration/comptes/` → « accès refusé ».
  En `user_a1`, ouvrir `/gestion/` et `/bureau/` → « accès refusé ».

### 2.6 Gestion, publication, accès exceptionnel — 🔴 bloquant

- [ ] **T25 – Membres.** En `gestionnaire` : Membres → Ajouter un membre (code `TEST`, une marque) → la fiche s'ouvre.
  Clore l'adhésion à un mois, puis tenter d'ouvrir une période qui la chevauche → refus expliqué.
- [ ] **T26 – Publication.** Publications → « Calculer (provisoire) » sur le mois de T11 → message de couverture.
  « Publier en définitif » sans cocher « je confirme » → refusé. En `user_a1` → Le marché : le mois apparaît ; des
  cases « c » peuvent apparaître (confidentiel) avec leur explication.
- [ ] **T27 – La gestion ne voit pas les totaux individuels.** Sur Publications et Dépôts : seulement des statuts,
  des dates et la couverture (x / y membres).
- [ ] **T28 – Accès exceptionnel.** En `gestionnaire` : Accès exceptionnel → demande sur A1, mois de T11, 30 min.
  « Ouvrir » → **refusé** (accord insuffisant). En `president` : Approbations → approuver. Re-tenter en gestion → toujours
  refusé (1 accord sur 2). En `vice_president` : approuver. En gestion : lecture **autorisée**, on voit 7 777 et 4 321.
  En `president` : Journal des accès → la lecture y figure (qui, quand, combien de lignes), **sans les chiffres**.

### 2.7 Rappels — 🟠 important

- [ ] **T29.** En `gestionnaire` : Dépôts → « Envoyer les rappels ». En développement, les e-mails s'affichent dans
  la fenêtre PowerShell du serveur. Attendu : un e-mail **par destinataire**, qui ne cite que **sa** société, la date
  limite et le lien ; aucun chiffre de vente, aucun autre membre, pas de liste de destinataires.

### 2.8 Sauvegarde et restauration — 🔴 bloquant

```powershell
$env:GIPAME_DB_USER = "gipame_dev" ; $env:GIPAME_DB_PASSWORD = "dev"
.\scripts\sauvegarde.ps1
createdb -U postgres -O gipame_dev gipame_restaure
pg_restore --no-owner -U gipame_dev -d gipame_restaure .\sauvegardes\<fichier>.dump
psql -U gipame_dev -d gipame_restaure -c "SELECT count(*) FROM collecte_lignevente"
psql -U gipame_dev -d gipame -c "SELECT count(*) FROM collecte_lignevente"
```
- [ ] **T30** – Les deux nombres sont égaux. Ensuite : `dropdb -U postgres gipame_restaure`.

Sur un **autre poste** (analyse hors ligne sur une machine neuve) : installer PostgreSQL 16, puis
`psql -U postgres -f scripts\creer_roles.sql` **avant** `pg_restore` (les rôles ne sont pas dans la sauvegarde).
On travaille ensuite en connexion `postgres` : elle voit tout, c'est voulu pour l'analyse ; le poste doit donc être chiffré.

### 2.9 Mode production sur votre poste — 🟠 important

```powershell
$env:DJANGO_DEBUG = "0" ; $env:DJANGO_SECRET_KEY = "essai-local" ; $env:DJANGO_SSL_REDIRECT = "0"
$env:DJANGO_ALLOWED_HOSTS = "127.0.0.1" ; $env:GIPAME_DB_URL = "postgresql://gipame_app:app@127.0.0.1:5432/gipame"
python manage.py collectstatic --noinput
python manage.py runserver --insecure
```
- [ ] **T31** – Le portail s'affiche normalement (styles, logo, graphiques) ; une adresse inexistante affiche la page
  « introuvable » de l'Observatoire (pas une page technique jaune) ; `python manage.py seed_demo` est **refusé**.
  (Sous Linux, l'équivalent exact de Render est `gunicorn config.wsgi:application` ; il a été vérifié le 12/11/2026.)

**Fin de la recette locale.** Tous les 🔴 doivent être cochés avant de passer au §3.

---

## 3. Préparer les comptes en ligne

Créer chaque compte **avec l'adresse institutionnelle du GIPAME**, activer la **double authentification** partout,
ranger identifiants et codes de secours dans le gestionnaire de mots de passe. Prévoir une **enveloppe scellée** remise au
bureau (identifiants + codes de secours) : c'est elle qui permet de reprendre la main si l'administrateur part.

| Service | Pour quoi | Offre |
|---|---|---|
| **GitHub** (github.com) | héberger le code (dépôt **privé**), lancer les rappels automatiques | gratuit |
| **Neon** (neon.com) | la base PostgreSQL | gratuit (Free) |
| **Render** (render.com) | l'application web | gratuit au départ, Starter ≈ 7 $/mois ensuite |
| **Messagerie SMTP** | envoyer activations, mots de passe oubliés, rappels | Brevo (offre gratuite, quelques centaines d'e-mails/jour) ou la messagerie du GIPAME |

Pour la messagerie : faire **authentifier le domaine** `gipame.ci` auprès du service (enregistrements SPF/DKIM à ajouter
chez le gestionnaire du nom de domaine), sinon les e-mails finiront en courrier indésirable.

### 3.1 Mettre le code sur GitHub (dépôt privé)
```powershell
cd D:\GIPAME\Application_GIPAME
git init -b main
git add .
git status          # VÉRIFIER : aucun fichier de vraies données, aucune sauvegarde, aucun .env
git commit -m "Observatoire GIPAME : version de mise en ligne"
```
Sur github.com : New repository → nom `observatoire-gipame` → **Private** → Create. Puis :
```powershell
git remote add origin https://github.com/<compte>/observatoire-gipame.git
git push -u origin main
```
- [ ] **T32 – 🔴 Aucune donnée réelle sur GitHub.** Sur la page du dépôt, parcourir les dossiers : seuls `exemples/`
  contient des fichiers Excel, tous **fictifs** (membres « (démo) »). Le vrai fichier du client n'est jamais dans ce dossier :
  le ranger dans `donnees_reelles\` (ignoré par Git) ou ailleurs.

---

## 4. Mettre la base en ligne (Neon)

1. Neon → **New project** : nom `observatoire-gipame`, **Postgres version 16**, région **AWS Europe Central 1 (Frankfurt)**.
2. Bouton **Connect** : choisir la branche principale (Neon l'appelle `production`), la base `neondb`, le rôle
   `neondb_owner`, **désactiver « Connection pooling »** (l'hôte ne doit pas contenir `-pooler`), **Show password**, copier
   l'adresse (la fin `&channel_binding=require` est normale). Elle ressemble à `postgresql://neondb_owner:XXXX@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`.
   **C'est l'adresse PROPRIÉTAIRE** : elle va dans le gestionnaire de mots de passe et **nulle part ailleurs**
   (ni Render, ni GitHub, ni un e-mail).
3. Sur votre poste, fenêtre PowerShell neuve, environnement activé :
   ```powershell
   $env:GIPAME_DB_URL = "<adresse propriétaire copiée>"
   python manage.py migrate
   python manage.py appliquer_droits_techniques
   python -c "import secrets; print(secrets.token_urlsafe(32))"      # mot de passe de gipame_app → gestionnaire de mots de passe
   psql "$env:GIPAME_DB_URL" -c "ALTER ROLE gipame_app LOGIN PASSWORD '<mot de passe généré>'"
   python manage.py verifier_installation
   ```
- [ ] **T33 – 🔴** `verifier_installation` répond « Installation conforme », **sans** la ligne « superutilisateur »
  (attendu : « INFO connecté en tant que neondb_owner (non superutilisateur) »).
  (Si la migration échoue sur la création des rôles : le projet Neon n'est pas vierge, en recréer un.)
   Sécurité de l'affichage : une adresse colle son mot de passe en clair. Ne jamais l'envoyer telle quelle (capture,
   message, assistant) ; pour la copier sans l'afficher : `... | Set-Clipboard`. Pour lire une adresse sans la montrer à
   l'écran : `$url = Read-Host "Adresse"`.
4. Construire l'**adresse de l'application** (même hôte, rôle `gipame_app`) :
   `postgresql://gipame_app:<mot de passe généré>@ep-xxxx.eu-central-1.aws.neon.tech/neondb?sslmode=require`
   → gestionnaire de mots de passe (« URL APPLICATION »).
- [ ] **T34 – 🔴** Avec l'URL APPLICATION : `psql "<URL APPLICATION>" -c "SELECT count(*) FROM collecte_membre"` →
  `permission denied`. C'est le résultat voulu : l'application seule n'a aucun droit.

---

## 5. Mettre l'application en ligne (Render)

1. Render → **New → Blueprint** → connecter GitHub → choisir `observatoire-gipame`. Render lit `render.yaml`
   (application `observatoire-gipame`, région Frankfurt, offre Free).
2. Renseigner les valeurs demandées :

| Variable | Valeur |
|---|---|
| `GIPAME_DB_URL` | l'**URL APPLICATION** (`gipame_app`, jamais le propriétaire) |
| `GIPAME_URL_PUBLIQUE` | `https://observatoire-gipame.onrender.com` (adresse affichée par Render, sans `/` final) |
| `GIPAME_EMAIL_EXPEDITEUR` | `Observatoire GIPAME <observatoire@gipame.ci>` |
| `GIPAME_SMTP_HOTE`, `…_UTILISATEUR`, `…_MOT_DE_PASSE` | fournis par le service de messagerie (Brevo : `smtp-relay.brevo.com`) |

   `DJANGO_SECRET_KEY` et `GIPAME_CLE_GABARIT` sont générées automatiquement. **Ne jamais changer `GIPAME_CLE_GABARIT`**
   ensuite : tous les gabarits déjà distribués deviendraient invalides.
3. **Apply** → attendre « Live » (3 à 5 minutes). Si l'adresse réelle diffère de celle saisie pour `GIPAME_URL_PUBLIQUE`,
   la corriger dans Environment → Save (Render redéploie).

- [ ] **T35 – 🔴** `https://<adresse>/sante/` affiche `ok`.
- [ ] **T36 – 🔴** `https://<adresse>/` affiche la page de connexion, avec le cadenas dans la barre d'adresse.
  `http://<adresse>/` (sans « s ») redirige vers `https://`.
- [ ] **T37 – 🟠** Sur securityheaders.com, saisir l'adresse : en-têtes `Strict-Transport-Security`, `X-Frame-Options`,
  `X-Content-Type-Options`, `Referrer-Policy` présents.
- [ ] **T38 – 🟢** Laisser l'application 20 minutes sans visite, puis l'ouvrir : noter le délai du premier affichage
  (attendu : 30 à 60 s en offre gratuite). Si c'est jugé gênant par les membres : passer Render en **Starter**
  (Settings → Instance type) — rien d'autre à changer.

**Adresse personnalisée (facultatif)** : Render → Settings → Custom Domains → `observatoire.gipame.ci`, puis ajouter
l'enregistrement CNAME indiqué chez le gestionnaire du domaine ; mettre à jour `GIPAME_URL_PUBLIQUE`.

### 5.1 Rappels automatiques (GitHub Actions)
Si le dossier `.github\workflows\` n'existe pas encore dans votre copie, le créer et y copier le fichier fourni :
```powershell
New-Item -ItemType Directory -Force .github\workflows ; Copy-Item docs\deploiement\rappels.yml .github\workflows\rappels.yml
git add .github ; git commit -m "Rappels automatiques" ; git push
```
GitHub → dépôt → Settings → Secrets and variables → Actions → **New repository secret**, un par ligne :
`GIPAME_DB_URL` (URL APPLICATION), `DJANGO_SECRET_KEY` (n'importe quelle longue valeur), `GIPAME_URL_PUBLIQUE`,
`GIPAME_EMAIL_EXPEDITEUR`, `GIPAME_SMTP_HOTE`, `GIPAME_SMTP_UTILISATEUR`, `GIPAME_SMTP_MOT_DE_PASSE`.
- [ ] **T39 – 🟠** Onglet Actions → « Rappels de dépôt » → **Run workflow** → la tâche se termine en vert et affiche
  « pas un jour de rappel » ou le bilan de l'envoi. Ensuite elle tourne seule chaque jour à 8 h (J-3, J+1, J+7 autour de
  la date limite).

---

## 6. Premier compte administrateur et référentiel

1. **Le seul passage en ligne de commande**, une fois, avec l'adresse propriétaire :
   ```powershell
   $env:GIPAME_DB_URL = "<adresse propriétaire>"
   $env:GIPAME_URL_PUBLIQUE = "https://<adresse Render>"
   python manage.py gerer_compte creer --email observatoire@gipame.ci --prenom Observatoire --nom GIPAME --role TECHNIQUE
   ```
   Le lien d'activation s'affiche : l'ouvrir, choisir un mot de passe fort.
- [ ] **T40 – 🔴** Connexion réussie ; le menu montre « Comptes ».
2. Fermer la fenêtre PowerShell (l'adresse propriétaire ne doit pas traîner dans une session ouverte).
3. **Tout le reste se fait dans le portail**, sans ligne de commande :
   - Membres → créer les membres (ou les laisser créer par le chargement de l'historique, §8) ; vérifier groupes
     économiques, adhésions, marques ;
   - Comptes → créer les comptes **bureau** (avec leur poste), **gestion**, puis un compte **déclarant** par membre ;
   - renseigner, avec l'adresse propriétaire, le contact et la définition de la vente (une fois) :
     ```powershell
     psql "<adresse propriétaire>" -c "UPDATE collecte_parametresysteme SET valeur='secretariat@gipame.ci' WHERE cle='contact_gipame'"
     psql "<adresse propriétaire>" -c "UPDATE collecte_parametresysteme SET valeur='Véhicules neufs facturés au client final dans le mois.' WHERE cle='definition_vente'"
     ```
     (la définition exacte est à **faire valider par écrit par le GIPAME** avant le pilote).
- [ ] **T41 – 🔴** Aucun compte de démonstration en ligne : Comptes ne montre aucune adresse `@demo.gipame.ci`.

---

## 7. Recette en ligne

Refaire, **sur l'adresse en ligne**, avec deux membres de test créés pour l'occasion (codes `ESSAI1`, `ESSAI2`, à clore
ensuite par Membres → Clore l'adhésion) :
- [ ] **T42 – 🔴** T11 à T14 (déclaration, URL forgée, fichier d'un autre, recherche des chiffres) ;
- [ ] **T43 – 🔴** T20 à T23 (création, activation **reçue par e-mail**, lien unique, blocage, désactivation) ;
- [ ] **T44 – 🟠** T26 et T29 (publication, rappels **reçus par e-mail**, pas dans les indésirables) ;
- [ ] **T45 – 🔴** Sauvegarde **depuis la base en ligne** puis restauration locale (§2.8 avec
  `$env:GIPAME_DB_URL = "<adresse propriétaire>"` avant `.\scripts\sauvegarde.ps1`) : comptes identiques ;
- [ ] **T46 – 🟠** Tout le parcours déclarant sur un **téléphone** (4G) : lisible, boutons utilisables, dépôt possible.
- [ ] **T47 – 🟢** Neon → Monitoring : la base se met en veille quand personne n'utilise le portail (sinon, chercher
  ce qui la réveille : une sonde externe qui interroge autre chose que `/sante/`, par exemple).

---

## 8. Charger l'historique réel

> Le vrai fichier ne quitte pas votre poste et ne va jamais dans Git. Seul son **contenu** part dans la base, par la
> connexion propriétaire. **Avant** cette étape : la question ARTCI (données hors CEDEAO, §10) doit être tranchée.

Pour chaque année du fichier (ex. 2022 à 2026), fenêtre PowerShell avec `$env:GIPAME_DB_URL = "<adresse propriétaire>"` :
```powershell
python manage.py historique_analyser --fichier D:\GIPAME\donnees_reelles\MTM_2024.xlsx --annee 2024 --sortie D:\GIPAME\donnees_reelles\rapprochement
# → ouvrir le fichier de rapprochement produit, le relire et le corriger (codes membres, marques, produits, doublons)
python manage.py historique_charger --fichier D:\GIPAME\donnees_reelles\MTM_2024.xlsx --rapprochement <fichier corrigé> --annee 2024 --a-blanc
# → lire le compte rendu ; recommencer l'analyse/correction tant qu'il signale des anomalies
python manage.py historique_charger --fichier D:\GIPAME\donnees_reelles\MTM_2024.xlsx --rapprochement <fichier corrigé> --annee 2024 --utilisateur observatoire@gipame.ci
```
- [ ] **T48 – 🔴** Faire une **sauvegarde avant** chaque chargement réel (§2.8).
- [ ] **T49 – 🔴** Pour une année chargée, le total annuel recalculé dans le portail (bureau → Le marché, après
  publication) correspond à la **somme des lignes** de l'ancien fichier (et non à ses totaux, qui contenaient des erreurs).
  Écarts expliqués par écrit.
- [ ] **T50 – 🟠** Membres : groupes économiques et périodes d'adhésion **conformes à la réalité** (sinon la couverture et
  les règles de confidentialité sont faussées).
- Publier les mois anciens : l'écran Publications couvre les 12 derniers mois ; pour les plus anciens, avec l'URL
  APPLICATION : `python manage.py calculer_publication --mois 2024-01 --definitive` (une fois par mois).

---

## 9. Pilote avec quelques membres

**Format conseillé** : 3 à 5 membres volontaires, **en parallèle** de l'ancien fichier, sur 2 cycles mensuels.

- [ ] **T51 – 🟠** Formation de 30 minutes par membre (partage d'écran) : activation, 3 étapes, rapport, correction, Aide.
- [ ] **T52 – 🟠** Chaque déclarant pilote dépose **seul** son mois. Noter : temps passé, erreurs rencontrées, questions.
- [ ] **T53 – 🔴** Comparer, membre par membre, ce qu'il a déclaré dans le portail et dans l'ancien fichier : identique.
- [ ] **T54 – 🟠** Après le premier cycle : publication provisoire, puis définitive ; le bureau la consulte ; la gestion
  envoie les rappels ; le bureau lit le Journal des accès du mois.
- [ ] **T55 – 🟠** Recueillir l'avis des membres (lisibilité, lenteur éventuelle au réveil, confiance) ; corriger avant
  d'élargir.

---

## 10. Décision « prêt à être proposé » (go / no-go)

À présenter au bureau du GIPAME. **Tout doit être coché** avant d'ouvrir l'Observatoire à tous les membres ou de le
présenter comme un produit fini.

**Technique**
- [ ] Tous les tests 🔴 de ce guide cochés, en local **et** en ligne (T01–T46).
- [ ] Une restauration complète réussie depuis la base en ligne datant de moins d'un mois.
- [ ] Un deuxième cycle mensuel du pilote sans incident bloquant.

**Juridique et gouvernance**
- [ ] **ARTCI** : la question du transfert de données hors CEDEAO (loi n° 2013-450) est tranchée par écrit (autorisation,
  avis d'un conseil, ou choix d'un hébergeur local).
- [ ] **Convention de collecte** signée par chaque membre (objet, définition de la vente, confidentialité, accès
  exceptionnel, durée de conservation) — modèle à faire rédiger ou relire par un juriste.
- [ ] **Charte de confidentialité** (`/confidentialite/`) relue et validée par le bureau ; hébergeur indiqué exact.
- [ ] **Définition de la vente** validée par écrit et affichée (§6).

**Organisation et continuité**
- [ ] Un **référent GIPAME** formé : sait créer un compte, ajouter un membre, publier un mois, envoyer les rappels,
  lire le journal, faire une sauvegarde.
- [ ] Enveloppe scellée (accès GitHub, Neon, Render, messagerie, adresse propriétaire) remise au bureau.
- [ ] Budget décidé pour Render Starter (≈ 7 $/mois) si l'offre gratuite est jugée trop lente.
- [ ] Un contact technique identifié pour les incidents (prestataire, ENSEA, ou successeur).

---

## 11. Routine d'exploitation

**Chaque mois** (référent GIPAME, dans le portail)
1. J+1 à J+10 : suivre « Dépôts » ; les rappels partent seuls (J-3, J+1, J+7) ; bouton « Envoyer les rappels » si besoin.
2. Valider les produits proposés (« Propositions »).
3. « Publications » : provisoire dès les premières déclarations ; **définitif** quand la couverture atteint le seuil.
4. Bureau : lire le **Journal des accès** du mois (Imprimer → archiver le PDF).

**Chaque semaine** (poste chiffré) : `.\scripts\sauvegarde.ps1` avec l'adresse propriétaire ; garder les 8 dernières,
plus une par mois sur un second support (disque externe chiffré).

**Chaque trimestre** : restaurer la dernière sauvegarde en local (§2.8) — une sauvegarde jamais restaurée n'est pas une
sauvegarde. Vérifier dans Neon que le stockage reste sous la limite gratuite et que le quota de calcul n'est pas atteint.

**Chaque année** : revue des comptes (désactiver les personnes parties), des groupes économiques et des adhésions ;
mise à jour de sécurité (`pip install -r requirements.txt --upgrade` **en local**, `python manage.py test` → tout vert,
puis `git push`) ; renouveler la question ARTCI si l'hébergeur change.

---

### 11.1 Roue de Secours (assistant d'aide) : entretien mensuel

- `python manage.py roue_avis --sortie avis.md` (connexion propriétaire) : lire les avis « À revoir » et les questions
  sans réponse ; corriger ou créer les fiches (`roue_de_secours/connaissances/`) ; ajouter les questions au jeu
  d'évaluation ; `python manage.py roue_verifier` ; tests ; push.
- Le contrôle mensuel GitHub Actions (« Roue de Secours — contrôle de l'aide ») envoie un courriel s'il échoue :
  fiche non relue depuis un an, lien mort, recherche dégradée.
- Une fois par an : `roue_avis --purger 365` ; vérifier que le modèle d'IA (`GIPAME_ROUE_MODELE`) est toujours proposé
  par le prestataire (`roue_essai`).
- **Production réelle** : ne pas renseigner `GIPAME_ROUE_CLE_API` sans l'accord écrit du GIPAME (transfert des
  questions vers un prestataire étranger, voir `ROUE_DE_SECOURS.md` §6). Sans clé, le mode simplifié reste disponible.

## 12. En cas de problème

| Symptôme | Cause probable | Que faire |
|---|---|---|
| Le portail met une minute à s'ouvrir | mise en veille de l'offre gratuite Render | normal ; passer en Starter si gênant |
| « Erreur serveur » partout | `GIPAME_DB_URL` erroné, ou quota Neon atteint | Render → Logs ; Neon → Usage. Quota atteint : passer au plan Launch (paiement à l'usage) |
| Les e-mails n'arrivent pas | SMTP mal renseigné, domaine non authentifié | Render → Environment ; tester « mot de passe oublié » ; vérifier SPF/DKIM |
| Un membre dit voir des chiffres d'un autre | **incident de confidentialité** | désactiver les comptes concernés, prévenir le bureau, ne rien modifier en base, faire une sauvegarde, analyser avec le Journal des accès et `collecte_journalmodification` |
| Tous les gabarits sont refusés « fichier modifié » | `GIPAME_CLE_GABARIT` a changé | remettre l'ancienne valeur (gestionnaire de mots de passe) |
| Un membre ne reçoit plus de gabarit avec ses produits | adhésion ou marques closes | Membres → fiche du membre |
| `psql` n'est pas reconnu | dossier `bin` de PostgreSQL absent du PATH | `$env:Path += ";C:\Program Files\PostgreSQL\18\bin"` (fenêtre en cours) ; durable : §0 |
| « authentification par mot de passe échouée pour gipame_dev » (tests, `check`) | compte de développement absent ou autre mot de passe | §1.2 : `CREATE ROLE gipame_dev …` ou `ALTER ROLE gipame_dev … PASSWORD 'dev'` |
| pgAdmin : liste des serveurs vide, « Failed to fetch », « Connection to pgAdmin server has been lost » | le serveur interne de pgAdmin a planté (la base n'est pas touchée) | fermer pgAdmin (Gestionnaire des tâches), relancer ; sinon renommer `%APPDATA%\pgAdmin` ; en attendant, `psql` suffit |
| Erreur de syntaxe sur un chemin `C:\Users\N'…` | l'apostrophe du nom d'utilisateur Windows ferme la chaîne | mettre les fichiers de travail dans `D:\GIPAME\` (chemin sans apostrophe) |
| Neon : « permission denied to set role "gipame_calcul" » | le propriétaire Neon n'est pas superutilisateur | seulement pour `seed_demo` (démonstration) : `GRANT gipame_calcul TO neondb_owner`, la commande, puis `REVOKE` ; le portail, lui, calcule via `gipame_app` |
| Un gabarit téléchargé ne s'ouvre pas dans Excel (« problème dans le contenu », puis échec de la réparation) | mode protégé d'Excel sur un fichier venu d'Internet | clic droit → Propriétés → **Débloquer**, puis rouvrir ; si cela ne suffit pas : envoyer le fichier, le message exact et la version d'Excel |
| Une fenêtre Windows « Demande d'informations d'identification » s'ouvre | commande mal collée (guillemet perdu) | **Annuler**, ne rien saisir ; recoller la commande en entier |
| Perte de la base | — | Neon : nouveau projet vierge (§4, étapes 1–2), puis `psql "<adresse propriétaire>" -f scripts/creer_roles.sql`, `pg_restore --no-owner --dbname "<adresse propriétaire>" <dernière sauvegarde>`, `ALTER ROLE gipame_app LOGIN PASSWORD '…'`, `verifier_installation` ; enfin mettre la nouvelle URL APPLICATION dans Render et GitHub |

Pour tout le reste : `PROJET_GIPAME.md` (§13 pièges connus, §14 limites, §6 sécurité).
