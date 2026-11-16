from django.core.management.base import BaseCommand

from collecte.contexte import en_role
from collecte.excel.gabarit import generer_gabarit

from ._outils import ecrire_fichier, membre_et_compte, mois_depuis_texte


class Command(BaseCommand):
    help = "Génère le gabarit Excel mensuel d'un membre (rôle PostgreSQL gipame_membre)."

    def add_arguments(self, parser):
        parser.add_argument("--membre", required=True, help="Code du membre (ex. A1)")
        parser.add_argument("--mois", required=True, help="AAAA-MM")
        parser.add_argument("--sortie", default="sortie")

    def handle(self, *args, **o):
        membre, compte = membre_et_compte(o["membre"])
        mois = mois_depuis_texte(o["mois"])
        with en_role("gipame_membre", membre_id=membre.id, utilisateur_id=compte.pk if compte else None):
            contenu, version, n = generer_gabarit(membre, mois)
        chemin = ecrire_fichier(o["sortie"], f"declaration_{membre.code}_{mois:%Y-%m}_v{version}.xlsx", contenu)
        self.stdout.write(self.style.SUCCESS(f"{chemin} : {n} lignes, version {version}"))
