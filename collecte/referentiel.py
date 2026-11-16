"""Référentiel des membres, tenu par la gestion depuis le portail : membres, groupes économiques, périodes
d'adhésion, marques et concessions. Rien ne se supprime : on clôt une période (date de fin) et on en ouvre une
autre. Les chevauchements sont refusés par la base (contraintes d'exclusion) ; chaque modification est tracée
dans collecte_journalmodification (triggers). À exécuter sous gipame_gestion (middleware).
"""
import calendar
import re

from django.db import IntegrityError, transaction

from .models import Concession, GroupeEconomique, Marque, Membre, Origine, PeriodeAdhesion


class ReferentielInvalide(ValueError):
    """Message destiné à l'agent de gestion."""


def fin_de_mois(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _code(texte, longueur):
    code = re.sub(r"[^A-Z0-9_]", "", (texte or "").strip().upper().replace(" ", "_"))
    if not code or len(code) > longueur:
        raise ReferentielInvalide(f"Code invalide : lettres, chiffres et _ uniquement, {longueur} caractères au plus.")
    return code


def _groupe(nom):
    nom = (nom or "").strip()
    if not nom:
        return None
    groupe = next((g for g in GroupeEconomique.objects.all() if g.nom.lower() == nom.lower()), None)
    return groupe or GroupeEconomique.objects.create(nom=nom[:150])


def _enregistrer(fonction):
    """Traduit les refus de la base (doublon, chevauchement) en message lisible."""
    try:
        with transaction.atomic():
            return fonction()
    except IntegrityError as e:
        texte = str(e)
        if "chevauchement" in texte:
            raise ReferentielInvalide("Cette période chevauche une période existante : clôturez d'abord la précédente.")
        if "unique" in texte.lower() or "duplicate" in texte.lower():
            raise ReferentielInvalide("Ce code existe déjà.")
        if "dates_ok" in texte:
            raise ReferentielInvalide("La date de fin précède la date de début.")
        raise ReferentielInvalide("Enregistrement refusé par la base de données.")


def creer_membre(code, raison_sociale, groupe_nom, debut, marques=()):
    """Nouveau membre déclarant à partir du mois `debut` (1er du mois), avec ses marques."""
    code = _code(code, 20)
    raison_sociale = (raison_sociale or "").strip()
    if not raison_sociale:
        raise ReferentielInvalide("La raison sociale est obligatoire.")

    def faire():
        membre = Membre.objects.create(code=code, raison_sociale=raison_sociale[:200], groupe=_groupe(groupe_nom))
        PeriodeAdhesion.objects.create(membre=membre, date_debut=debut)
        for marque in marques:
            Concession.objects.create(membre=membre, marque=marque, date_debut=debut)
        return membre
    return _enregistrer(faire)


def modifier_membre(membre, raison_sociale, groupe_nom):
    raison_sociale = (raison_sociale or "").strip()
    if not raison_sociale:
        raise ReferentielInvalide("La raison sociale est obligatoire.")

    def faire():
        membre.raison_sociale = raison_sociale[:200]
        membre.groupe = _groupe(groupe_nom)
        membre.save(update_fields=["raison_sociale", "groupe", "modifie_le"])
    _enregistrer(faire)


def ouvrir_adhesion(membre, debut):
    _enregistrer(lambda: PeriodeAdhesion.objects.create(membre=membre, date_debut=debut))


def clore_adhesion(periode, dernier_mois):
    """Le membre ne déclare plus après `dernier_mois` (inclus)."""
    def faire():
        periode.date_fin = fin_de_mois(dernier_mois)
        periode.save(update_fields=["date_fin", "modifie_le"])
    _enregistrer(faire)


def ajouter_concession(membre, marque, debut):
    _enregistrer(lambda: Concession.objects.create(membre=membre, marque=marque, date_debut=debut))


def clore_concession(concession, dernier_mois):
    def faire():
        concession.date_fin = fin_de_mois(dernier_mois)
        concession.save(update_fields=["date_fin", "modifie_le"])
    _enregistrer(faire)


def creer_marque(code, nom, origine):
    code = _code(code, 30)
    nom = (nom or "").strip()
    if not nom or not isinstance(origine, Origine):
        raise ReferentielInvalide("Le nom et l'origine de la marque sont obligatoires.")
    return _enregistrer(lambda: Marque.objects.create(code=code, nom=nom[:100], origine=origine))
