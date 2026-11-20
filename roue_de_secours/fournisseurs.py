"""Fournisseurs de réponses : un modèle d'IA par API (Anthropic, ou tout service « compatible OpenAI » : OpenAI, Mistral,
Groq, Ollama…), ou le mode hors ligne (extraits des fiches, sans IA).

Aucune dépendance ajoutée : appels HTTPS en streaming avec la bibliothèque standard (urllib), qui respecte les
variables HTTPS_PROXY. Changer de fournisseur ou de modèle = changer deux variables d'environnement.

Robustesse sur la durée : si le fournisseur refuse la clé, a retiré le modèle, ne répond plus ou disparaît, l'appel
lève ErreurFournisseur et la conversation bascule toute seule sur le mode hors ligne (voir conversation.py).
"""
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import reglages

journal = logging.getLogger(__name__)


class ErreurFournisseur(Exception):
    """Le fournisseur n'a pas pu répondre. `raison` est affichable (jamais de détail technique ni de clé)."""

    def __init__(self, raison, technique=""):
        super().__init__(raison)
        self.raison, self.technique = raison, technique


@dataclass
class Requete:
    systeme_fixe: str
    systeme_variable: str
    messages: list              # [{"role": "user"|"assistant", "texte": "..."}], le dernier est la question
    passages: list = field(default_factory=list)   # sections retrouvées (pour le mode hors ligne)
    vals: dict = field(default_factory=dict)       # valeurs des variables {{…}}
    max_jetons: int = reglages.REPONSE_MAX_JETONS


def _messages_alternes(messages):
    """Les API exigent : premier message de l'utilisateur, puis alternance stricte."""
    propres = []
    for m in messages:
        role = "assistant" if m.get("role") == "assistant" else "user"
        texte = (m.get("texte") or "").strip()
        if not texte:
            continue
        if propres and propres[-1]["role"] == role:
            propres[-1]["content"] += "\n\n" + texte
        else:
            propres.append({"role": role, "content": texte})
    while propres and propres[0]["role"] == "assistant":
        propres.pop(0)
    return propres


def _lignes_sse(reponse):
    """Itère sur les lignes « data: … » d'un flux Server-Sent Events."""
    for brut in reponse:
        ligne = brut.decode("utf-8", errors="replace").rstrip("\r\n")
        if ligne.startswith("data:"):
            yield ligne[5:].strip()


def _ouvrir(url, corps, entetes):
    requete = urllib.request.Request(url, data=json.dumps(corps).encode("utf-8"), method="POST",
                                     headers={"content-type": "application/json", "accept": "text/event-stream", **entetes})
    try:
        return urllib.request.urlopen(requete, timeout=reglages.DELAI_FOURNISSEUR)
    except urllib.error.HTTPError as e:
        try:
            detail = e.read(2000).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 — le détail n'est qu'informatif
            detail = ""
        raisons = {400: "requête refusée par le service d'IA", 401: "clé d'API refusée", 403: "accès refusé par le service d'IA",
                   404: "modèle ou adresse d'API introuvable (modèle retiré ?)", 429: "service d'IA saturé ou quota atteint"}
        raison = raisons.get(e.code, "service d'IA indisponible")
        journal.error("Roue de Secours : le fournisseur a répondu HTTP %s (%s)", e.code, raison)
        raise ErreurFournisseur(raison, f"HTTP {e.code} {detail[:300]}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        journal.error("Roue de Secours : fournisseur injoignable (%s)", type(e).__name__)
        raise ErreurFournisseur("service d'IA injoignable", type(e).__name__)


class Fournisseur:
    nom = "?"
    est_ia = True

    def __init__(self, modele="", cle="", url=""):
        self.modele, self.cle, self.url = modele, cle, url
        self.usage = {}

    def diffuser(self, requete):
        """Génère des morceaux de texte de la réponse. Lève ErreurFournisseur si rien ne peut être produit."""
        raise NotImplementedError


class Anthropic(Fournisseur):
    nom = "anthropic"
    URL = "https://api.anthropic.com/v1/messages"
    VERSION_API = "2023-06-01"

    def diffuser(self, requete):
        if not self.cle:
            raise ErreurFournisseur("aucune clé d'API configurée")
        corps = {
            "model": self.modele, "max_tokens": requete.max_jetons, "temperature": 0.3, "stream": True,
            # Bloc fixe marqué « en cache » : relu à prix réduit tant qu'il ne change pas.
            "system": [{"type": "text", "text": requete.systeme_fixe, "cache_control": {"type": "ephemeral"}},
                       {"type": "text", "text": requete.systeme_variable}],
            "messages": _messages_alternes(requete.messages),
        }
        reponse = _ouvrir(self.url or self.URL, corps, {"x-api-key": self.cle, "anthropic-version": self.VERSION_API})
        with reponse:
            for donnees in _lignes_sse(reponse):
                try:
                    evenement = json.loads(donnees)
                except ValueError:
                    continue
                genre = evenement.get("type")
                if genre == "content_block_delta" and evenement.get("delta", {}).get("type") == "text_delta":
                    yield evenement["delta"].get("text", "")
                elif genre == "message_start":
                    self.usage.update(evenement.get("message", {}).get("usage", {}))
                elif genre == "message_delta":
                    self.usage.update(evenement.get("usage", {}))
                elif genre == "error":
                    message = evenement.get("error", {}).get("type", "erreur")
                    journal.error("Roue de Secours : erreur en cours de réponse (%s)", message)
                    raise ErreurFournisseur("le service d'IA a interrompu la réponse", message)
                elif genre == "message_stop":
                    return


class CompatibleOpenAI(Fournisseur):
    """Toute API « chat/completions » : OpenAI, Mistral (https://api.mistral.ai/v1), Groq, Ollama local…"""
    nom = "openai"

    def diffuser(self, requete):
        if not self.url:
            raise ErreurFournisseur("aucune adresse d'API configurée")
        messages = [{"role": "system", "content": requete.systeme_fixe + "\n\n" + requete.systeme_variable}]
        messages += _messages_alternes(requete.messages)
        corps = {"model": self.modele, "messages": messages, "stream": True, "max_tokens": requete.max_jetons,
                 "temperature": 0.3}
        entetes = {"authorization": f"Bearer {self.cle}"} if self.cle else {}
        reponse = _ouvrir(self.url + "/chat/completions", corps, entetes)
        with reponse:
            for donnees in _lignes_sse(reponse):
                if donnees == "[DONE]":
                    return
                try:
                    evenement = json.loads(donnees)
                except ValueError:
                    continue
                if evenement.get("error"):
                    raise ErreurFournisseur("le service d'IA a interrompu la réponse", str(evenement["error"])[:200])
                for choix in evenement.get("choices", []):
                    morceau = (choix.get("delta") or {}).get("content")
                    if morceau:
                        yield morceau
                if evenement.get("usage"):
                    self.usage.update(evenement["usage"])


class HorsLigne(Fournisseur):
    """Sans IA : restitue les passages les plus pertinents, tels qu'écrits dans les fiches. Toujours disponible."""
    nom = "hors_ligne"
    est_ia = False

    def diffuser(self, requete):
        from .connaissances import remplir
        passages = requete.passages[:2]
        if not passages:
            yield ("Je n'ai pas trouvé de réponse à cette question dans l'aide du portail. Vous pouvez reformuler avec "
                   f"d'autres mots, consulter la page [Aide](/aide/) ou écrire à {requete.vals.get('contact', 'le secrétariat du GIPAME')}.")
            return
        yield "Voici ce que dit l'aide du portail :\n\n"
        for i, p in enumerate(passages):
            titre = p.titre or p.titre_fiche
            yield ("\n\n" if i else "") + f"**{titre}**\n\n{remplir(p.texte, requete.vals)}"


def construire(nom=None):
    nom = nom or reglages.fournisseur()
    if nom == "anthropic":
        return Anthropic(reglages.modele(), reglages.cle_api(), reglages.url_api())
    if nom == "openai":
        return CompatibleOpenAI(reglages.modele(), reglages.cle_api(), reglages.url_api())
    return HorsLigne()
