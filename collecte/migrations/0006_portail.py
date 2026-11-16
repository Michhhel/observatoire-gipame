"""Portail web : commentaire du membre sur les alertes (saisi dans la page), comptes non supprimables.
SQL : ../sql/0006_portail.sql."""
from pathlib import Path

from django.db import migrations, models

SQL = Path(__file__).resolve().parent.parent / "sql" / "0006_portail.sql"


def appliquer(apps, schema_editor):
    texte = "\n" + SQL.read_text(encoding="utf-8")
    for bloc in texte.split("\n--@@\n"):
        bloc = bloc.strip()
        if bloc and not all(ligne.strip().startswith("--") or not ligne.strip() for ligne in bloc.splitlines()):
            schema_editor.execute(bloc, params=None)


def annuler(apps, schema_editor):
    schema_editor.execute("DROP VIEW IF EXISTS collecte_v_profil_utilisateur")
    schema_editor.execute("DROP TRIGGER IF EXISTS trg_pas_de_suppression ON collecte_utilisateur")
    schema_editor.execute("REVOKE UPDATE (commentaire_portail) ON collecte_declaration FROM gipame_membre")


class Migration(migrations.Migration):
    dependencies = [("collecte", "0005_excel")]
    operations = [
        migrations.AddField(
            model_name="declaration",
            name="commentaire_portail",
            field=models.TextField(blank=True, default="",
                                   help_text="Explications données par le membre sur les alertes, depuis le portail."),
        ),
        migrations.RunPython(appliquer, annuler),
        migrations.CreateModel(
            name="ProfilUtilisateur",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(max_length=150)),
                ("first_name", models.CharField(blank=True, max_length=150)),
                ("last_name", models.CharField(blank=True, max_length=150)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("role_metier", models.CharField(max_length=10)),
                ("is_active", models.BooleanField()),
                ("membre", models.ForeignKey(null=True, on_delete=models.deletion.DO_NOTHING, related_name="+", to="collecte.membre")),
            ],
            options={"db_table": "collecte_v_profil_utilisateur", "managed": False},
        ),
    ]
