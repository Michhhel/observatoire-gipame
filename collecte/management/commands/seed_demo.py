from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from collecte.demo import charger_demo, enrichir_historique


class Command(BaseCommand):
    help = "Charge des données de démonstration fictives (à n'utiliser que sur une base de développement)."

    def add_arguments(self, parser):
        parser.add_argument("--historique", type=int, default=22,
                            help="Nombre de mois de déclarations fictives à ajouter jusqu'au mois dernier (0 : jeu minimal).")

    def handle(self, *args, **options):
        if not (settings.DEBUG or settings.MODE_DEMO):  # garde-fou : jamais de données fictives dans la base réelle
            raise CommandError("Refusé : DJANGO_DEBUG=0 et GIPAME_MODE_DEMO≠1 (base réelle ?). Données fictives réservées au développement et à la démonstration.")
        from django.db import connection
        with connection.cursor() as cur:  # le calcul des publications prend le rôle gipame_calcul
            cur.execute("SELECT rolsuper OR pg_has_role(current_user, 'gipame_calcul', 'SET') FROM pg_roles WHERE rolname = current_user")
            if options["historique"] and not cur.fetchone()[0]:
                raise CommandError("Le compte connecté ne peut pas prendre le rôle gipame_calcul (cas de Neon). Lancer d'abord : "
                                   "GRANT gipame_calcul TO <propriétaire> ; puis, après seed_demo : REVOKE gipame_calcul FROM <propriétaire>.")
        d = charger_demo(recul=1 if options["historique"] else 0)
        mois = enrichir_historique(d, options["historique"]) if options["historique"] else []
        self.stdout.write(self.style.SUCCESS(
            f"Démo chargée : {len(d.membres)} membres, {len(d.produits)} produits, "
            f"{len(mois) or 2} mois de déclarations (le mois dernier reste à déclarer pour A1 et B3)."))
