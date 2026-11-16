from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = ("Donne à gipame_app les droits sur les tables TECHNIQUES de Django (comptes, sessions, admin), "
            "jamais sur les tables métier. À lancer avec le compte propriétaire après `migrate` (idempotent).")

    TABLES = ["collecte_utilisateur", "collecte_utilisateur_groups", "collecte_utilisateur_user_permissions", "auth_group",
              "auth_permission", "auth_group_permissions", "django_content_type", "django_session", "django_admin_log",
              "portail_tentativeconnexion"]
    SANS_SUPPRESSION = ["collecte_utilisateur", "portail_tentativeconnexion"]  # jamais de DELETE (trigger + droits)
    LECTURE_SEULE = ["django_migrations"]  # le serveur vérifie l'état des migrations au démarrage

    def handle(self, *args, **options):
        with connection.cursor() as cur:
            for table in self.TABLES:
                cur.execute("SELECT to_regclass(%s)", [table])
                if cur.fetchone()[0] is None:
                    self.stdout.write(f"  absente (ignorée) : {table}")
                    continue
                cur.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO gipame_app')
                if table in self.SANS_SUPPRESSION:
                    cur.execute(f'REVOKE DELETE ON "{table}" FROM gipame_app')
                cur.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = %s AND column_name = 'id'", [table])
                sequence = None
                if cur.fetchone()[0]:
                    cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", [table])
                    sequence = cur.fetchone()[0]
                if sequence:
                    cur.execute(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO gipame_app")
                self.stdout.write(self.style.SUCCESS(f"  droits accordés : {table}"))
            for table in self.LECTURE_SEULE:
                cur.execute(f'GRANT SELECT ON "{table}" TO gipame_app')
                self.stdout.write(self.style.SUCCESS(f"  lecture seule : {table}"))
