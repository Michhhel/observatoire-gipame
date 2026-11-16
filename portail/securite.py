"""Protection de la connexion : blocage temporaire après des échecs répétés.

Règle (décision Q2-d) : 5 échecs pour un même identifiant en 15 minutes → nouvelle tentative refusée
pendant 15 minutes, que le compte existe ou non (on ne révèle jamais si une adresse est connue).
Tout est journalisé dans portail_tentativeconnexion (ajout seulement).
"""
from datetime import timedelta

from django.utils import timezone

from .models import TentativeConnexion

MAX_ECHECS = 5
FENETRE = timedelta(minutes=15)


def normaliser_identifiant(valeur):
    return (valeur or "").strip().lower()[:254]


def adresse_ip(request):
    """Adresse du client ; derrière un reverse proxy, X-Forwarded-For doit être posé par le proxy seul."""
    transmis = request.META.get("HTTP_X_FORWARDED_FOR")
    if transmis:
        return transmis.split(",")[0].strip()[:45] or None
    return request.META.get("REMOTE_ADDR") or None


def est_bloque(identifiant):
    """Vrai si l'identifiant a cumulé MAX_ECHECS échecs dans la fenêtre, sans réussite depuis."""
    depuis = timezone.now() - FENETRE
    recentes = list(TentativeConnexion.objects.filter(identifiant=identifiant, cree_le__gte=depuis)
                    .order_by("-cree_le").values_list("reussie", flat=True)[:MAX_ECHECS])
    return len(recentes) >= MAX_ECHECS and not any(recentes)


def enregistrer(identifiant, reussie, request=None):
    TentativeConnexion.objects.create(identifiant=identifiant, reussie=reussie,
                                      adresse_ip=adresse_ip(request) if request else None)
