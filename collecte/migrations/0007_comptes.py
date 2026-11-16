"""Gestion des comptes depuis le portail : fonctions SQL à privilège défini, annuaire enrichi.
SQL : ../sql/0007_comptes.sql."""
from pathlib import Path

from django.db import migrations, models

SQL = Path(__file__).resolve().parent.parent / "sql" / "0007_comptes.sql"


def appliquer(apps, schema_editor):
    texte = "\n" + SQL.read_text(encoding="utf-8")
    for bloc in texte.split("\n--@@\n"):
        bloc = bloc.strip()
        if bloc and not all(ligne.strip().startswith("--") or not ligne.strip() for ligne in bloc.splitlines()):
            schema_editor.execute(bloc, params=None)


def annuler(apps, schema_editor):
    for f in ("gipame_compte_creer(text, text, text, text, bigint, text)", "gipame_compte_etat(bigint, boolean, text)",
              "gipame_compte_modifier(bigint, text, text, text)", "gipame_compte_pour_activation(bigint)",
              "gipame_exiger_administrateur()"):
        schema_editor.execute(f"DROP FUNCTION IF EXISTS {f}")
    schema_editor.execute("DROP VIEW IF EXISTS collecte_v_profil_utilisateur")
    schema_editor.execute("CREATE VIEW collecte_v_profil_utilisateur AS SELECT id, username, first_name, last_name, email, "
                          "role_metier, membre_id, is_active FROM collecte_utilisateur")
    schema_editor.execute("GRANT SELECT ON collecte_v_profil_utilisateur TO gipame_gestion, gipame_bureau, gipame_membre")


class Migration(migrations.Migration):
    dependencies = [("collecte", "0006_portail")]
    operations = [
        migrations.RunPython(appliquer, annuler),
        migrations.AddField(model_name="profilutilisateur", name="compte_active", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="profilutilisateur", name="derniere_connexion", field=models.DateTimeField(null=True)),
        migrations.AddField(model_name="profilutilisateur", name="cree_le", field=models.DateTimeField(null=True)),
    ]
