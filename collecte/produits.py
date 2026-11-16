"""Services « produits » côté membre : proposer un nouveau produit, masquer / réafficher une ligne.

Mêmes règles que l'onglet AJOUTS du gabarit (excel/depot.py), appelées depuis le portail. À exécuter
dans le contexte du membre (rôle gipame_membre) : la sécurité par ligne limite tout à ses données.
"""
from django.db import transaction

from .contexte import garantir_contexte_membre
from .excel import commun as c
from .excel.depot import _produit_propose
from .models import Concession, Marque, Modele, Produit, ProduitMembre


class PropositionRefusee(ValueError):
    """Message destiné au membre (français simple)."""


def marques_du_membre(membre):
    return Marque.objects.filter(concessions__membre=membre).distinct().order_by("nom")


def proposer_produit(membre, marque, nom_modele, finition, energie, boite=None, motricite="", segment="", note="",
                     cylindree=None, puissance=None, charge=None, ptac=None, places=None):
    """Crée (ou retrouve) la proposition PROPOSE du membre. Renvoie (produit, produit_proche_ou_None).
    Lève PropositionRefusee si le produit existe déjà au catalogue ou si la marque n'est pas la sienne."""
    with transaction.atomic():
        garantir_contexte_membre(membre.id)
        if not Concession.objects.filter(membre=membre, marque=marque).exists():
            raise PropositionRefusee("Cette marque ne fait pas partie de vos marques : contactez le GIPAME pour l'ajouter.")
        nom_modele, finition = c.texte_propre(nom_modele, 120), c.texte_propre(finition, 120).upper()
        motricite = c.texte_propre(motricite, 10).upper()
        if not nom_modele or not finition:
            raise PropositionRefusee("Le modèle et la version / finition sont obligatoires.")
        modele = next((m for m in Modele.objects.filter(marque=marque) if c.normaliser(m.nom) == c.normaliser(nom_modele)), None)
        proche = None
        if modele:
            existants = Produit.objects.filter(modele=modele, statut__in=["ACTIF", "ARCHIVE"])
            exact = next((p for p in existants if c.normaliser(p.finition) == c.normaliser(finition)
                          and p.energie_id == energie.id and p.boite_id == (boite.id if boite else None)
                          and p.cylindree_cm3 == cylindree and p.puissance_fiscale_cv == puissance
                          and p.motricite == motricite), None)
            if exact:
                raise PropositionRefusee(f"Ce produit existe déjà au catalogue ({exact.libelle_affiche}) : déclarez-le "
                                         "directement. S'il n'apparaît pas dans votre gabarit, contactez le GIPAME.")
            proche = next((p for p in existants if c.normaliser(p.finition) == c.normaliser(finition)), None)
        produit = _produit_propose(membre, {
            "marque": marque, "modele": modele, "nom_modele": nom_modele, "finition": finition, "energie": energie,
            "boite": boite, "motricite": motricite, "segment": c.texte_propre(segment, 150), "note": c.texte_propre(note, 500),
            "cylindree": cylindree, "puissance": puissance, "charge": charge, "ptac": ptac, "places": places})
    return produit, proche


def changer_affichage(membre, produit_id, masquer, motif=""):
    """Masque (ou réaffiche) un produit dans les gabarits du membre. Rien n'est supprimé : l'historique reste."""
    with transaction.atomic():
        garantir_contexte_membre(membre.id)
        produit = Produit.objects.get(pk=produit_id)
        exception, _ = ProduitMembre.objects.get_or_create(
            membre=membre, produit=produit, defaults={"etat": "MASQUE" if masquer else "AFFICHE_FORCE", "motif": motif})
        exception.etat = "MASQUE" if masquer else "AFFICHE_FORCE"
        exception.mode = "MANUEL"
        exception.motif = motif
        exception.save(update_fields=["etat", "mode", "motif", "modifie_le"])
    return exception
