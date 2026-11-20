"""Relecture des avis laissés sur la Roue de Secours (connexion PROPRIÉTAIRE : les rôles du portail ne peuvent pas lire
cette table). Les avis sont anonymes : rôle, page, question, réponse, sources, commentaire.

    python manage.py roue_avis                    # avis « À revoir » et questions sans réponse des 31 derniers jours
    python manage.py roue_avis --jours 90 --tous  # tous les avis, y compris « Utile »
    python manage.py roue_avis --sortie avis.md   # même chose dans un fichier Markdown
    python manage.py roue_avis --purger 365       # efface les avis de plus de 365 jours (conservation limitée)
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from roue_de_secours.models import Avis

LIBELLES = {1: "Utile", -1: "À revoir", 0: "Sans réponse"}


class Command(BaseCommand):
    help = "Affiche les avis sur la Roue de Secours (à faire chaque mois) ; peut purger les plus anciens."

    def add_arguments(self, parser):
        parser.add_argument("--jours", type=int, default=31)
        parser.add_argument("--tous", action="store_true", help="Inclure les avis « Utile ».")
        parser.add_argument("--sortie", help="Écrire le rapport dans ce fichier Markdown.")
        parser.add_argument("--purger", type=int, metavar="JOURS", help="Effacer les avis plus anciens que JOURS jours.")

    def handle(self, *args, jours, tous, sortie=None, purger=None, **options):
        if purger:
            n, _ = Avis.objects.filter(cree_le__lt=timezone.now() - timedelta(days=purger)).delete()
            self.stdout.write(self.style.SUCCESS(f"{n} avis de plus de {purger} jours effacés."))
            return
        depuis = timezone.now() - timedelta(days=jours)
        avis = Avis.objects.filter(cree_le__gte=depuis).order_by("note", "-cree_le")
        total = {n: avis.filter(note=n).count() for n in (1, -1, 0)}
        lignes = [f"# Avis sur la Roue de Secours — {jours} derniers jours", "",
                  f"Utile : {total[1]} · À revoir : {total[-1]} · Sans réponse : {total[0]}", ""]
        for a in (avis if tous else avis.exclude(note=1)):
            lignes += [f"## {LIBELLES[a.note]} — {a.cree_le:%d/%m/%Y %H:%M} — {a.role}" + (f" — {a.page}" if a.page else ""),
                       f"**Question** : {a.question}", ""]
            if a.reponse:
                lignes += ["**Réponse** :", "", "> " + a.reponse.replace("\n", "\n> "), ""]
            if a.sources:
                lignes.append(f"**Sources** : {a.sources}" + (f" · mode {a.mode}" if a.mode else ""))
            if a.commentaire:
                lignes.append(f"**Commentaire** : {a.commentaire}")
            lignes.append("")
        lignes.append("Pour chaque avis : corriger ou créer la fiche, ajouter la question à roue_de_secours/evaluation.py, "
                      "puis `python manage.py roue_verifier`.")
        texte = "\n".join(lignes)
        if sortie:
            with open(sortie, "w", encoding="utf-8") as f:
                f.write(texte)
            self.stdout.write(self.style.SUCCESS(f"Rapport écrit dans {sortie}."))
        else:
            self.stdout.write(texte)
