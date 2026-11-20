"""Pose une question à la Roue de Secours depuis la console, comme le ferait un compte du rôle choisi.

    python manage.py roue_essai "Comment déclarer mes ventes ?"
    python manage.py roue_essai "Qui n'a pas déclaré ?" --compte gestionnaire@demo.gipame.ci
    python manage.py roue_essai "…" --hors-ligne     # sans appel au service d'IA
    python manage.py roue_essai "…" --voir-prompt    # affiche exactement ce qui serait envoyé au prestataire

Sert à vérifier une clé d'API, un nouveau modèle, ou l'effet d'une fiche modifiée. À lancer avec la connexion
habituelle (propriétaire en développement) : la situation est lue sous le rôle du compte choisi.
"""
import json

from django.core.management.base import BaseCommand, CommandError

from collecte.contexte import en_role
from collecte.middleware import ROLES_DB
from collecte.models import Utilisateur
from roue_de_secours import conversation
from roue_de_secours.fournisseurs import HorsLigne, construire


class Command(BaseCommand):
    help = "Pose une question à la Roue de Secours (test d'une clé d'API, d'un modèle ou d'une fiche)."

    def add_arguments(self, parser):
        parser.add_argument("question")
        parser.add_argument("--compte", help="Adresse du compte dont on prend le rôle (défaut : premier compte membre actif).")
        parser.add_argument("--hors-ligne", action="store_true")
        parser.add_argument("--voir-prompt", action="store_true")

    def handle(self, *args, question, compte=None, hors_ligne=False, voir_prompt=False, **options):
        if compte:
            user = Utilisateur.objects.filter(username=compte).first() or Utilisateur.objects.filter(email=compte).first()
        else:
            user = Utilisateur.objects.filter(role_metier="MEMBRE", is_active=True).exclude(membre=None).first()
        if user is None:
            raise CommandError("Compte introuvable.")
        with en_role(ROLES_DB[user.role_metier], membre_id=user.membre_id, utilisateur_id=user.pk):
            prep = conversation.preparer(user, question, [], None)
        if voir_prompt:
            self.stdout.write("=== BLOC FIXE ===\n" + prep.requete.systeme_fixe + "\n\n=== BLOC VARIABLE ===\n"
                              + prep.requete.systeme_variable + "\n\n=== QUESTION ===\n" + question + "\n")
        fournisseur = HorsLigne() if hors_ligne else construire()
        self.stdout.write(f"[rôle {user.role_metier} · fournisseur {fournisseur.nom}{' · ' + fournisseur.modele if fournisseur.modele else ''}]\n")
        for ligne in conversation.flux(prep, fournisseur):
            ev = json.loads(ligne)
            if ev["t"] == "sources":
                self.stdout.write("Sources : " + (", ".join(s["titre"] for s in ev["sources"]) or "aucune") + "\n")
            elif ev["t"] == "texte":
                self.stdout.write(ev["d"], ending="")
                self.stdout.flush()
            elif ev["t"] == "mode":
                self.stdout.write(self.style.WARNING(f"\n[bascule hors ligne : {ev['raison']}]\n"))
            elif ev["t"] == "erreur":
                self.stdout.write(self.style.ERROR(f"\n[{ev['message']}]"))
        self.stdout.write(f"\n\n[jetons : {fournisseur.usage or '-'}]")
