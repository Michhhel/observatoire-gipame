"""Déroulé d'une question : préparer (base de données, avec les droits de la personne) puis diffuser (sans base).

preparer() s'exécute DANS la requête, sous le rôle PostgreSQL posé par le middleware : paramètres publics, faits du
jour, situation, recherche des passages. Tout ce qui sera envoyé au fournisseur est fixé à cette étape.

flux() s'exécute APRÈS la fin de la transaction (réponse diffusée au fil de l'eau) : il ne touche plus la base,
il ne fait qu'appeler le fournisseur et transmettre au navigateur des lignes JSON :
  {"t": "sources", "sources": [...]}      dès le début : les fiches retrouvées
  {"t": "texte", "d": "…"}                morceaux de la réponse
  {"t": "mode", "mode": "hors_ligne", "raison": "…"}   bascule automatique si le service d'IA fait défaut
  {"t": "erreur", "message": "…"}         réponse interrompue
  {"t": "fin", "mode": "ia"|"hors_ligne", "sans_fiche": bool}
"""
import json
import logging
import time
from datetime import date
from dataclasses import dataclass

from collecte.contexte import parametres_publics
from portail import formats

from . import consignes, faits, reglages
from .connaissances import sections, valeurs
from .fournisseurs import ErreurFournisseur, HorsLigne, Requete, construire
from .recherche import Index

journal = logging.getLogger(__name__)


@dataclass
class Preparation:
    requete: Requete
    sources: list
    sans_fiche: bool


def preparer(user, question, historique, page_chemin):
    role = user.role_metier
    params = dict(parametres_publics())
    params.update(faits.parametres_securite(role))
    vals = valeurs(params)
    du_jour = faits.sections_du_jour(role, params)
    calendrier = next((s for s in du_jour if s.fiche_id == "calendrier"), None)
    toutes = [s for s in sections() if s.visible_par(role)] + [s for s in du_jour if s is not calendrier]
    permanentes = [s for s in toutes if s.toujours]
    precedente = next((m["texte"] for m in reversed(historique) if m.get("role") == "user"), "")
    resultats = Index(toutes).chercher(question, role, k=5, contexte=precedente)
    retrouves = [r.section for r in resultats]
    variables = [s for s in retrouves if not s.toujours]
    page = faits.page_libelle(page_chemin)
    situation = faits.situation(user, params)
    fixe = consignes.bloc_fixe(role, permanentes, vals)
    variable = consignes.bloc_variable(role, page, situation, variables, vals,
                                       formats.date_longue(date.today()), calendrier)
    messages = list(historique) + [{"role": "user", "texte": question}]
    sources, vus = [], set()
    for s in retrouves:
        if s.fiche_id in vus or len(sources) >= 3:
            continue
        vus.add(s.fiche_id)
        sources.append({"titre": s.titre_fiche, "lien": s.lien or ""})
    return Preparation(Requete(fixe, variable, messages, retrouves, vals), sources, sans_fiche=not variables)


def _ligne(objet):
    return (json.dumps(objet, ensure_ascii=False) + "\n").encode("utf-8")


def flux(preparation, fournisseur=None):
    fournisseur = fournisseur or construire()
    yield _ligne({"t": "sources", "sources": preparation.sources, "sans_fiche": preparation.sans_fiche})
    debut, recu, mode = time.monotonic(), False, "ia" if fournisseur.est_ia else "hors_ligne"
    try:
        for morceau in fournisseur.diffuser(preparation.requete):
            if morceau:
                recu = True
                yield _ligne({"t": "texte", "d": morceau})
    except ErreurFournisseur as e:
        if recu:
            yield _ligne({"t": "erreur", "message": "La réponse a été interrompue. Vous pouvez reposer la question."})
            yield _ligne({"t": "fin", "mode": mode, "sans_fiche": preparation.sans_fiche})
            return
        # Rien reçu : bascule silencieuse sur les fiches (le portail n'est jamais bloqué par le service d'IA).
        mode = "hors_ligne"
        yield _ligne({"t": "mode", "mode": "hors_ligne", "raison": e.raison})
        for morceau in HorsLigne().diffuser(preparation.requete):
            yield _ligne({"t": "texte", "d": morceau})
    except Exception:  # noqa: BLE001 — une panne imprévue ne doit jamais casser la page
        journal.exception("Roue de Secours : erreur inattendue pendant la réponse")
        yield _ligne({"t": "erreur", "message": "Une erreur est survenue. Réessayez dans un instant."})
    finally:
        # Journal technique : durée, mode, jetons. JAMAIS le texte de la question ni de la réponse.
        journal.info("Roue de Secours : réponse %s en %.1f s (fournisseur %s, jetons %s)", mode,
                     time.monotonic() - debut, fournisseur.nom, fournisseur.usage or "-")
    yield _ligne({"t": "fin", "mode": mode, "sans_fiche": preparation.sans_fiche})
