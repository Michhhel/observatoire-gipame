"""
Bascule de rôle PostgreSQL par requête (À PLACER EN DERNIER dans MIDDLEWARE).

L'application se connecte avec gipame_app, qui n'a aucun droit sur les tables métier. Pour chaque
requête authentifiée, ce middleware ouvre une transaction, bascule vers le rôle correspondant au rôle
métier de l'utilisateur et pose le contexte (membre, utilisateur) lu par la sécurité par ligne.
Toute la requête s'exécute dans cette transaction : si la vue renvoie une erreur serveur (5xx), on
annule ce qui a été écrit.

Exception : l'administration Django (/admin/) n'est utilisable qu'avec la connexion propriétaire
(outil de secours, voir §10 du document de passation) ; on n'y bascule pas de rôle pour un superuser.

STATUT : activé dans settings.MIDDLEWARE ; exercé par les tests du portail (portail/tests/).
"""
from django.db import transaction

from .contexte import en_role

# Chemins servis sans bascule de rôle : ils ne touchent que les tables techniques (sessions, comptes).
CHEMINS_TECHNIQUES = ("/deconnexion/",)
# Chemins qui ne doivent jamais toucher la base (sonde de disponibilité : laisse la base Neon s'endormir).
CHEMINS_SANS_BASE = ("/sante/",)

ROLES_DB = {
    "MEMBRE": "gipame_membre",
    "GESTION": "gipame_gestion",
    "TECHNIQUE": "gipame_gestion",
    "BUREAU": "gipame_bureau",
}


class ContexteBaseDeDonnees:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in CHEMINS_SANS_BASE:
            return self.get_response(request)
        user = getattr(request, "user", None)
        role = ROLES_DB.get(getattr(user, "role_metier", None)) if user and user.is_authenticated else None
        if role is None or request.path in CHEMINS_TECHNIQUES or (request.path.startswith("/admin/") and user.is_superuser):
            return self.get_response(request)
        with en_role(role, membre_id=user.membre_id, utilisateur_id=user.pk):
            reponse = self.get_response(request)
            if reponse.status_code >= 500:
                transaction.set_rollback(True)
            return reponse
