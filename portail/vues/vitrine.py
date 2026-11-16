"""Page d'accueil publique (avant connexion) : présentation de l'observatoire.

Règle : cette page ne lit AUCUNE donnée de la base. Les chiffres affichés sont des valeurs publiques
saisies ici à la main (aujourd'hui : valeurs d'illustration). Aucun chiffre de membre, aucun nombre de
contributeurs n'y apparaît. Le test « vitrine » vérifie qu'elle s'affiche sans une seule requête SQL.

Pour mettre à jour la page : modifier CHIFFRES, SEGMENTS et SERIE_MENSUELLE ci-dessous, puis passer
CHIFFRES_ILLUSTRATIFS à False quand ce sont des chiffres officiellement publiés par le GIPAME.
"""
from django.contrib.staticfiles import finders
from django.shortcuts import render

# Tant que True, une mention « valeurs d'illustration » accompagne les chiffres.
CHIFFRES_ILLUSTRATIFS = True

CHIFFRES = [
    {"valeur": "18 640", "libelle": "véhicules neufs vendus en 2025"},
    {"valeur": "+8,4 %", "libelle": "par rapport à 2024"},
    {"valeur": "6,2 %", "libelle": "de véhicules hybrides ou électriques"},
    {"valeur": "Le 20", "libelle": "de chaque mois, publication du mois précédent"},
]

# photo : fichier facultatif dans static/portail/vitrine/photos/ ; à défaut, un dessin au trait s'affiche.
SEGMENTS = [
    {"cle": "citadine", "nom": "Citadines et berlines", "part": 31,
     "texte": "Le cœur du marché des particuliers et des flottes d'entreprise."},
    {"cle": "suv", "nom": "SUV et 4x4", "part": 29,
     "texte": "La catégorie qui progresse le plus vite depuis trois ans."},
    {"cle": "pickup", "nom": "Pick-up", "part": 21,
     "texte": "Le véhicule de travail des chantiers, des plantations et de l'intérieur du pays."},
    {"cle": "utilitaire", "nom": "Utilitaires", "part": 11,
     "texte": "Fourgons et minibus pour la livraison et le transport de personnes."},
    {"cle": "camion", "nom": "Camions et bus", "part": 8,
     "texte": "Le transport de marchandises et le transport collectif."},
]

# 24 mois de ventes totales (illustration), du plus ancien au plus récent : nourrit la courbe d'ouverture.
SERIE_MENSUELLE = [1290, 1335, 1420, 1310, 1385, 1460, 1405, 1350, 1480, 1525, 1440, 1610,
                   1395, 1450, 1560, 1470, 1520, 1605, 1540, 1495, 1630, 1690, 1580, 1785]
MOIS_DEBUT = "janv. 2024"
MOIS_FIN = "déc. 2025"


def _photo(cle):
    for ext in ("webp", "jpg", "jpeg", "png"):
        chemin = f"portail/vitrine/photos/{cle}.{ext}"
        if finders.find(chemin):
            return chemin
    return None


def vitrine(request):
    segments = [dict(s, photo=_photo(s["cle"])) for s in SEGMENTS]
    return render(request, "portail/vitrine/accueil.html", {
        "chiffres": CHIFFRES,
        "illustratif": CHIFFRES_ILLUSTRATIFS,
        "segments": segments,
        "serie": {"valeurs": SERIE_MENSUELLE, "debut": MOIS_DEBUT, "fin": MOIS_FIN},
    })
