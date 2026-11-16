"""Rôles, triggers, sécurité par ligne (RLS), vues et fonctions : voir ../sql/0002_securite.sql.

Le SQL est volontairement dans un fichier à part, lisible et relisible par un DBA.
Cette migration n'est pas réversible (retour en arrière = restauration d'une sauvegarde).
"""
from pathlib import Path

from django.db import migrations

SQL = Path(__file__).resolve().parent.parent / "sql" / "0002_securite.sql"


def appliquer(apps, schema_editor):
    texte = "\n" + SQL.read_text(encoding="utf-8")
    for bloc in texte.split("\n--@@\n"):
        bloc = bloc.strip()
        if bloc and not all(ligne.strip().startswith("--") or not ligne.strip() for ligne in bloc.splitlines()):
            schema_editor.execute(bloc, params=None)


class Migration(migrations.Migration):
    dependencies = [("collecte", "0001_initial")]
    operations = [migrations.RunPython(appliquer, migrations.RunPython.noop)]
