"""Aide commune aux commandes : lecture de fichiers, écriture de sorties, résolution de membre/utilisateur."""
import os
from datetime import date

from django.core.management.base import CommandError

from collecte.models import Membre, Utilisateur


def mois_depuis_texte(texte):
    try:
        annee, mois = (int(x) for x in texte.split("-")[:2])
        return date(annee, mois, 1)
    except (ValueError, AttributeError):
        raise CommandError("Le mois doit avoir la forme AAAA-MM (ex. 2027-01).")


def membre_et_compte(code_membre, nom_utilisateur=None):
    try:
        membre = Membre.objects.get(code=code_membre)
    except Membre.DoesNotExist:
        raise CommandError(f"Membre inconnu : {code_membre}")
    compte = Utilisateur.objects.filter(username=nom_utilisateur).first() if nom_utilisateur else \
        Utilisateur.objects.filter(membre=membre, role_metier="MEMBRE").first()
    return membre, compte


def ecrire_fichier(dossier, nom, contenu):
    os.makedirs(dossier, exist_ok=True)
    chemin = os.path.join(dossier, nom)
    with open(chemin, "wb") as f:
        f.write(contenu)
    return chemin


def lire_fichier(chemin):
    if not os.path.isfile(chemin):
        raise CommandError(f"Fichier introuvable : {chemin}")
    with open(chemin, "rb") as f:
        return f.read()
