# Mettre la démonstration en ligne (Neon + Render)

Objectif : une adresse publique, par exemple `https://observatoire-gipame-demo.onrender.com`, que l'on peut partager
pour faire essayer l'Observatoire. Elle fonctionne exactement comme la future version réelle (même code, sécurité en
base, connexion non privilégiée, HTTPS), mais :

- la base est une base **à part**, remplie de **données fictives** (6 membres, 22 mois de ventes, publications) ;
- un bandeau **« Démonstration »** apparaît sur toutes les pages ;
- la page de connexion propose les **comptes d'essai** (un clic remplit l'adresse et le mot de passe `demo-2026`) ;
- les comptes d'essai ne peuvent être ni désactivés ni modifiés, pour qu'un visiteur ne bloque pas les suivants ;
- aucun courriel ne part (ils s'écrivent dans les journaux de Render).

> Ne **jamais** mettre `GIPAME_MODE_DEMO=1` sur la future base réelle. La démonstration et la production auront chacune
> leur projet Neon et leur service Render.

Durée : environ 45 minutes la première fois.

**État (17/11/2026) : en ligne** à `https://observatoire-gipame-demo.onrender.com` — projet Neon
`observatoire-gipame-demo` (PostgreSQL 16, Francfort ; branches `production` = modèle propre et `demo` = base utilisée
par Render), Blueprint Render `observatoire-gipame-demo` (fichier `render-demo.yaml`, offre Free).

---

## 1. Envoyer la dernière version du code sur GitHub

```powershell
cd D:\GIPAME\Application_GIPAME
git add -A
git status          # ni PROJET_GIPAME.md, ni PROMPT_DE_REPRISE.md, ni __pycache__
git commit -m "Démonstration en ligne : mode démo, historique fictif, fichiers Excel normalisés"
git push
```

## 2. Créer la base de démonstration (Neon)

1. Neon → **New project** : nom `observatoire-gipame-demo`, **Postgres 16**, région **AWS Europe Central 1 (Frankfurt)**.
2. **Connect** → branche `production`, base `neondb`, rôle `neondb_owner`, **« Connection pooling » désactivé** → copier l'adresse.
   C'est l'**adresse propriétaire de la démo** : gestionnaire de mots de passe uniquement (ni Render, ni GitHub).
3. Sur votre poste, PowerShell, environnement activé (`D:\GIPAME\venv_gipame\Scripts\Activate.ps1`) :

```powershell
cd D:\GIPAME\Application_GIPAME
$env:GIPAME_DB_URL    = "<adresse propriétaire de la démo>"
$env:DJANGO_DEBUG     = "0"
$env:GIPAME_MODE_DEMO = "1"

$env:Path += ";C:\Program Files\PostgreSQL\18\bin"   # psql, si ce n'est pas déjà fait
python manage.py migrate
python manage.py appliquer_droits_techniques
psql "$env:GIPAME_DB_URL" -c "GRANT gipame_calcul TO neondb_owner"     # Neon : le propriétaire n'est pas superutilisateur
python manage.py seed_demo            # 6 membres fictifs, 22 mois de ventes, publications
psql "$env:GIPAME_DB_URL" -c "REVOKE gipame_calcul FROM neondb_owner"  # droit retiré aussitôt
python manage.py comptes_demo         # comptes <nom>@demo.gipame.ci, mot de passe demo-2026

# mot de passe de la connexion de l'application (gipame_app)
$mdp = python -c "import secrets; print(secrets.token_urlsafe(24))"
psql "$env:GIPAME_DB_URL" -c "ALTER ROLE gipame_app LOGIN PASSWORD '$mdp'"
python manage.py verifier_installation   # doit finir par « Installation conforme. »

# adresse de l'APPLICATION (rôle gipame_app) : à copier pour Render
$env:GIPAME_DB_URL -replace '^postgresql://[^@]+@', "postgresql://gipame_app:$mdp@"
```

La dernière ligne affiche l'**adresse application**. Rangez-la dans le gestionnaire de mots de passe.
Pour la copier sans l'afficher : remplacer la dernière ligne par `(... ) | Set-Clipboard`.

Ordre important : changer le mot de passe de `gipame_app` **avant** de créer la branche `demo` (une branche copie les
rôles et leurs mots de passe au moment de sa création ; ensuite, chaque branche a les siens).

Si `psql` n'est pas reconnu : `$env:Path += ";C:\Program Files\PostgreSQL\18\bin"`.

4. **Point de remise à zéro.** Neon → **Branches** → **Create branch** : nom `demo`, **Auto-delete : Never**, parent
   `production` (la branche principale, parfois appelée `main`), option « Branch data and schema ».
   Ouvrez la branche `demo` → **Connect** → recopiez l'adresse, puis remplacez-y le rôle et le mot de passe comme
   ci-dessus (`gipame_app` et `$mdp`). **C'est cette adresse (branche `demo`) que Render utilisera.**
   La branche `production` reste intacte : elle sert de modèle propre.

## 3. Mettre l'application en ligne (Render)

1. Render (connexion « Sign in with GitHub », accès au dépôt autorisé) → **New → Blueprint** → choisir le dépôt
   `observatoire-gipame` → nom du Blueprint : `observatoire-gipame-demo` → champ **Blueprint Path** : `render-demo.yaml`.
2. Renseigner :

| Variable | Valeur |
|---|---|
| `GIPAME_DB_URL` | l'adresse application de la **branche `demo`** (rôle `gipame_app`) |
| `GIPAME_URL_PUBLIQUE` | `https://observatoire-gipame-demo.onrender.com` (sans `/` final) |

3. **Apply**, puis attendre l'état **Live** (3 à 5 minutes).

Si le champ « Blueprint Path » n'apparaît pas, passez par **New → Web Service** → dépôt → région Frankfurt, avec :
Build `pip install -r requirements.txt && python manage.py collectstatic --noinput`,
Start `gunicorn config.wsgi:application --workers 2 --timeout 120 --access-logfile -`,
Health check `/sante/`, et les variables `DJANGO_DEBUG=0`, `GIPAME_MODE_DEMO=1`, `DJANGO_SECRET_KEY` (valeur
générée), `GIPAME_CLE_GABARIT` (valeur générée), `GIPAME_DB_URL`, `GIPAME_URL_PUBLIQUE`.

## 4. Vérifications avant de partager le lien

- [x] `https://<adresse>/sante/` affiche `ok` (vérifié le 17/11/2026).
- [x] `https://<adresse>/connexion/` : bandeau « Démonstration » et profils d'essai Membre ×2, Gestion, Bureau,
      Administration (vérifié le 17/11/2026).
- [ ] `https://<adresse>/` : page de présentation, pastille « Démonstration » en bas de l'écran, photos des véhicules.
- [ ] « Accéder au portail » → les comptes d'essai sont proposés ; **Membre (Alpha Motors)** → connexion.
- [ ] **Déclarer** → télécharger le gabarit du mois dernier → **l'ouvrir dans Excel** depuis le dossier Téléchargements
      (bandeau jaune « Mode protégé » : « Activer la modification »). C'est le test du problème d'ouverture ; voir §6.
- [ ] Remplir quelques quantités, enregistrer, déposer → rapport de contrôle → soumettre → confirmation.
- [ ] Se déconnecter, **Gestion** → le dépôt d'Alpha Motors apparaît dans le suivi.
- [ ] **Bureau** → tableau du marché avec ses graphiques.
- [ ] Sur téléphone : la page de présentation et la connexion s'affichent correctement.

## 5. Partager

Message possible :

> Voici la démonstration de l'Observatoire GIPAME : <adresse>
> Toutes les données sont fictives. Sur la page de connexion, choisissez un profil (Membre, Gestion, Bureau…)
> pour entrer directement. Essayez de déclarer les ventes d'octobre avec le profil « Membre ».
> Vos remarques m'intéressent : ce qui est clair, ce qui ne l'est pas, ce qui manque.

## 6. Fiabilité : les dispositions pratiques

- **Mise en veille (offre gratuite de Render).** Après 15 minutes sans visite, la première page met 30 à 60 secondes à
  s'afficher. Pendant la période d'essai, passez le service en **Starter** (≈ 7 $/mois, Settings → Instance type),
  ou créez une sonde gratuite (UptimeRobot) qui appelle `https://<adresse>/sante/` toutes les 5 minutes.
- **Remise à zéro de la démonstration** (après une séance d'essais, ou chaque semaine) : Neon → Branches → `demo` →
  **Reset from parent**. Rien à changer chez Render.
- **Démo toujours « à jour »** : le jeu fictif est daté au moment du `seed_demo` (le mois à déclarer est le mois
  précédent). Au bout d'un mois ou deux, recréer un projet Neon et refaire les étapes 2 et 3 (`GIPAME_DB_URL` à
  mettre à jour chez Render).
- **Fichiers Excel.** Les fichiers produits ont désormais la même structure interne que ceux qu'écrit Excel (déclaration
  XML sur chaque partie, ordre du paquet). Un fichier téléchargé s'ouvre toujours en **Mode protégé** : c'est normal,
  « Activer la modification » suffit. **Si l'ouverture échoue encore** sur un poste : clic droit sur le fichier →
  Propriétés → **Débloquer**, puis le rouvrir. Si cela le règle, c'est le mode protégé de ce poste qui est en cause
  (pas le fichier) ; envoyez-moi le fichier et le message exact, avec la version d'Excel (Fichier → Compte).
- **Secrets.** L'adresse propriétaire ne va jamais chez Render ni sur GitHub ; seule l'adresse `gipame_app` y figure.
  `GIPAME_CLE_GABARIT` ne se change pas une fois des gabarits distribués.
- **Journaux.** Render → Logs : on y voit les erreurs éventuelles (jamais de quantité) et les courriels de démonstration.
- **Mises à jour.** Chaque `git push` sur `main` redéploie automatiquement la démonstration (2 à 4 minutes).

## 7. Leçons de la première mise en ligne (17/11/2026)

- **Neon n'a pas de superutilisateur** : `seed_demo` (calcul des publications) exige le droit temporaire
  `GRANT gipame_calcul TO neondb_owner` … `REVOKE` (intégré à l'étape 2 ; `seed_demo` s'arrête proprement sinon).
- **La branche principale de Neon s'appelle `production`** ; à la création de la branche `demo`, régler
  **Auto-delete : Never** (proposé par défaut : « After 1 day »).
- **`manage.py shell` lisant un texte collé** n'exécute pas une boucle sans ligne vide finale : pour un script,
  l'écrire dans un fichier de `D:\GIPAME\` et lancer `python manage.py shell -c "exec(open('D:/GIPAME/x.py', encoding='utf-8-sig').read())"`.
- **Chemin Windows avec apostrophe** (`C:\Users\N'…`) : ne jamais y placer un fichier appelé depuis Python.
- **Secrets à l'écran** : les mots de passe de la démonstration ont été affichés pendant l'installation et n'ont pas été
  changés (choix assumé : données fictives). Ne pas réutiliser ce projet Neon ni ces adresses pour la version réelle.

## 8. Mise à jour du 20/11/2026 : la Roue de Secours (assistant d'aide)

1. **Migration sur la base de démonstration** (une table nouvelle, isolée). Elle se lance depuis votre poste avec
   l'adresse PROPRIÉTAIRE de la branche `demo`, qui ne doit jamais être enregistrée sur Render ni sur GitHub :
   ```
   $env:GIPAME_DB_URL = "<adresse propriétaire de la branche demo>"
   python manage.py migrate
   Remove-Item Env:GIPAME_DB_URL
   ```
2. `git push`. Render redéploie seul et applique le nouveau démarrage (`gthread`). Si Render signale de nouvelles
   variables (`GIPAME_ROUE_CLE_API`, `GIPAME_ROUE_MODELE`), on peut les laisser vides.
3. **Sans clé**, la Roue répond en mode simplifié (extraits des fiches). **Avec une clé** (démonstration seulement,
   données fictives) : Render → Environment → `GIPAME_ROUE_CLE_API`, puis redéploiement. Essai préalable depuis le
   poste : `python manage.py roue_essai "Comment déclarer ?"`.
4. Vérifier : connexion avec un profil d'essai, bouton « Besoin d'aide ? » en bas à droite, une question, une réponse.

Pour tout le reste, voir `ROUE_DE_SECOURS.md`.

