"""Deux points d'entrée JSON, réservés aux comptes connectés :
POST /roue-de-secours/question/  → réponse diffusée (lignes JSON, voir conversation.py)
POST /roue-de-secours/avis/      → enregistre un avis anonyme (Utile / À revoir / question sans réponse)

La personne vient TOUJOURS de request.user (jamais du corps de la requête) ; le corps ne porte que la question, les
derniers messages de la conversation (gardés dans l'onglet du navigateur) et la page affichée.
"""
import json

from django.core.cache import cache
from django.db import connection
from django.http import Http404, JsonResponse, StreamingHttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from portail.acces import ROLES

from . import conversation, faits, reglages


def _erreur(message, statut):
    return JsonResponse({"erreur": message}, status=statut)


def _quota(cle, limite, duree):
    """Compteur simple (cache du processus). Renvoie False si la limite est atteinte."""
    if cache.add(cle, 1, duree):
        return True
    try:
        return cache.incr(cle) <= limite
    except ValueError:  # clé expirée entre-temps
        cache.set(cle, 1, duree)
        return True


def _corps(request):
    if not reglages.active():
        raise Http404
    if not request.user.is_authenticated or request.user.role_metier not in ROLES:
        return None, _erreur("Votre session a expiré : reconnectez-vous pour utiliser la Roue de Secours.", 401)
    if len(request.body) > reglages.CORPS_MAX:
        return None, _erreur("Message trop long.", 400)
    try:
        donnees = json.loads(request.body or b"{}")
    except ValueError:
        return None, _erreur("Requête illisible.", 400)
    if not isinstance(donnees, dict):
        return None, _erreur("Requête illisible.", 400)
    return donnees, None


def _historique(brut):
    if not isinstance(brut, list):
        return []
    propre = []
    for m in brut[-reglages.HISTORIQUE_MAX:]:
        if isinstance(m, dict) and m.get("role") in {"user", "assistant"} and isinstance(m.get("texte"), str):
            propre.append({"role": m["role"], "texte": m["texte"][: reglages.HISTORIQUE_TEXTE_MAX]})
    return propre


@never_cache
@require_POST
def question(request):
    donnees, erreur = _corps(request)
    if erreur:
        return erreur
    texte = donnees.get("question")
    if not isinstance(texte, str) or not texte.strip():
        return _erreur("Écrivez votre question.", 400)
    texte = texte.strip()
    if len(texte) > reglages.QUESTION_MAX:
        return _erreur(f"Votre question est trop longue ({len(texte)} caractères, {reglages.QUESTION_MAX} au plus).", 400)
    uid = request.user.pk
    if not _quota(f"roue:q10:{uid}", reglages.QUOTA_10_MIN, 600) or not _quota(f"roue:qj:{uid}", reglages.QUOTA_JOUR, 86400):
        return _erreur("Vous avez posé beaucoup de questions en peu de temps : patientez quelques minutes. "
                       "La page Aide reste disponible.", 429)
    preparation = conversation.preparer(request.user, texte, _historique(donnees.get("historique")), donnees.get("page"))
    reponse = StreamingHttpResponse(conversation.flux(preparation), content_type="application/x-ndjson; charset=utf-8")
    reponse["X-Accel-Buffering"] = "no"  # pas de mise en mémoire tampon par un relais : le texte arrive au fil de l'eau
    return reponse


@never_cache
@require_POST
def avis(request):
    donnees, erreur = _corps(request)
    if erreur:
        return erreur
    note = donnees.get("note")
    question_texte = donnees.get("question")
    if note not in (-1, 0, 1) or not isinstance(question_texte, str) or not question_texte.strip():
        return _erreur("Avis incomplet.", 400)
    if not _quota(f"roue:avis:{request.user.pk}", reglages.QUOTA_AVIS_JOUR, 86400):
        return _erreur("Merci, nous avons déjà reçu beaucoup d'avis de votre part aujourd'hui.", 429)

    def champ(nom, longueur):
        valeur = donnees.get(nom)
        return valeur.strip()[:longueur] if isinstance(valeur, str) else ""

    sources = donnees.get("sources")
    sources = ", ".join(str(s)[:80] for s in sources[:5]) if isinstance(sources, list) else ""
    mode = champ("mode", 12) if champ("mode", 12) in {"ia", "hors_ligne"} else ""
    with connection.cursor() as cur:
        # INSERT sans RETURNING : les rôles du portail n'ont que le droit d'ajouter (pas de lire) cette table.
        cur.execute(
            "INSERT INTO roue_de_secours_avis (cree_le, role, page, question, reponse, sources, mode, note, commentaire) "
            "VALUES (now(), %s, %s, %s, %s, %s, %s, %s, %s)",
            [request.user.role_metier, (faits.page_libelle(donnees.get("page")) or "")[:80],
             question_texte.strip()[: reglages.QUESTION_MAX], champ("reponse", 6000), sources[:400], mode, note,
             champ("commentaire", 1000)])
    return JsonResponse({"ok": True})
