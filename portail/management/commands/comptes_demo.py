"""Donne un mot de passe connu aux comptes du jeu de démonstration (développement uniquement).

Usage : python manage.py comptes_demo  → identifiant <nom>@demo.gipame.ci, mot de passe « demo-2026 »
Refuse de s'exécuter hors développement (DEBUG) et hors démonstration (GIPAME_MODE_DEMO=1).
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from collecte.models import Utilisateur

MOT_DE_PASSE = "demo-2026"


class Command(BaseCommand):
    help = "Attribue un e-mail et un mot de passe de démonstration aux comptes du jeu seed_demo (développement ou démonstration)."

    def handle(self, *args, **options):
        if not (settings.DEBUG or settings.MODE_DEMO):
            raise CommandError("Refusé : cette commande ne s'exécute qu'en développement (DEBUG=1) ou en démonstration (GIPAME_MODE_DEMO=1).")
        n = 0
        for u in Utilisateur.objects.all():
            if u.is_superuser:
                continue
            email = f"{u.username.lower()}@demo.gipame.ci"
            u.email = email
            u.username = email  # l'identifiant de connexion est l'adresse e-mail
            u.set_password(MOT_DE_PASSE)
            u.save()
            n += 1
        self.stdout.write(f"{n} comptes prêts. Identifiant : <nom>@demo.gipame.ci (ex. user_a1@demo.gipame.ci), mot de passe : {MOT_DE_PASSE}")
