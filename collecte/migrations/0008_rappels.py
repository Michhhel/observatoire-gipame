"""Rappels de dépôt : destinataires calculés par la base (la gestion ne lit pas la table des comptes).
SQL : ../sql/0008_rappels.sql."""
from pathlib import Path

from django.db import migrations

SQL = Path(__file__).resolve().parent.parent / "sql" / "0008_rappels.sql"


def appliquer(apps, schema_editor):
    texte = "\n" + SQL.read_text(encoding="utf-8")
    for bloc in texte.split("\n--@@\n"):
        bloc = bloc.strip()
        if bloc and not all(ligne.strip().startswith("--") or not ligne.strip() for ligne in bloc.splitlines()):
            schema_editor.execute(bloc, params=None)


def annuler(apps, schema_editor):
    schema_editor.execute("DROP FUNCTION IF EXISTS gipame_destinataires_rappel(date)")


class Migration(migrations.Migration):
    dependencies = [("collecte", "0007_comptes")]
    operations = [migrations.RunPython(appliquer, annuler)]
