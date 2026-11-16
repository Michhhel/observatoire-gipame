"""Filtres de gabarit : formats français. Usage : {% load fr %} puis {{ valeur|nombre }}."""
from django import template

from .. import formats

register = template.Library()

register.filter("nombre", formats.nombre)
register.filter("pourcentage", formats.pourcentage)
register.filter("mois_long", formats.mois_long)
register.filter("mois_court", formats.mois_court)
register.filter("de_mois", formats.de_mois)
register.filter("date_courte", formats.date_courte)
register.filter("date_heure", formats.date_heure)


@register.filter
def mois_titre(d):
    return formats.mois_long(d, majuscule=True)


@register.filter
def cle(dictionnaire, clef):
    """{{ dico|cle:clef }} — lecture d'un dictionnaire avec une clé calculée."""
    try:
        return dictionnaire.get(clef)
    except AttributeError:
        return None


@register.filter
def badge_statut(statut):
    """Classe CSS du badge d'un statut de déclaration / dépôt / publication."""
    return {
        "BROUILLON": "badge--brouillon", "SOUMISE": "badge--soumise", "REMPLACEE": "badge--remplacee",
        "ANNULEE": "badge--annulee", "ACCEPTE": "badge--soumise", "ACCEPTE_AVEC_ALERTES": "badge--alerte",
        "REJETE": "badge--rejete", "PROVISOIRE": "badge--provisoire", "DEFINITIVE": "badge--definitive",
        "PROPOSE": "badge--attente", "ACTIF": "badge--soumise", "ARCHIVE": "badge--neutre",
        "FUSIONNE": "badge--remplacee", "MASQUE": "badge--neutre",
    }.get(statut, "badge--neutre")


@register.filter
def libelle_statut(statut):
    return {
        "BROUILLON": "Brouillon", "SOUMISE": "Soumise", "REMPLACEE": "Remplacée", "ANNULEE": "Annulée",
        "ACCEPTE": "Accepté", "ACCEPTE_AVEC_ALERTES": "Accepté avec alertes", "REJETE": "Refusé",
        "PROVISOIRE": "Provisoire", "DEFINITIVE": "Définitive", "PROPOSE": "En attente de validation",
        "ACTIF": "Actif", "ARCHIVE": "Archivé", "REJETE_PRODUIT": "Rejeté", "FUSIONNE": "Fusionné", "MASQUE": "Masqué",
        "APPROUVEE": "Approuvée", "REFUSEE": "Refusée",
    }.get(statut, statut or "—")
