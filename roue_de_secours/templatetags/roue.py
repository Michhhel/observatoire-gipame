from django import template

from .. import reglages

register = template.Library()


@register.inclusion_tag("roue_de_secours/_charte.html")
def roue_charte():
    """Paragraphe de la charte de confidentialité sur la Roue de Secours (affiché seulement si elle est active)."""
    return {"active": reglages.active(), "ia": reglages.fournisseur() != "hors_ligne", "prestataire": reglages.prestataire()}
