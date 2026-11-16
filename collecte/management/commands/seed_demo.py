from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from collecte.demo import charger_demo


class Command(BaseCommand):
    help = "Charge des données de démonstration fictives (à n'utiliser que sur une base de développement)."

    def handle(self, *args, **options):
        if not settings.DEBUG:  # garde-fou : jamais de données fictives dans la base de production
            raise CommandError("Refusé : DJANGO_DEBUG=0 (base de production ?). Données fictives réservées au développement.")
        d = charger_demo()
        self.stdout.write(self.style.SUCCESS(
            f"Démo chargée : {len(d.membres)} membres, {len(d.produits)} produits, "
            f"mois {d.mois_plein:%Y-%m} (complet) et {d.mois_partiel:%Y-%m} (B3 manquant)."))
