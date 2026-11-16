"""Données de référence initiales : vocabulaires, postes de gouvernance, paramètres,
première segmentation (reprise de la structure du fichier 2024, définitions à rédiger)."""
from django.db import migrations

ORIGINES = [("JAPONAISE", "Japonaise"), ("EUROPEENNE", "Européenne"), ("COREENNE", "Coréenne"),
            ("CHINOISE", "Chinoise"), ("AUTRES", "Autres")]
ENERGIES = [("ESSENCE", "Essence"), ("DIESEL", "Diesel"), ("HYBRIDE", "Hybride"),
            ("HYBRIDE_RECHARGEABLE", "Hybride rechargeable"), ("ELECTRIQUE", "Électrique"),
            ("GAZ", "Gaz"), ("AUTRE", "Autre")]
BOITES = [("BVM", "Boîte manuelle"), ("BVA", "Boîte automatique"), ("AUTRE", "Autre")]
POSTES = [("PRESIDENT", "Président"), ("VICE_PRESIDENT", "Vice-président"),
          ("DELEGUE_GENERAL", "Délégué général")]

# (clé, valeur, catégorie, description)
PARAMETRES = [
    ("seuil_approbations_acces", "2", "SECURITE", "Nombre de postes (sur 3) qui doivent approuver un accès exceptionnel."),
    ("confidentialite_min_contributeurs", "3", "SECURITE", "Nombre minimal de contributeurs indépendants par cellule publiée."),
    ("confidentialite_dominance_pct", "80", "SECURITE", "Un contributeur au-dessus de ce % d'une cellule la rend confidentielle."),
    ("jours_grace_depot", "10", "OPERATIONNEL", "Jours après la fin du mois avant d'alerter les membres n'ayant pas déposé."),
    ("mois_inactivite_masquage", "12", "OPERATIONNEL", "Mois sans vente avant de proposer de masquer un produit."),
    ("gabarit_toutes_lignes", "non", "OPERATIONNEL", "oui = chaque gabarit contient tous les produits ; non = seulement ceux des marques du membre."),
    ("couverture_min_publication_pct", "80", "OPERATIONNEL", "Couverture minimale pour qu'une publication soit définitive."),
    ("conservation_annees", "5", "OPERATIONNEL", "Durée de conservation des données individuelles (à confirmer, voir convention)."),
]

# catégorie -> (libellé, [(code segment, libellé)])  ; définitions métier à rédiger avec le GIPAME
SEGMENTATION = [
    ("VP", "Véhicules particuliers", [("AB", "Segment A/B"), ("M1", "Segment M1"), ("M2", "Segment M2"), ("H", "Segment H")]),
    ("4X4", "4x4 et SUV", [("SUV", "SUV"), ("4X4_MEDIUM", "4x4 medium"), ("4X4_LARGE", "4x4 large")]),
    ("PICKUP", "Pick-up", [("PU_4X2", "Pick-up 4x2"), ("PU_4X4", "Pick-up 4x4"), ("PU_HD", "Pick-up heavy duty")]),
    ("VAN", "Vans", [("VAN", "Van")]),
    ("BUS", "Bus et cars", [("BUS_MOINS_22", "Moins de 22 places"), ("BUS_23_34", "23 à 34 places"), ("BUS_PLUS_34", "Plus de 34 places")]),
    ("CAMION_LEGER", "Camions légers 3-6 t", [("CAMION_3_6T", "Camions 3 à 6 t")]),
    ("POIDS_LOURD", "Poids lourds > 6 t", [("CAMION_6_15T", "Camions 6 à 15 t"), ("TRACTEUR_PLUS_15T", "Tracteurs > 15 t"), ("PORTEUR_PLUS_15T", "Porteurs > 15 t")]),
]


def charger(apps, schema_editor):
    for modele, valeurs in (("Origine", ORIGINES), ("Energie", ENERGIES), ("Boite", BOITES)):
        M = apps.get_model("collecte", modele)
        for ordre, (code, libelle) in enumerate(valeurs, 1):
            M.objects.get_or_create(code=code, defaults={"libelle": libelle, "ordre": ordre})
    Poste = apps.get_model("collecte", "Poste")
    for code, libelle in POSTES:
        Poste.objects.get_or_create(code=code, defaults={"libelle": libelle})
    Param = apps.get_model("collecte", "ParametreSysteme")
    for cle, valeur, categorie, description in PARAMETRES:
        Param.objects.get_or_create(cle=cle, defaults={"valeur": valeur, "categorie": categorie, "description": description})
    Segmentation = apps.get_model("collecte", "Segmentation")
    Categorie = apps.get_model("collecte", "Categorie")
    Segment = apps.get_model("collecte", "Segment")
    seg, _ = Segmentation.objects.get_or_create(
        code="GIPAME-V1",
        defaults={"libelle": "Grille GIPAME (reprise du fichier 2024)", "statut": "COURANTE",
                  "description": "Reprise de la structure du fichier de collecte 2024. Les définitions des segments "
                                 "(A/B, M1, M2, H...) reposent sur la connaissance métier et restent à rédiger."})
    for o, (code, libelle, segments) in enumerate(SEGMENTATION, 1):
        cat, _ = Categorie.objects.get_or_create(segmentation=seg, code=code, defaults={"libelle": libelle, "ordre": o})
        for so, (scode, slibelle) in enumerate(segments, 1):
            Segment.objects.get_or_create(categorie=cat, code=scode, defaults={"libelle": slibelle, "ordre": so})


class Migration(migrations.Migration):
    dependencies = [("collecte", "0002_securite")]
    operations = [migrations.RunPython(charger, migrations.RunPython.noop)]
