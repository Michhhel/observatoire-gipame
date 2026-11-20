# Base de connaissances de la Roue de Secours

Chaque fichier `.md` de ce dossier est une **fiche**. La Roue de Secours ne répond qu'à partir de ces fiches (et de la
situation de l'utilisateur : statut de sa déclaration, jamais une quantité). Corriger une fiche corrige les réponses.

Ce fichier (LISEZ-MOI.md) n'est pas une fiche : il est ignoré.

## Format d'une fiche

```
---
id: declarer-etapes                 # unique, = nom du fichier sans .md
titre: Déclarer ses ventes du mois  # affiché comme source sous la réponse
roles: MEMBRE                       # MEMBRE, GESTION, BUREAU, TECHNIQUE ou TOUS (plusieurs : séparés par des virgules)
lien: /declarer/                    # page du portail à proposer (facultatif, doit exister)
questions: Comment déclarer ? | Par où commencer ?   # façons dont les gens posent la question (aide la recherche)
toujours: non                       # oui = jointe à chaque question (plan du site, glossaire) ; à réserver aux fiches courtes
mise_a_jour: 2026-11-20
---
Texte d'introduction (facultatif).

## Une section = un passage retrouvable
Texte court, concret, à la 2e personne (vous). Les liens vers le portail s'écrivent [Déclarer](/declarer/).
```

Valeurs dynamiques (remplacées par les paramètres de la base au moment de la question) :
`{{jours_grace_depot}}`, `{{definition_vente}}`, `{{contact}}`, `{{import_quantite_max}}`, `{{import_max_ajouts}}`,
`{{import_taille_max_ko}}`, `{{import_variation_alerte_pct}}`, `{{import_variation_min_unites}}`.

## Règles de rédaction

- **Jamais de donnée réelle** : aucun nom de membre, aucune marque réelle, aucun chiffre de vente, aucune adresse e-mail.
- Une fiche = un sujet ; une section = une question précise. Les sections courtes (5 à 10 lignes) sont mieux retrouvées.
- Écrire les mots que les utilisateurs emploient (« fichier Excel » autant que « gabarit »), et les ajouter à `questions:`.
- Après toute modification : `python manage.py roue_verifier` (contrôle des fiches + jeu d'évaluation), puis les tests.
- Une réponse fausse signalée ? Corriger la fiche, puis ajouter la question au jeu d'évaluation
  (`roue_de_secours/evaluation.py`) pour qu'elle ne revienne jamais.
