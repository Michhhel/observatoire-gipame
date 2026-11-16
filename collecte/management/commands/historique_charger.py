from django.core.management.base import BaseCommand, CommandError

from collecte.excel.historique import charger_historique
from collecte.models import Utilisateur

from ._outils import lire_fichier


class Command(BaseCommand):
    help = "Charge l'historique d'un ancien fichier annuel après rapprochement (compte propriétaire). --a-blanc simule."

    def add_arguments(self, parser):
        parser.add_argument("--fichier", required=True)
        parser.add_argument("--rapprochement", required=True)
        parser.add_argument("--annee", type=int)
        parser.add_argument("--a-blanc", action="store_true", dest="a_blanc")
        parser.add_argument("--utilisateur", help="Nom du compte qui effectue le chargement (audit)")

    def handle(self, *args, **o):
        utilisateur = Utilisateur.objects.filter(username=o["utilisateur"]).first() if o["utilisateur"] else None
        rapport = charger_historique(lire_fichier(o["fichier"]), lire_fichier(o["rapprochement"]), o["annee"], o["a_blanc"],
                                     utilisateur, nom_fichier=o["fichier"])
        self.stdout.write(rapport.en_texte())
        if rapport.totaux:
            self.stdout.write("Totaux recalculés (à comparer à l'ancien fichier) :")
            for (code, mois), total in sorted(rapport.totaux.items()):
                self.stdout.write(f"  {code} {mois} : {total}")
        if rapport.erreurs:
            raise CommandError(f"{len(rapport.erreurs)} erreur(s) : rien n'a été chargé.")
