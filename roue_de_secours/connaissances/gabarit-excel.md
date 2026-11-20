---
id: gabarit-excel
titre: Remplir le gabarit Excel
roles: MEMBRE
lien: /declarer/
questions: Comment remplir le fichier ? | Où mettre les quantités ? | Que signifient les cellules grises ? | Que mettre si je n'ai pas vendu un produit ? | Que veut dire « Déclaration complète et exacte » ? | Le fichier est en lecture seule | Puis-je modifier les onglets ? | Quelle taille maximale ?
toujours: non
mise_a_jour: 2026-11-20
---
## Le contenu du fichier
Le gabarit est préparé pour votre société et pour un mois précis. Il a trois onglets visibles :
- **DECLARATION** : une ligne par produit ; vous remplissez la colonne jaune « QUANTITÉ VENDUE » (et, si besoin, « Commentaire ») ;
- **AJOUTS** : pour déclarer un produit qui ne figure pas dans la liste ;
- **LISEZ-MOI** : le mode d'emploi.
Les cellules grises (code produit, marque, désignation…) sont verrouillées : ne les modifiez pas.

## Saisir les quantités
- Un nombre entier, sans décimale, sans signe, sans texte : le nombre de véhicules neufs vendus dans le mois.
- 0 pour un produit non vendu : aucune case ne doit rester vide.
- Au plus {{import_quantite_max}} par ligne.
- Le mois précédent est rappelé pour vous aider ; les cases orange signalent une forte variation : ajoutez un commentaire.

## Les deux questions en haut de l'onglet DECLARATION
- « Aucune vente ce mois-ci ? » : OUI seulement si toutes les quantités sont à 0, sinon NON.
- « Déclaration complète et exacte ? » : répondez OUI quand vous avez terminé.
Choisissez OUI ou NON dans la liste déroulante de la cellule.

## À ne pas faire
Renommer les onglets, supprimer ou ajouter des lignes dans DECLARATION, modifier la colonne « Code produit »,
copier les cellules dans un autre classeur, utiliser le fichier d'un autre mois ou d'une autre société, ajouter des
macros. Enregistrez au format .xlsx (pas .xls, pas .csv) ; taille maximale : {{import_taille_max_ko}} Ko.

## Mode protégé d'Excel
À l'ouverture, Excel affiche un bandeau jaune « Mode protégé », comme pour tout fichier téléchargé : cliquez sur
« Activer la modification ». Si Excel refuse d'ouvrir le fichier : enregistrez-le d'abord, puis clic droit sur le
fichier → Propriétés → cochez « Débloquer » → OK, et rouvrez-le.
