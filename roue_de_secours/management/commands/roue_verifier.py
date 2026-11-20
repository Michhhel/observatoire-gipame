"""Contrôle de la base de connaissances de la Roue de Secours. Sans base de données (utilisable en intégration continue).

    python manage.py roue_verifier            # fiches + jeu d'évaluation ; code de sortie 1 en cas de problème
    python manage.py roue_verifier --strict   # les avertissements (fiche non relue depuis un an…) deviennent bloquants
"""
from django.core.management.base import BaseCommand, CommandError

from roue_de_secours import connaissances, reglages
from roue_de_secours.connaissances import Section
from roue_de_secours.evaluation import CAS, HORS_SUJET
from roue_de_secours.recherche import Index

SEUIL_REUSSITE = 0.9

# Sections du jour (lues en base en temps normal) remplacées par des exemples fixes pour l'évaluation.
EXEMPLES_DU_JOUR = [
    Section("calendrier", "Calendrier de la collecte", "", "Mois à déclarer en ce moment : octobre, date limite le 10 novembre.",
            frozenset({"TOUS"}), "/declarer/", ("Quel mois déclarer ?", "Quelle est la date limite ?"), True),
    Section("grille-segments", "Grille des segments", "", "Grille actuelle des segments (types de véhicules) : "
            "Véhicules particuliers : Segment A/B, Segment M1 ; Pick-up : Pick-up 4x2, Pick-up 4x4.", frozenset({"TOUS"}),
            "/le-marche/", ("Dans quel segment est mon véhicule ?", "Quels sont les segments ?", "Types de véhicules"), False),
]


def evaluer():
    index = Index(list(connaissances.sections()) + EXEMPLES_DU_JOUR)
    echecs = []
    for role, question, attendues in CAS:
        trouvees = [r.section.fiche_id for r in index.chercher(question, role)[:3]]
        if not set(trouvees) & attendues:
            echecs.append((role, question, attendues, trouvees))
    faux_positifs = [(role, q, [r.section.fiche_id for r in index.chercher(q, role)[:2]])
                     for role, q in HORS_SUJET if index.chercher(q, role)]
    return echecs, faux_positifs


class Command(BaseCommand):
    help = "Vérifie les fiches de la Roue de Secours (format, liens, variables, fraîcheur) et la qualité de la recherche."
    requires_system_checks = []  # aucune base de données nécessaire (exécutable en intégration continue)

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="Les avertissements font échouer la commande.")

    def handle(self, *args, **options):
        fiches = connaissances.charger()
        self.stdout.write(f"Fiches : {len(fiches)} ({sum(len(f.sections) for f in fiches)} passages). "
                          f"Fournisseur : {reglages.fournisseur()}" + (f", modèle {reglages.modele()}" if reglages.modele() else ""))
        problemes = connaissances.verifier(fiches)
        avertissements = connaissances.avertissements(fiches)
        for p in problemes:
            self.stdout.write(self.style.ERROR(f"  PROBLÈME  {p}"))
        for a in avertissements:
            self.stdout.write(self.style.WARNING(f"  À REVOIR  {a}"))
        echecs, faux_positifs = evaluer()
        taux = 1 - len(echecs) / len(CAS)
        for role, q, attendues, trouvees in echecs:
            self.stdout.write(self.style.WARNING(f"  RECHERCHE [{role}] « {q} » → {trouvees or 'rien'} (attendu : {', '.join(sorted(attendues))})"))
        for role, q, trouvees in faux_positifs:
            self.stdout.write(self.style.WARNING(f"  HORS SUJET [{role}] « {q} » a retrouvé {trouvees}"))
        self.stdout.write(f"Évaluation de la recherche : {len(CAS) - len(echecs)}/{len(CAS)} ({taux:.0%}), "
                          f"seuil {SEUIL_REUSSITE:.0%}.")
        if problemes or taux < SEUIL_REUSSITE or (options["strict"] and (avertissements or faux_positifs)):
            raise CommandError("La base de connaissances de la Roue de Secours doit être corrigée (voir ci-dessus).")
        self.stdout.write(self.style.SUCCESS("Base de connaissances en ordre."))
