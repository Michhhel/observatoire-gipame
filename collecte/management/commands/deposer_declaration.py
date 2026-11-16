import os

from django.core.management.base import BaseCommand

from collecte.contexte import en_role
from collecte.excel.depot import deposer_declaration

from ._outils import lire_fichier, membre_et_compte


class Command(BaseCommand):
    help = "Dépose un fichier Excel de déclaration au nom d'un membre et affiche le rapport de contrôle."

    def add_arguments(self, parser):
        parser.add_argument("--membre", required=True)
        parser.add_argument("--fichier", required=True)
        parser.add_argument("--soumettre", action="store_true", help="Soumettre si aucune erreur et attestation à OUI")

    def handle(self, *args, **o):
        membre, compte = membre_et_compte(o["membre"])
        contenu = lire_fichier(o["fichier"])
        with en_role("gipame_membre", membre_id=membre.id, utilisateur_id=compte.pk if compte else None):
            rapport = deposer_declaration(contenu, os.path.basename(o["fichier"]), membre, compte, soumettre=o["soumettre"])
        self.stdout.write(rapport.en_texte())
