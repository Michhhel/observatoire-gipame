"""Réglages de la Roue de Secours (variables d'environnement lues dans config/settings.py → ROUE_DE_SECOURS).

Fournisseur « auto » : Anthropic si une clé est fournie sans adresse d'API, « compatible OpenAI » si une adresse est
fournie (OpenAI, Mistral, Groq, Ollama…), sinon le mode hors ligne (réponses extraites des fiches, sans IA).
"""
from django.conf import settings

MODELES_PAR_DEFAUT = {"anthropic": "claude-haiku-5-5"}

# Garde-fous d'usage (coût, abus). Par compte et par processus du serveur.
QUESTION_MAX = 800          # caractères
HISTORIQUE_MAX = 6          # derniers messages renvoyés au modèle (3 échanges)
HISTORIQUE_TEXTE_MAX = 1500 # caractères par message d'historique
CORPS_MAX = 24_000          # octets du corps JSON
QUOTA_10_MIN = 20
QUOTA_JOUR = 150
QUOTA_AVIS_JOUR = 40
REPONSE_MAX_JETONS = 700
DELAI_FOURNISSEUR = 30      # secondes sans recevoir de données avant d'abandonner


def _r():
    return getattr(settings, "ROUE_DE_SECOURS", {}) or {}


def active():
    return bool(_r().get("ACTIVE", True))


def fournisseur():
    r = _r()
    choix = (r.get("FOURNISSEUR") or "auto").strip().lower()
    if choix == "auto":
        if r.get("CLE_API") and not r.get("URL_API"):
            return "anthropic"
        if r.get("URL_API"):
            return "openai"
        return "hors_ligne"
    if choix not in {"anthropic", "openai", "hors_ligne"}:
        raise ValueError(f"GIPAME_ROUE_FOURNISSEUR inconnu : {choix}")
    return choix


def modele():
    return (_r().get("MODELE") or MODELES_PAR_DEFAUT.get(fournisseur(), "")).strip()


def cle_api():
    return _r().get("CLE_API", "")


def url_api():
    return (_r().get("URL_API") or "").rstrip("/")


def prestataire():
    """Nom affiché dans la charte de confidentialité."""
    nom = (_r().get("PRESTATAIRE") or "").strip()
    if nom:
        return nom
    return {"anthropic": "Anthropic (États-Unis)", "openai": "le prestataire d'IA configuré",
            "hors_ligne": ""}[fournisseur()]
