from django.db import migrations, models

ROLES_PORTAIL = "gipame_membre, gipame_gestion, gipame_bureau"


class Migration(migrations.Migration):
    initial = True
    dependencies = [("collecte", "0008_rappels")]

    operations = [
        migrations.CreateModel(
            name="Avis",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("cree_le", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("role", models.CharField(max_length=12)),
                ("page", models.CharField(blank=True, max_length=80)),
                ("question", models.TextField()),
                ("reponse", models.TextField(blank=True)),
                ("sources", models.CharField(blank=True, max_length=400)),
                ("mode", models.CharField(blank=True, max_length=12)),
                ("note", models.SmallIntegerField(choices=[(1, "Utile"), (-1, "À revoir"), (0, "Question sans réponse")])),
                ("commentaire", models.TextField(blank=True)),
            ],
            options={"verbose_name": "avis sur une réponse", "verbose_name_plural": "avis sur les réponses",
                     "constraints": [models.CheckConstraint(condition=models.Q(note__in=[-1, 0, 1]), name="roue_avis_note_ok")]},
        ),
        # Droits : AJOUT seulement pour les rôles du portail (ni lecture : les avis d'un membre ne doivent être lus ni
        # par la gestion ni par un autre membre). Aucune table métier n'est touchée.
        migrations.RunSQL(
            f"REVOKE ALL ON roue_de_secours_avis FROM PUBLIC;"
            f"GRANT INSERT ON roue_de_secours_avis TO {ROLES_PORTAIL};"
            f"GRANT USAGE ON SEQUENCE roue_de_secours_avis_id_seq TO {ROLES_PORTAIL};",
            f"REVOKE ALL ON roue_de_secours_avis FROM {ROLES_PORTAIL};"
            f"REVOKE ALL ON SEQUENCE roue_de_secours_avis_id_seq FROM {ROLES_PORTAIL};"),
    ]
