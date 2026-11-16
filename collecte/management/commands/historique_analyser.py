from django.core.management.base import BaseCommand

from collecte.excel.historique import ecrire_rapprochement, lire_historique

from ._outils import ecrire_fichier, lire_fichier


class Command(BaseCommand):
    help = "Analyse un ancien fichier annuel et produit le fichier de rapprochement à valider (lecture seule)."

    def add_arguments(self, parser):
        parser.add_argument("--fichier", required=True)
        parser.add_argument("--annee", type=int)
        parser.add_argument("--sortie", default="sortie")

    def handle(self, *args, **o):
        lecture = lire_historique(lire_fichier(o["fichier"]), o["annee"])
        contenu, a_completer = ecrire_rapprochement(lecture)
        chemin = ecrire_fichier(o["sortie"], f"rapprochement_{lecture.annee}.xlsx", contenu)
        self.stdout.write(self.style.SUCCESS(
            f"{chemin} : {len(lecture.lignes)} lignes produit (sur {lecture.nb_lignes_source} lignes source), "
            f"{a_completer} à compléter, {len(lecture.anomalies)} anomalie(s) (onglet ANOMALIES)."))
