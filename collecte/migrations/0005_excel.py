"""Fichiers Excel : droits sur les dépôts, paramètres de contrôle des fichiers, fonction de lecture
des paramètres publics. SQL : ../sql/0005_excel.sql."""
from pathlib import Path

from django.db import migrations

SQL = Path(__file__).resolve().parent.parent / "sql" / "0005_excel.sql"

PARAMETRES = [  # clé, valeur, catégorie, description
    ("import_variation_alerte_pct", "50", "OPERATIONNEL", "Variation (en %) d'une ligne vs le mois précédent au-delà de laquelle on demande un commentaire."),
    ("import_variation_min_unites", "10", "OPERATIONNEL", "Nombre minimal d'unités (mois précédent ou courant) pour déclencher l'alerte de variation."),
    ("import_quantite_max", "20000", "OPERATIONNEL", "Quantité maximale plausible par ligne et par mois (au-delà : fichier refusé)."),
    ("import_max_ajouts", "20", "OPERATIONNEL", "Nombre maximal de nouveaux produits proposés par fichier."),
    ("import_taille_max_ko", "2048", "OPERATIONNEL", "Taille maximale d'un fichier Excel déposé (Ko)."),
    ("definition_vente", "Véhicules neufs facturés dans le mois (définition à confirmer par le GIPAME).", "OPERATIONNEL",
     "Texte affiché dans les gabarits : ce qu'on entend par « vente »."),
    ("contact_gipame", "À renseigner (adresse du secrétariat du GIPAME).", "OPERATIONNEL", "Contact affiché dans les gabarits."),
]


def appliquer(apps, schema_editor):
    texte = "\n" + SQL.read_text(encoding="utf-8")
    for bloc in texte.split("\n--@@\n"):
        bloc = bloc.strip()
        if bloc and not all(ligne.strip().startswith("--") or not ligne.strip() for ligne in bloc.splitlines()):
            schema_editor.execute(bloc, params=None)
    Param = apps.get_model("collecte", "ParametreSysteme")
    for cle, valeur, categorie, description in PARAMETRES:
        Param.objects.get_or_create(cle=cle, defaults={"valeur": valeur, "categorie": categorie, "description": description})


class Migration(migrations.Migration):
    dependencies = [("collecte", "0004_depotfichier")]
    operations = [migrations.RunPython(appliquer, migrations.RunPython.noop)]
