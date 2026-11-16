from django.core.management.base import BaseCommand

from collecte.demo_historique import fabriquer_historique

from ._outils import ecrire_fichier


class Command(BaseCommand):
    help = "Écrit un ancien fichier annuel FICTIF au format réel, pour essayer la reprise de l'historique sans données réelles."

    def add_arguments(self, parser):
        parser.add_argument("--annee", type=int, default=2024)
        parser.add_argument("--sortie", default="sortie")

    def handle(self, *args, **o):
        self.stdout.write(self.style.SUCCESS(
            ecrire_fichier(o["sortie"], f"MTM_{o['annee']}_fictif.xlsx", fabriquer_historique(o["annee"]))))
