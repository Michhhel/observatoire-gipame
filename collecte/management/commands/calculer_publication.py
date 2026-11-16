from django.core.management.base import BaseCommand, CommandError

from collecte.contexte import en_role
from collecte.services import calculer_publication

from ._outils import mois_depuis_texte


class Command(BaseCommand):
    help = "Calcule et fige la publication d'un mois (rôle PostgreSQL gipame_calcul)."

    def add_arguments(self, parser):
        parser.add_argument("--mois", required=True, help="AAAA-MM")
        parser.add_argument("--definitive", action="store_true")

    def handle(self, *args, **o):
        mois = mois_depuis_texte(o["mois"])
        try:
            with en_role("gipame_calcul"):
                pub = calculer_publication(mois, statut="DEFINITIVE" if o["definitive"] else "PROVISOIRE")
                n, masquees = pub.cellules.count(), pub.cellules.filter(supprime=True).count()
        except ValueError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(
            f"Publication {pub.statut} v{pub.version} {mois:%Y-%m} : couverture {pub.couverture_pct} % "
            f"({pub.nb_membres_declarants}/{pub.nb_membres_attendus}), {n} cellules dont {masquees} masquées."))
