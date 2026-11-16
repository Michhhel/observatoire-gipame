from django.core.management.base import BaseCommand, CommandError

from collecte.contexte import en_role
from collecte.excel import exports
from collecte.models import Publication

from ._outils import ecrire_fichier, membre_et_compte, mois_depuis_texte


class Command(BaseCommand):
    help = "Exporte un fichier Excel : annee (membre), publication (bureau ou gestion), suivi (gestion)."

    def add_arguments(self, parser):
        parser.add_argument("type", choices=["annee", "publication", "suivi"])
        parser.add_argument("--membre")
        parser.add_argument("--annee", type=int)
        parser.add_argument("--mois")
        parser.add_argument("--detail", action="store_true", help="Publication : ajoute contributeurs et motifs (gestion)")
        parser.add_argument("--sortie", default="sortie")

    def handle(self, *args, **o):
        if o["type"] == "annee":
            if not o["membre"] or not o["annee"]:
                raise CommandError("--membre et --annee sont requis.")
            membre, compte = membre_et_compte(o["membre"])
            with en_role("gipame_membre", membre_id=membre.id, utilisateur_id=compte.pk if compte else None):
                contenu = exports.exporter_annee_membre(membre, o["annee"])
            nom = f"annee_{membre.code}_{o['annee']}.xlsx"
        elif o["type"] == "publication":
            if not o["mois"]:
                raise CommandError("--mois est requis.")
            mois = mois_depuis_texte(o["mois"])
            role = "gipame_gestion" if o["detail"] else "gipame_bureau"
            with en_role(role):
                pub = Publication.objects.filter(mois=mois).order_by("-version").first()
                if pub is None:
                    raise CommandError("Aucune publication pour ce mois.")
                contenu = exports.exporter_publication(pub, detail=o["detail"])
            nom = f"publication_{mois:%Y-%m}_v{pub.version}{'_detail' if o['detail'] else ''}.xlsx"
        else:
            with en_role("gipame_gestion"):
                contenu = exports.exporter_suivi_depots()
            nom = "suivi_depots.xlsx"
        self.stdout.write(self.style.SUCCESS(ecrire_fichier(o["sortie"], nom, contenu)))
