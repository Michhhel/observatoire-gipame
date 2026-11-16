"""Mode démonstration (GIPAME_MODE_DEMO=1) : bandeau sur toutes les pages et comptes d'essai sur la page de connexion.

Les comptes listés ici sont ceux créés par seed_demo puis comptes_demo (mot de passe commun « demo-2026 »).
En démonstration, ces comptes ne peuvent pas être désactivés ni recevoir un nouveau lien d'activation :
un visiteur ne doit pas pouvoir bloquer l'essai des suivants.
"""
from django.conf import settings

DOMAINE = "@demo.gipame.ci"
MOT_DE_PASSE = "demo-2026"
COMPTES = [
    {"email": "user_a1@demo.gipame.ci", "role": "Membre", "detail": "Alpha Motors : déclarer ses ventes, suivre son année"},
    {"email": "user_b1@demo.gipame.ci", "role": "Membre", "detail": "Beta Distribution : un autre membre, cloisonné"},
    {"email": "gestionnaire@demo.gipame.ci", "role": "Gestion", "detail": "Suivi des dépôts, publications, produits"},
    {"email": "president@demo.gipame.ci", "role": "Bureau", "detail": "Tableau du marché, approbations"},
    {"email": "technicien@demo.gipame.ci", "role": "Administration", "detail": "Comptes et accès"},
]


def actif():
    return bool(getattr(settings, "MODE_DEMO", False))


def compte_protege(email):
    return actif() and (email or "").lower().endswith(DOMAINE)


def contexte(request):
    if not actif():
        return {"mode_demo": False}
    return {"mode_demo": True, "comptes_demo": COMPTES, "mot_de_passe_demo": MOT_DE_PASSE}
