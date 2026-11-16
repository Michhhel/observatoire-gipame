from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from collecte.contexte import en_role
from collecte.rappels import envoyer_rappels, jours_de_rappel

from ._outils import mois_depuis_texte


class Command(BaseCommand):
    help = ("Envoie les rappels de dépôt (rôle gipame_gestion ; connexion gipame_app suffisante). Sans --mois : le mois "
            "précédent. Avec --si-echeance : n'envoie que les jours prévus (J-3, J+1, J+7 autour de la date limite) — "
            "c'est l'option utilisée par la tâche planifiée quotidienne (.github/workflows/rappels.yml).")

    def add_arguments(self, parser):
        parser.add_argument("--mois", help="AAAA-MM (défaut : mois précédent)")
        parser.add_argument("--si-echeance", action="store_true")

    def handle(self, *args, **o):
        if o["mois"]:
            mois = mois_depuis_texte(o["mois"])
        else:
            t = date.today()
            mois = date(t.year - (t.month == 1), (t.month - 2) % 12 + 1, 1)
        with transaction.atomic(), en_role("gipame_gestion"):
            if o["si_echeance"] and not jours_de_rappel(mois):
                self.stdout.write(f"{mois:%Y-%m} : pas un jour de rappel, rien à faire.")
                return
            bilan = envoyer_rappels(mois)
        self.stdout.write(self.style.SUCCESS(
            f"{mois:%Y-%m} : {bilan['envoyes']} rappel(s) envoyé(s), {bilan['membres']} membre(s) sans déclaration soumise, "
            f"{len(bilan['sans_compte'])} sans compte actif, {len(bilan['echecs'])} échec(s)."))
