"""Rapport de contrôle lisible : traduit chaque problème du dépôt (codes internes de §18.3 du
document de passation) en trois éléments pour un non-spécialiste : QUOI (titre), OÙ (onglet, ligne),
COMMENT CORRIGER (conseil). Le message détaillé produit par le dépôt reste affiché tel quel.

Aucun code technique n'est montré au membre ; le code interne ne sert qu'à choisir le conseil.
"""
from dataclasses import dataclass

from django.utils.text import capfirst

CONSEILS = {
    # ERREURS (bloquantes) ----------------------------------------------------------------------
    "FICHIER": ("Fichier illisible", "Enregistrez votre déclaration au format Excel (.xlsx), sans macro ni lien externe, puis déposez-la à nouveau."),
    "STRUCTURE": ("Le fichier ne correspond pas au gabarit", "Repartez du gabarit téléchargé à l'étape 1 ; ne renommez pas et ne supprimez pas d'onglet."),
    "VERSION_GABARIT": ("Gabarit trop ancien", "Téléchargez le gabarit du mois (étape 1), recopiez vos quantités dedans, puis déposez-le."),
    "SIGNATURE": ("Fichier modifié ou non reconnu", "Les cellules grises ont été modifiées, ou le fichier ne vient pas du portail : repartez du gabarit téléchargé ici."),
    "COMPTE": ("Ce fichier n'a pas été généré pour votre compte", "Téléchargez le gabarit depuis votre propre session (étape 1) et remplissez celui-là."),
    "MOIS_FUTUR": ("Mois non encore ouvert", "Vous ne pouvez déclarer qu'un mois écoulé : téléchargez le gabarit du bon mois."),
    "GABARIT_PERIME": ("Gabarit déjà utilisé", "Une déclaration plus récente existe pour ce mois : téléchargez un nouveau gabarit, il sera pré-rempli avec vos derniers chiffres."),
    "DOUBLON": ("Produit en double", "Un même produit apparaît deux fois : repartez du gabarit téléchargé, sans copier-coller de lignes."),
    "QUANTITE": ("Quantité invalide", "Saisissez un nombre entier positif (0 si aucune vente), sans décimale, sans signe ni texte."),
    "LIGNE_AJOUTEE": ("Ligne ajoutée dans l'onglet DECLARATION", "N'ajoutez pas de ligne ici : pour un nouveau produit, utilisez l'onglet AJOUTS ou la page « Mes produits »."),
    "LIGNE_MANQUANTE": ("Ligne supprimée dans l'onglet DECLARATION", "Ne supprimez aucune ligne : laissez la quantité à 0 pour un produit non vendu."),
    "PRODUIT_RETIRE": ("Produit retiré du catalogue", "Ce produit n'est plus déclarable : mettez sa quantité à 0, ou téléchargez un gabarit à jour."),
    "REPONSE": ("Réponse attendue : OUI ou NON", "En haut de l'onglet DECLARATION, choisissez OUI ou NON dans la liste déroulante."),
    "ZERO_NON_CONFIRME": ("Toutes les quantités sont à zéro", "Si vous n'avez vendu aucun véhicule neuf ce mois-ci, répondez OUI à « Aucune vente ce mois-ci ? » ; sinon renseignez vos quantités."),
    "INCOHERENCE": ("Réponses contradictoires", "« Aucune vente ce mois-ci » est à OUI alors que des quantités sont renseignées : corrigez l'un ou l'autre."),
    "MOTIF_REQUIS": ("Motif de correction manquant", "Indiquez en une phrase pourquoi vous corrigez votre déclaration (ci-dessous sur cette page, ou en cellule G4 du fichier)."),
    "AUCUNE_MODIFICATION": ("Aucune différence avec la déclaration déjà soumise", "Modifiez au moins une quantité, ou laissez la déclaration en l'état : elle est déjà enregistrée."),
    "TROP_D_AJOUTS": ("Trop de nouveaux produits dans un seul fichier", "Proposez les produits restants dans un second dépôt, ou depuis la page « Mes produits »."),
    "AJOUT_MARQUE": ("Marque non reconnue (onglet AJOUTS)", "Choisissez la marque dans la liste déroulante : seules vos marques sont proposées."),
    "AJOUT_INCOMPLET": ("Nouveau produit incomplet (onglet AJOUTS)", "Renseignez au minimum le modèle et la version / finition."),
    "AJOUT_ENERGIE": ("Énergie manquante (onglet AJOUTS)", "Choisissez l'énergie dans la liste déroulante."),
    "AJOUT_BOITE": ("Boîte non reconnue (onglet AJOUTS)", "Choisissez la boîte dans la liste déroulante, ou laissez la case vide."),
    "AJOUT_NOMBRE": ("Valeur non numérique (onglet AJOUTS)", "Cylindrée, puissance, charge utile, PTAC et places doivent être des nombres entiers."),
    "AJOUT_QUANTITE": ("Quantité invalide (onglet AJOUTS)", "Saisissez un nombre entier positif pour la quantité vendue ce mois."),
    "AJOUT_DOUBLON": ("Nouveau produit saisi deux fois", "Gardez une seule ligne par nouveau produit dans l'onglet AJOUTS."),
    "AJOUT_EXISTE_DEJA": ("Ce produit existe déjà au catalogue", "Renseignez sa quantité dans l'onglet DECLARATION ; s'il n'y figure pas, signalez-le au GIPAME."),
    "SOUMISSION": ("Soumission refusée", "Votre brouillon est enregistré ; corrigez le point indiqué puis soumettez à nouveau."),
    "BASE": ("Enregistrement impossible pour le moment", "Réessayez dans un instant ; si le problème persiste, contactez le GIPAME."),
    # ALERTES (le fichier est accepté) ---------------------------------------------------------
    "NOMBRE_EN_TEXTE": ("Nombre saisi comme texte", "Accepté tel quel. Pour éviter l'alerte, saisissez directement le chiffre, sans guillemet ni espace."),
    "CATALOGUE_PLUS_RECENT": ("Catalogue mis à jour depuis votre téléchargement", "Le produit ajouté est compté à 0 ce mois-ci. Si vous en avez vendu, téléchargez un gabarit à jour et corrigez."),
    "VARIATION": ("Variation forte par rapport au mois précédent", "Vérifiez la quantité. Si elle est exacte, un mot d'explication ci-dessous suffit."),
    "IDENTIQUE": ("Quantités identiques au mois précédent", "Assurez-vous qu'il ne s'agit pas d'une copie du mois dernier. Si c'est exact, confirmez-le ci-dessous."),
    "BAISSE_TOTALE": ("Total en forte baisse", "Si c'est exact, un mot d'explication ci-dessous aidera le GIPAME à interpréter."),
    "HAUSSE_TOTALE": ("Total en forte hausse", "Si c'est exact, un mot d'explication ci-dessous aidera le GIPAME à interpréter."),
    "AJOUT_PROCHE": ("Produit proche d'un produit existant", "Rien à faire : le GIPAME vérifiera qu'il ne s'agit pas d'un doublon avant de l'intégrer au catalogue."),
    "ATTESTATION_MANQUANTE": ("Attestation non cochée dans le fichier", "Cochez l'attestation ci-dessous pour soumettre votre déclaration."),
    "TRACE": ("Trace du dépôt non enregistrée", "Votre déclaration est bien enregistrée ; signalez ce message au GIPAME."),
}
ALERTES_A_COMMENTER = {"VARIATION", "IDENTIQUE", "BAISSE_TOTALE", "HAUSSE_TOTALE"}
ONGLETS = {"DECLARATION": "onglet DECLARATION", "AJOUTS": "onglet AJOUTS"}


@dataclass
class Ligne:
    gravite: str      # ERREUR | ALERTE
    quoi: str
    ou: str           # « onglet DECLARATION, ligne 12 » ou ""
    detail: str       # message produit par le dépôt
    comment: str
    code: str         # interne, non affiché


def traduire(probleme):
    """Probleme (dataclass du dépôt ou dict JSON de DepotFichier.rapport) → Ligne."""
    p = probleme if isinstance(probleme, dict) else probleme.__dict__
    code, gravite = p.get("code", ""), p.get("gravite", "ALERTE")
    quoi, comment = CONSEILS.get(code, ("Point à vérifier" if gravite == "ALERTE" else "Point à corriger",
                                        "Corrigez le point indiqué puis déposez à nouveau le fichier."))
    feuille, ligne = p.get("feuille") or "", p.get("ligne")
    ou = ONGLETS.get(feuille, feuille)
    if ou and ligne:
        ou = f"{ou}, ligne {ligne}"
    return Ligne(gravite=gravite, quoi=quoi, ou=capfirst(ou) if ou else "", detail=p.get("message", ""),
                 comment=comment, code=code)


def traduire_tout(problemes):
    lignes = [traduire(p) for p in problemes]
    erreurs = [x for x in lignes if x.gravite == "ERREUR"]
    alertes = [x for x in lignes if x.gravite == "ALERTE"]
    return erreurs, alertes


def alertes_a_commenter(alertes):
    return [a for a in alertes if a.code in ALERTES_A_COMMENTER]
