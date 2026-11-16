"""Services de la gestion (secrétariat du GIPAME) : validation des produits proposés, demandes d'accès
exceptionnel. À exécuter dans le rôle gipame_gestion (middleware). Rien n'est supprimé : un produit
proposé devient ACTIF, FUSIONNE ou REJETE, et la décision est tracée sur la ligne elle-même.
"""
from django.db import transaction
from django.utils import timezone

from .excel import commun as c
from .models import ClassementProduit, DemandeAccesExceptionnel, Modele, Produit, Segment, Segmentation


class DecisionImpossible(ValueError):
    """Message destiné à l'agent de gestion."""


def _decider(produit, utilisateur, statut, motif):
    produit.statut = statut
    produit.decide_par_id = utilisateur.id
    produit.decide_le = timezone.now()
    produit.motif_decision = motif or ""


def valider_proposition(produit_id, utilisateur, segment, nom_modele=None, finition=None, motif=""):
    """Transforme une proposition en produit ACTIF, classé dans la segmentation courante.
    Le code est attribué automatiquement par la base. Lève DecisionImpossible si incohérent."""
    with transaction.atomic():
        produit = Produit.objects.select_for_update().get(pk=produit_id)
        if produit.statut != "PROPOSE":
            raise DecisionImpossible("Cette proposition a déjà été traitée.")
        segmentation = Segmentation.objects.filter(statut="COURANTE").first()
        if segmentation is None or segment.categorie.segmentation_id != segmentation.id:
            raise DecisionImpossible("Le segment choisi n'appartient pas à la segmentation en vigueur.")
        marque = produit.modele.marque if produit.modele_id else produit.marque_proposee
        nom_modele = c.texte_propre(nom_modele or (produit.modele.nom if produit.modele_id else produit.modele_propose), 120)
        if not nom_modele:
            raise DecisionImpossible("Le nom du modèle est obligatoire.")
        modele = next((m for m in Modele.objects.filter(marque=marque) if c.normaliser(m.nom) == c.normaliser(nom_modele)), None)
        if modele is None:
            modele = Modele.objects.create(marque=marque, nom=nom_modele)
        produit.modele = modele
        produit.modele_propose = ""
        if finition:
            produit.finition = c.texte_propre(finition, 120).upper()
        produit.libelle_affiche = f"{modele.nom} {produit.finition}".strip()
        doublon = Produit.objects.filter(
            modele=modele, finition=produit.finition, energie=produit.energie, boite=produit.boite,
            cylindree_cm3=produit.cylindree_cm3, puissance_fiscale_cv=produit.puissance_fiscale_cv,
            motricite=produit.motricite, statut__in=["ACTIF", "ARCHIVE"]).exclude(pk=produit.pk).first()
        if doublon:
            raise DecisionImpossible(f"Un produit identique existe déjà ({doublon.code} {doublon.libelle_affiche}) : "
                                     "utilisez « Fusionner » vers ce produit.")
        _decider(produit, utilisateur, "ACTIF", motif)
        produit.save()
        ClassementProduit.objects.create(produit=produit, segmentation=segmentation, segment=segment, source="MANUEL")
        produit.refresh_from_db()
    return produit


def fusionner_proposition(produit_id, cible_id, utilisateur, motif=""):
    """La proposition est un doublon d'un produit existant : on la marque FUSIONNE vers la cible."""
    with transaction.atomic():
        produit = Produit.objects.select_for_update().get(pk=produit_id)
        cible = Produit.objects.get(pk=cible_id, statut__in=["ACTIF", "ARCHIVE"])
        if produit.statut != "PROPOSE":
            raise DecisionImpossible("Cette proposition a déjà été traitée.")
        produit.fusionne_dans = cible
        _decider(produit, utilisateur, "FUSIONNE", motif)
        produit.save()
    return produit


def rejeter_proposition(produit_id, utilisateur, motif):
    with transaction.atomic():
        produit = Produit.objects.select_for_update().get(pk=produit_id)
        if produit.statut != "PROPOSE":
            raise DecisionImpossible("Cette proposition a déjà été traitée.")
        if not (motif or "").strip():
            raise DecisionImpossible("Un motif est obligatoire pour rejeter une proposition.")
        _decider(produit, utilisateur, "REJETE", motif.strip())
        produit.save()
    return produit


def segments_courants():
    segmentation = Segmentation.objects.filter(statut="COURANTE").first()
    if segmentation is None:
        return Segment.objects.none()
    return Segment.objects.filter(categorie__segmentation=segmentation).select_related("categorie").order_by(
        "categorie__ordre", "ordre")


def creer_demande_acces(demandeur, motif, membre_cible, mois_debut, mois_fin, duree_minutes=60):
    with transaction.atomic():
        return DemandeAccesExceptionnel.objects.create(
            demandeur=demandeur, motif=motif.strip(), membre_cible=membre_cible, mois_debut=mois_debut,
            mois_fin=mois_fin, duree_minutes=duree_minutes)


def parametres_publication():
    """Paramètres utiles à l'écran des publications (lisibles par la gestion)."""
    from .models import ParametreSysteme
    return ParametreSysteme.objects.filter(cle__in=["couverture_min_publication_pct"]).values_list("cle", "valeur")
