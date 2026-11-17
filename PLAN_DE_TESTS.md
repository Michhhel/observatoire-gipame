# Plan de tests de l'Observatoire GIPAME

Trois niveaux, du plus automatique au plus humain. Les deux premiers se relancent en quelques minutes après chaque
modification ; le troisième se fait sur la démonstration en ligne, avec de vraies personnes.

| Niveau | Quoi | Combien de temps | Qui |
|---|---|---|---|
| 1. Tests automatiques | 186 tests : règles de sécurité en base, fichiers Excel, parcours du portail, non-fuite | ≈ 2 min | `python manage.py test` |
| 2. Balayage navigateur | toutes les pages × 6 profils × ordinateur/téléphone × clair/sombre (≈ 150 pages) | ≈ 10 min | `python scripts/balayage.py` |
| 3. Tests profonds | scénarios réels, cas limites, avis des utilisateurs | 1 à 2 h par testeur | Michel et les testeurs |

---

## 1. Tests automatiques

```powershell
D:\GIPAME\venv_gipame\Scripts\Activate.ps1 ; cd D:\GIPAME\Application_GIPAME
python manage.py test
```
Attendu : `Ran 186 tests … OK`. Un seul échec = on ne met rien en ligne avant de comprendre.

Ce qu'ils couvrent : contraintes et droits en base (RLS, rôles, triggers, comptes non supprimables), seuils de
confidentialité, gabarit (contenu, signature, structure du fichier), dépôt (erreurs, alertes, fichiers piégés,
corrections), exports, reprise d'historique, chaque écran du portail par rôle, non-fuite (un membre ne voit jamais un
autre membre ; la gestion ne voit aucune quantité individuelle ; le bureau ne voit ni le nombre de contributeurs ni le
motif de masquage), fichiers téléchargés intacts octet par octet, mode démonstration.

## 2. Balayage navigateur (toutes les variations)

```powershell
pip install -r requirements-dev.txt ; playwright install chromium     # une fois
python scripts/balayage.py                                           # la démonstration en ligne
python scripts/balayage.py --adresse http://127.0.0.1:8000           # le serveur local (jeu de démonstration)
python scripts/balayage.py --rapide                                  # ordinateur + clair seulement
```
Le script se connecte avec chaque profil d'essai, ouvre toutes les pages du menu et vérifie : réponse sans erreur,
aucune erreur JavaScript, **aucun débordement horizontal** (téléphone), présence d'un titre, images avec texte
alternatif, et **non-fuite** (aucun nom d'un autre membre sur les pages d'un membre). Il ne dépose ni ne modifie rien.
Résultat : `balayage\RAPPORT.md` et une capture par page (dossier ignoré par Git).

Premier passage (17/11/2026) : 152 pages, 14 débordements sur téléphone (Déclarer, Historique, Mes produits, Comptes),
corrigés ; second passage : **0 problème**.

## 3. Tests profonds sur la démonstration

Adresse : https://observatoire-gipame-demo.onrender.com — profils d'essai sur la page de connexion
(mot de passe `demo-2026`). Remettre la démo à zéro avant une séance : Neon → Branches → `demo` → Reset from parent.

Pour chaque scénario : noter **OK / Problème**, et pour un problème : la page, ce qui était attendu, ce qui s'est
passé, une capture. Modèle de retour en fin de document.

### 3.1 Membre (Alpha Motors, puis Delta Véhicules)
| # | Scénario | Attendu |
|---|---|---|
| M1 | Déclarer octobre : télécharger, remplir quelques quantités, déposer, soumettre | fichier ouvert sans réparation ; rapport clair ; confirmation ; statut « Soumise » |
| M2 | Déposer un fichier avec erreurs (texte dans une quantité, nombre négatif, ligne supprimée) | dépôt refusé, chaque erreur expliquée avec la ligne et la façon de corriger |
| M3 | Déposer le gabarit d'un **autre mois** ou d'un **autre membre** | refus explicite |
| M4 | Déposer un fichier modifié à la main (onglet caché touché, code produit changé) | refus « fichier modifié » |
| M5 | Déposer un fichier qui n'est pas un Excel (PDF renommé en .xlsx, fichier vide, très gros fichier) | refus propre, sans erreur serveur |
| M6 | Tout à zéro sans cocher « aucune vente » | message demandant de confirmer l'absence de ventes |
| M7 | Forte variation par rapport au mois précédent | alerte à commenter, non bloquante |
| M8 | Corriger un mois déjà soumis (septembre) | motif demandé ; nouvelle version ; l'historique garde l'ancienne |
| M9 | Proposer un nouveau produit dans l'onglet AJOUTS | proposition visible dans « Mes produits », en attente de la gestion |
| M10 | Mon année, Le marché, export Excel de mon année | chiffres cohérents avec mes dépôts ; cellules « c » expliquées |
| M11 | Essayer d'ouvrir une page de la gestion ou du bureau en tapant l'adresse | accès refusé |
| M12 | Avec Beta Distribution : vérifier qu'aucun chiffre ni nom d'Alpha Motors n'apparaît nulle part | aucun |

### 3.2 Gestion
| # | Scénario | Attendu |
|---|---|---|
| G1 | Suivi des dépôts d'octobre après M1 | Alpha Motors « soumis » ; aucune quantité individuelle visible |
| G2 | Envoyer les rappels | message de succès ; en démo, le courriel s'écrit dans les journaux de Render |
| G3 | Valider, fusionner ou rejeter le produit proposé en M9 | le produit apparaît (ou non) dans le prochain gabarit du membre |
| G4 | Calculer la publication provisoire puis définitive d'octobre | couverture affichée, pas de chiffre par membre |
| G5 | Membres : créer un membre fictif, lui ajouter une marque | visible dans la liste ; son gabarit contient les produits de la marque |
| G6 | Demande d'accès exceptionnel aux données d'un membre | demande créée, en attente du bureau |

### 3.3 Bureau
| # | Scénario | Attendu |
|---|---|---|
| B1 | Tableau du marché | graphiques lisibles ; cellules masquées « c » sans motif ni nombre de contributeurs |
| B2 | Approuver la demande G6 avec deux postes (président puis vice-président) | lecture ouverte à la gestion seulement après le 2e accord |
| B3 | Journal des accès du mois | la lecture exceptionnelle et les rappels y figurent |

### 3.4 Administration
| # | Scénario | Attendu |
|---|---|---|
| A1 | Créer un compte membre, afficher son lien d'activation, l'ouvrir dans une fenêtre privée, choisir un mot de passe | connexion possible avec ce compte |
| A2 | Désactiver ce compte | il ne peut plus se connecter |
| A3 | Essayer de désactiver un compte de démonstration | refus expliqué (protection de la démo) |

### 3.5 Transversal
| # | Scénario | Attendu |
|---|---|---|
| T1 | Téléphone : toute la déclaration (M1) depuis un téléphone | possible de bout en bout |
| T2 | Mode clair / sombre de la page de présentation ; défilement | lisible dans les deux modes |
| T3 | Déconnexion | demande de confirmation ; « Rester connecté » annule |
| T4 | Session inactive 8 h, retour arrière après déconnexion | retour à la connexion, aucune donnée affichée |
| T5 | Connexion avec un mauvais mot de passe 5 fois | message clair, pas d'indication sur l'existence du compte |
| T6 | Lenteur : première visite après 20 minutes sans activité | 30 à 60 s (offre gratuite), ensuite rapide |
| T7 | Autres navigateurs : Edge, Chrome, Firefox, Safari (iPhone) | même rendu ; transitions de page absentes sur Firefox (normal) |
| T8 | Excel : ouvrir chaque fichier téléchargé (gabarit, mon année, exports gestion) sur plusieurs versions d'Excel, et dans LibreOffice | aucune réparation demandée |

### Modèle de retour pour les testeurs

> **Profil utilisé** : … **Appareil / navigateur** : …
> **Ce qui est clair** : …
> **Ce qui n'est pas clair ou m'a fait hésiter** : …
> **Problèmes** (page, ce que j'attendais, ce qui s'est passé, capture) : …
> **Ce qui manque** : …
