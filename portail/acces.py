"""Contrôle d'accès du portail : qui peut voir quoi.

Règle d'or (§6.4 du document de passation) : le membre vient TOUJOURS de request.user.membre,
jamais d'un paramètre d'URL ou de formulaire. Les décorateurs ci-dessous vérifient le rôle métier ;
la base PostgreSQL (rôle + sécurité par ligne, posés par le middleware) reste la vraie barrière.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

ROLES = {"MEMBRE", "GESTION", "BUREAU", "TECHNIQUE"}


def role_requis(*roles):
    """Limite une vue aux rôles métier donnés (l'utilisateur doit déjà être connecté)."""
    roles = set(roles)
    if not roles <= ROLES:
        raise ValueError(f"Rôle inconnu dans {roles}")

    def decorateur(vue):
        @wraps(vue)
        @login_required
        def enveloppe(request, *args, **kwargs):
            if request.user.role_metier not in roles:
                raise PermissionDenied("Cette page n'est pas accessible avec votre rôle.")
            return vue(request, *args, **kwargs)
        return enveloppe
    return decorateur


membre_requis = role_requis("MEMBRE")
gestion_requise = role_requis("GESTION", "TECHNIQUE")
bureau_requis = role_requis("BUREAU")
technique_requis = role_requis("TECHNIQUE")


def membre_courant(request):
    """Le membre (société) du compte connecté. Lève PermissionDenied si le compte n'est pas un compte MEMBRE."""
    if request.user.role_metier != "MEMBRE" or request.user.membre_id is None:
        raise PermissionDenied("Ce compte n'est rattaché à aucune société membre.")
    return request.user.membre


def accueil_selon_role(user):
    """Nom d'URL de la page d'accueil de chaque rôle."""
    return {"MEMBRE": "portail:accueil", "GESTION": "portail:gestion_tableau", "TECHNIQUE": "portail:gestion_tableau",
            "BUREAU": "portail:bureau_tableau"}.get(getattr(user, "role_metier", None), "portail:connexion")
