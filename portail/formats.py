"""Formats français utilisés par le portail (dates, mois, nombres).

Ces fonctions sont aussi exposées comme filtres de gabarit (templatetags/fr.py).
"""
from datetime import date, datetime, timedelta

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
MOIS_COURTS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
INSECABLE = " "  # espace fine insécable : séparateur de milliers


def nombre(valeur, defaut="—"):
    """12345 → « 12 345 » (espace fine insécable) ; None → tiret."""
    if valeur is None or valeur == "":
        return defaut
    try:
        n = int(valeur)
    except (TypeError, ValueError):
        return str(valeur)
    signe = "-" if n < 0 else ""
    return signe + f"{abs(n):,}".replace(",", INSECABLE)


def pourcentage(valeur, decimales=1):
    if valeur is None:
        return "—"
    return f"{float(valeur):.{decimales}f}".replace(".", ",") + INSECABLE + "%"


def mois_long(d, majuscule=False):
    """date(2026, 11, 1) → « novembre 2026 »."""
    if not d:
        return "—"
    texte = f"{MOIS[d.month - 1]} {d.year}"
    return texte[0].upper() + texte[1:] if majuscule else texte


def de_mois(d):
    """« d'octobre 2026 », « de novembre 2026 » (élision)."""
    if not d:
        return "—"
    nom = MOIS[d.month - 1]
    return ("d'" if nom[0] in "aeiouy" else "de ") + f"{nom} {d.year}"


def mois_court(d):
    return f"{MOIS_COURTS[d.month - 1]} {d.year}" if d else "—"


def date_courte(d):
    """10 nov. 2026."""
    if not d:
        return "—"
    return f"{d.day} {MOIS_COURTS[d.month - 1]} {d.year}"


def date_longue(d):
    """« 11 décembre 2026 » (courriels)."""
    if not d:
        return "—"
    return f"{'1er' if d.day == 1 else d.day} {MOIS[d.month - 1]} {d.year}"


def date_heure(d):
    if not d:
        return "—"
    if isinstance(d, datetime):
        from django.utils import timezone
        d = timezone.localtime(d)
        return f"{date_courte(d)} à {d:%H}h{d:%M}"
    return date_courte(d)


def premier_du_mois(d=None, decalage=0):
    d = d or date.today()
    m = d.year * 12 + d.month - 1 + decalage
    return date(m // 12, m % 12 + 1, 1)


def fin_du_mois(d):
    return premier_du_mois(d, 1) - timedelta(days=1)


def jours_restants(date_limite, aujourd_hui=None):
    return (date_limite - (aujourd_hui or date.today())).days


def phrase_delai(date_limite, aujourd_hui=None):
    """« Il vous reste 3 jours », « C'est le dernier jour », « En retard de 2 jours »."""
    n = jours_restants(date_limite, aujourd_hui)
    if n > 1:
        return f"Il vous reste {n} jours"
    if n == 1:
        return "Il vous reste 1 jour"
    if n == 0:
        return "C'est le dernier jour"
    if n == -1:
        return "En retard de 1 jour"
    return f"En retard de {-n} jours"
