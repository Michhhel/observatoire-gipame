"""Faits lus EN DIRECT à chaque question : la Roue de Secours ne devient jamais obsolète sur ce qui change avec le
temps (mois à déclarer, dates limites, publications, grille des segments, paramètres, état de la déclaration).

Toutes les lectures se font avec les droits de la personne connectée (rôle PostgreSQL posé par le middleware pour la
page en cours) et ne portent que sur des statuts, des dates et des libellés : JAMAIS une quantité.
Chaque bloc est protégé : s'il échoue, il est simplement omis (point de sauvegarde), la réponse continue.
"""
import logging
from datetime import date, timedelta

from django.db import DatabaseError, transaction
from django.urls import Resolver404, resolve

from portail import formats

from .connaissances import Section

journal = logging.getLogger(__name__)

ROLES_LIBELLES = {
    "MEMBRE": "membre déclarant (une société membre du GIPAME)",
    "GESTION": "gestion (secrétariat du GIPAME)",
    "TECHNIQUE": "administrateur du portail (droits de la gestion + comptes)",
    "BUREAU": "bureau du GIPAME (président, vice-président ou délégué général)",
}

PAGES = {
    "accueil": "Accueil du membre", "assistant": "Déclarer (télécharger / déposer le gabarit)",
    "rapport": "Rapport de contrôle d'un fichier déposé", "confirmation": "Confirmation de soumission",
    "historique": "Historique", "mon_annee": "Mon année", "marche": "Le marché", "mes_produits": "Mes produits",
    "gestion_tableau": "Suivi des dépôts", "gestion_publications": "Publications", "gestion_propositions": "Propositions",
    "gestion_proposition": "Traitement d'une proposition", "gestion_membres": "Membres", "gestion_membre": "Fiche d'un membre",
    "gestion_membre_nouveau": "Ajout d'un membre", "gestion_catalogue": "Catalogue", "gestion_demandes": "Accès exceptionnel",
    "gestion_lecture_acces": "Lecture exceptionnelle", "bureau_tableau": "Le marché (bureau)",
    "bureau_journal": "Journal des accès", "bureau_approbations": "Approbations", "bureau_approbation": "Examen d'une demande",
    "admin_comptes": "Comptes", "admin_compte": "Fiche d'un compte", "aide": "Aide", "confidentialite": "Charte de confidentialité",
    "mot_de_passe_change": "Changer mon mot de passe",
}


def page_libelle(chemin):
    """Chemin envoyé par le navigateur → libellé de page connu (jamais le chemin lui-même : il peut contenir un id)."""
    if not isinstance(chemin, str) or not chemin.startswith("/") or len(chemin) > 200:
        return None
    try:
        return PAGES.get(resolve(chemin.split("?")[0]).url_name)
    except Resolver404:
        return None


def _delai(limite, aujourd_hui=None):
    n = formats.jours_restants(limite, aujourd_hui)
    if n > 1:
        return f"dans {n} jours"
    if n == 1:
        return "demain"
    if n == 0:
        return "aujourd'hui"
    return f"dépassée depuis {-n} jour{'s' if n < -1 else ''}"


def _protege(fonction, *args):
    try:
        with transaction.atomic():
            return fonction(*args)
    except (DatabaseError, LookupError, ValueError, TypeError, AttributeError) as e:
        journal.warning("Roue de Secours : fait ignoré (%s : %s)", fonction.__name__, type(e).__name__)
        return None


# ------------------------------------------------------------------------------------------------ faits communs
def _calendrier(params, aujourd_hui):
    mois = formats.premier_du_mois(aujourd_hui, decalage=-1)
    limite = formats.fin_du_mois(mois) + timedelta(days=int(params.get("jours_grace_depot") or 10))
    courant = formats.premier_du_mois(aujourd_hui)
    suivant = formats.premier_du_mois(courant + timedelta(days=32))
    texte = (f"Aujourd'hui : {formats.date_longue(aujourd_hui)}. Mois à déclarer en ce moment : {formats.mois_long(mois)}, "
             f"date limite le {formats.date_longue(limite)} ({_delai(limite, aujourd_hui)}). "
             f"Le mois en cours ({formats.mois_long(courant)}) se déclare à partir du {formats.date_longue(suivant)}. "
             f"On peut corriger jusqu'à 36 mois en arrière.")
    return Section("calendrier", "Calendrier de la collecte", "", texte, frozenset({"TOUS"}), "/declarer/",
                   ("Quel mois déclarer ?", "Quelle est la date limite ?", "Quand puis-je déclarer ce mois-ci ?"), True)


def _publications(params, aujourd_hui):
    from collecte.models import Publication
    derniere = Publication.objects.order_by("-mois", "-version").first()
    if derniere is None:
        texte = "Aucune publication du marché n'a encore été calculée."
    else:
        definitive = Publication.objects.filter(statut="DEFINITIVE").order_by("-mois").values_list("mois", flat=True).first()
        texte = (f"Dernière publication du marché : {formats.mois_long(derniere.mois)}, "
                 f"{derniere.get_statut_display().lower()} (version {derniere.version}, calculée le "
                 f"{formats.date_longue(derniere.calculee_le.date())}).")
        if definitive:
            texte += f" Dernier mois publié en définitif : {formats.mois_long(definitive)}."
    return Section("publications-etat", "État des publications du marché", "", texte, frozenset({"TOUS"}), "/le-marche/",
                   ("Le marché est-il publié ?", "Quand sortent les chiffres du marché ?", "Dernière publication"), False)


def _grille(params, aujourd_hui):
    from collecte.models import Segment
    segments = (Segment.objects.filter(categorie__segmentation__statut="COURANTE").select_related("categorie")
                .order_by("categorie__ordre", "ordre"))
    par_categorie = {}
    for s in segments:
        libelle = s.libelle + (f" ({s.definition.strip()})" if s.definition.strip() else "")
        par_categorie.setdefault(s.categorie.libelle, []).append(libelle)
    if not par_categorie:
        return None
    texte = "Grille actuelle des segments (types de véhicules) : " + " ; ".join(
        f"{cat} : {', '.join(libs)}" for cat, libs in par_categorie.items()) + "."
    texte += " Le classement d'un produit dans un segment est fait par le GIPAME quand il valide le produit."
    return Section("grille-segments", "Grille des segments", "", texte, frozenset({"TOUS"}), "/le-marche/",
                   ("Dans quel segment est mon véhicule ?", "Quels sont les segments ?", "Qu'est-ce qu'un segment ?",
                    "Types de véhicules"), False)


def _listes(params, aujourd_hui):
    from collecte.models import Boite, Energie
    energies = ", ".join(Energie.objects.order_by("libelle").values_list("libelle", flat=True))
    boites = ", ".join(Boite.objects.order_by("libelle").values_list("libelle", flat=True))
    texte = f"Énergies proposées dans l'onglet AJOUTS : {energies}. Boîtes : {boites} (facultatif)."
    return Section("listes-ajouts", "Listes de l'onglet AJOUTS", "", texte, frozenset({"MEMBRE"}), "/mes-produits/",
                   ("Quelles énergies puis-je choisir ?", "Électrique hybride", "Boîte de vitesses"), False)


def sections_du_jour(role, params, aujourd_hui=None):
    """Sections dynamiques, ajoutées aux fiches pour la recherche de cette question."""
    aujourd_hui = aujourd_hui or date.today()
    blocs = [_protege(f, params, aujourd_hui) for f in (_calendrier, _publications, _grille, _listes)]
    return [b for b in blocs if b is not None and b.visible_par(role)]


def parametres_securite(role):
    """Seuils de confidentialité et d'approbation : lus en direct si le rôle y a droit (gestion, bureau)."""
    if role not in {"GESTION", "TECHNIQUE", "BUREAU"}:
        return {}

    def lire():
        from collecte.models import ParametreSysteme
        return dict(ParametreSysteme.objects.filter(cle__in=[
            "confidentialite_min_contributeurs", "confidentialite_dominance_pct", "seuil_approbations_acces",
            "couverture_min_publication_pct"]).values_list("cle", "valeur"))
    return _protege(lire) or {}


# ------------------------------------------------------------------------------------------------ situation
def _situation_membre(user, params):
    from portail.vues.membre import _situation  # même calcul que la page d'accueil (source unique)
    mois = formats.premier_du_mois(decalage=-1)
    s = _situation(user.membre, mois, params)
    if s["etat"] == "SOUMISE":
        etat = f"soumise (version {s['soumise'].version}, le {formats.date_longue(s['soumise'].soumise_le.date())})" \
            if getattr(s["soumise"], "soumise_le", None) else f"soumise (version {s['soumise'].version})"
    elif s["etat"] == "BROUILLON":
        etat = "fichier déposé et accepté, mais déclaration PAS ENCORE SOUMISE (brouillon : il reste à cliquer sur « Soumettre »)"
    else:
        etat = "pas encore déposée" if s["attendue"] else "non requise pour ce mois (pas de déclaration attendue)"
    lignes = [f"Déclaration {formats.de_mois(mois)} : {etat}."]
    if s["attendue"] and s["etat"] != "SOUMISE":
        lignes.append(f"Date limite : {formats.date_longue(s['date_limite'])} ({_delai(s['date_limite'])})"
                      + (" — EN RETARD." if s["en_retard"] else "."))
    retard = []
    for i in range(2, 13):
        m = formats.premier_du_mois(decalage=-i)
        si = _situation(user.membre, m, params)
        if si["attendue"] and si["etat"] != "SOUMISE":
            retard.append(formats.mois_long(m))
    if retard:
        suite = f" et {len(retard) - 6} autre(s)" if len(retard) > 6 else ""
        lignes.append("Mois précédents attendus mais non soumis : " + ", ".join(retard[:6]) + suite + ".")
    return lignes


def _situation_gestion(user, params):
    from collecte.models import Produit
    from portail.vues.gestion import _suivi
    mois = formats.premier_du_mois(decalage=-1)
    lignes = [l for l in _suivi() if l["mois"] == mois]
    recues = sum(1 for l in lignes if l["statut_depot"] == "SOUMISE")
    retard = sum(1 for l in lignes if l["en_retard"])
    propositions = Produit.objects.filter(statut="PROPOSE").count()
    return [f"Collecte {formats.de_mois(mois)} : {recues} déclaration(s) soumise(s) sur {len(lignes)} attendue(s), "
            f"{retard} membre(s) en retard.", f"Produits proposés en attente de traitement : {propositions}."]


def _situation_bureau(user, params):
    from collecte.models import DemandeAccesExceptionnel
    from portail.vues.bureau import _poste_du
    poste = _poste_du(user)
    seuil = int(parametres_securite("BUREAU").get("seuil_approbations_acces") or 2)
    a_examiner = 0
    for d in DemandeAccesExceptionnel.objects.prefetch_related("approbations").order_by("-cree_le")[:50]:
        decisions = list(d.approbations.all())
        accords = sum(1 for a in decisions if a.decision == "APPROUVEE")
        deja = poste is not None and any(a.poste_id == poste.id for a in decisions)
        if accords < seuil and not deja:
            a_examiner += 1
    lignes = [f"Poste au bureau : {poste.libelle if poste else 'aucun poste rattaché (consultation seulement, pas d’approbation)'}."]
    if poste:
        lignes.append(f"Demandes d'accès exceptionnel en attente de votre décision : {a_examiner}.")
    return lignes


def situation(user, params):
    """Lignes « situation de l'utilisateur » (statuts et dates seulement). Liste vide si rien à dire."""
    role = user.role_metier
    fonction = {"MEMBRE": _situation_membre, "GESTION": _situation_gestion, "TECHNIQUE": _situation_gestion,
                "BUREAU": _situation_bureau}.get(role)
    if fonction is None or (role == "MEMBRE" and user.membre_id is None):
        return []
    return _protege(fonction, user, params) or []
