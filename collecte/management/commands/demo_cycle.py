from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from collecte.cycle import executer_cycle_demo

from ._outils import mois_depuis_texte


class Command(BaseCommand):
    help = ("Cycle complet sur la base de démonstration : gabarits, remplissage, dépôts, publication, exports. "
            "Chaque étape utilise le rôle PostgreSQL qui lui correspond. Écrit tous les fichiers Excel dans --sortie.")

    def add_arguments(self, parser):
        parser.add_argument("--sortie", default="sortie_demo")
        parser.add_argument("--mois", help="AAAA-MM (par défaut : le mois courant)")

    def handle(self, *args, **o):
        if not settings.DEBUG:  # garde-fou : jamais de données fictives dans la base de production
            raise CommandError("Refusé : DJANGO_DEBUG=0 (base de production ?). Données fictives réservées au développement.")
        try:
            executer_cycle_demo(mois_depuis_texte(o["mois"]) if o["mois"] else None, o["sortie"], journal=self.stdout.write)
        except RuntimeError as exc:
            raise CommandError(str(exc))
