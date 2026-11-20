"""Base de connaissances : lecture, contrôle et découpage des fiches Markdown (dossier connaissances/).

Une fiche = un en-tête (clé: valeur) + un texte découpé en sections « ## ». Chaque section est un passage que la
recherche peut retrouver. Une fiche est aussi générée depuis le code : les messages du rapport de contrôle
(portail/rapport.py), pour que l'aide et l'application ne divergent jamais.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent / "connaissances"
ROLES = {"MEMBRE", "GESTION", "BUREAU", "TECHNIQUE"}
CHAMPS_REQUIS = ("id", "titre", "roles", "mise_a_jour")
VARIABLES = {"jours_grace_depot", "definition_vente", "contact", "import_quantite_max", "import_max_ajouts",
             "import_taille_max_ko", "import_variation_alerte_pct", "import_variation_min_unites",
             "min_contributeurs", "dominance_pct", "seuil_approbations", "couverture_min_pct"}
# Paramètres de sécurité : lus en direct quand le rôle y a droit (gestion, bureau), sinon ces valeurs, identiques à
# celles de collecte/migrations/0003_donnees_initiales.py (vérifié par un test).
PARAMETRES_SECURITE = {"min_contributeurs": ("confidentialite_min_contributeurs", "3"),
                       "dominance_pct": ("confidentialite_dominance_pct", "80"),
                       "seuil_approbations": ("seuil_approbations_acces", "2"),
                       "couverture_min_pct": ("couverture_min_publication_pct", "80")}
RE_VARIABLE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
RE_LIEN = re.compile(r"\]\((/[^)\s]*)\)")
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
SECTION_MAX = 1400  # caractères : au-delà, la section est trop longue pour être bien retrouvée


class FicheInvalide(ValueError):
    pass


@dataclass(frozen=True)
class Section:
    fiche_id: str
    titre_fiche: str
    titre: str            # titre de la section ("" pour l'introduction)
    texte: str
    roles: frozenset
    lien: str
    questions: tuple
    toujours: bool

    @property
    def cle(self):
        return f"{self.fiche_id}#{self.titre}" if self.titre else self.fiche_id

    def visible_par(self, role):
        return "TOUS" in self.roles or role in self.roles


@dataclass(frozen=True)
class Fiche:
    id: str
    titre: str
    roles: frozenset
    lien: str
    questions: tuple
    toujours: bool
    mise_a_jour: str
    sections: tuple = field(default_factory=tuple)
    source: str = ""


def _decouper(fiche_id, titre_fiche, corps, roles, lien, questions, toujours):
    """Une section par titre « ## ». Une ligne « ?: q1 | q2 » ajoute des formulations propres à la section
    (elles servent à la recherche et ne sont jamais affichées)."""
    sections, titre, lignes, propres = [], "", [], []

    def fermer():
        texte = "\n".join(lignes).strip()
        if texte:
            sections.append(Section(fiche_id, titre_fiche, titre, texte, roles, lien, tuple(propres) + questions, toujours))

    for ligne in corps.splitlines():
        if ligne.startswith("## "):
            fermer()
            titre, lignes, propres = ligne[3:].strip(), [], []
        elif ligne.startswith("?:"):
            propres.extend(q.strip() for q in ligne[2:].split("|") if q.strip())
        else:
            lignes.append(ligne)
    fermer()
    return tuple(sections)


def lire_texte(texte, source="(texte)"):
    if not texte.startswith("---\n"):
        raise FicheInvalide(f"{source} : l'en-tête doit commencer par une ligne « --- ».")
    try:
        entete, corps = texte[4:].split("\n---\n", 1)
    except ValueError:
        raise FicheInvalide(f"{source} : en-tête non fermé (ligne « --- » manquante).")
    meta = {}
    for ligne in entete.splitlines():
        if not ligne.strip() or ligne.lstrip().startswith("#"):
            continue
        if ":" not in ligne:
            raise FicheInvalide(f"{source} : ligne d'en-tête sans « : » → {ligne!r}")
        cle, valeur = ligne.split(":", 1)
        meta[cle.strip()] = valeur.split(" #", 1)[0].strip()
    manquants = [c for c in CHAMPS_REQUIS if not meta.get(c)]
    if manquants:
        raise FicheInvalide(f"{source} : champ(s) obligatoire(s) manquant(s) : {', '.join(manquants)}")
    roles = frozenset(r.strip().upper() for r in meta["roles"].split(",") if r.strip())
    inconnus = roles - ROLES - {"TOUS"}
    if inconnus:
        raise FicheInvalide(f"{source} : rôle(s) inconnu(s) : {', '.join(sorted(inconnus))}")
    questions = tuple(q.strip() for q in meta.get("questions", "").split("|") if q.strip())
    toujours = meta.get("toujours", "non").lower() in {"oui", "yes", "1", "vrai"}
    lien = meta.get("lien", "")
    sections = _decouper(meta["id"], meta["titre"], corps, roles, lien, questions, toujours)
    if not sections:
        raise FicheInvalide(f"{source} : fiche vide.")
    return Fiche(meta["id"], meta["titre"], roles, lien, questions, toujours, meta["mise_a_jour"], sections, source)


def fiche_messages_rapport():
    """Fiche générée : un passage par message du rapport de contrôle (même texte que l'écran)."""
    from portail.rapport import CONSEILS
    roles = frozenset({"MEMBRE"})
    questions = ("Que veut dire ce message du rapport ?", "Mon fichier est refusé", "Comment corriger cette erreur ?")
    sections = tuple(
        Section("messages-rapport", "Messages du rapport de contrôle", quoi,
                f"Message « {quoi} ». Que faire : {comment}", roles, "/declarer/", questions, False)
        for _, (quoi, comment) in sorted(CONSEILS.items()))
    return Fiche("messages-rapport", "Messages du rapport de contrôle", roles, "/declarer/", questions, False,
                 "généré", sections, "portail/rapport.py")


def _signature(dossier):
    return tuple(sorted((p.name, p.stat().st_mtime_ns) for p in Path(dossier).glob("*.md")))


@lru_cache(maxsize=4)
def _charger(dossier, signature):
    fiches = []
    for chemin in sorted(Path(dossier).glob("*.md")):
        if chemin.name.upper().startswith("LISEZ-MOI"):
            continue
        fiche = lire_texte(chemin.read_text(encoding="utf-8"), chemin.name)
        if fiche.id != chemin.stem:
            raise FicheInvalide(f"{chemin.name} : l'id « {fiche.id} » doit être égal au nom du fichier.")
        fiches.append(fiche)
    fiches.append(fiche_messages_rapport())
    ids = [f.id for f in fiches]
    doublons = {i for i in ids if ids.count(i) > 1}
    if doublons:
        raise FicheInvalide(f"id en double : {', '.join(sorted(doublons))}")
    return tuple(fiches)


def charger(dossier=DOSSIER):
    """Toutes les fiches (relues automatiquement si un fichier change)."""
    return _charger(str(dossier), _signature(dossier))


def sections(dossier=DOSSIER):
    return tuple(s for f in charger(dossier) for s in f.sections)


def verifier(fiches=None):
    """Contrôles de qualité (commande roue_verifier, tests). Renvoie la liste des problèmes (vide = tout va bien)."""
    from django.urls import Resolver404, resolve
    problemes = []
    for f in fiches if fiches is not None else charger():
        liens = {f.lien} if f.lien else set()
        for s in f.sections:
            ou = f"{f.id}" + (f" / {s.titre}" if s.titre else "")
            liens.update(RE_LIEN.findall(s.texte))
            for v in RE_VARIABLE.findall(s.texte):
                if v not in VARIABLES:
                    problemes.append(f"{ou} : variable inconnue {{{{{v}}}}}")
            if RE_EMAIL.search(s.texte):
                problemes.append(f"{ou} : adresse e-mail dans le texte (utiliser {{{{contact}}}})")
            if len(s.texte) > SECTION_MAX:
                problemes.append(f"{ou} : section trop longue ({len(s.texte)} caractères, maximum {SECTION_MAX}) : la découper")
        for lien in sorted(liens):
            try:
                resolve(lien.split("?")[0].split("#")[0])
            except Resolver404:
                problemes.append(f"{f.id} : lien vers une page inexistante : {lien}")
    return problemes


def valeurs(params):
    """Paramètres publics (collecte.contexte.parametres_publics) → valeurs des variables {{…}} des fiches."""
    contact = (params.get("contact_gipame") or "").strip()
    if not contact or "renseigner" in contact.lower():
        contact_phrase = "le secrétariat du GIPAME"
    else:
        contact_phrase = f"le secrétariat du GIPAME ({contact})"
    v = {k: str(params.get(k, "")) for k in VARIABLES if k != "contact" and k not in PARAMETRES_SECURITE}
    for var, (cle, defaut) in PARAMETRES_SECURITE.items():
        v[var] = str(params.get(cle) or defaut)
    v["contact"] = contact_phrase
    return v


def remplir(texte, vals):
    return RE_VARIABLE.sub(lambda m: vals.get(m.group(1), m.group(0)), texte)


def sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


RE_ANNEE = re.compile(r"\b(19|20)\d\d\b")
RELECTURE_MAX_JOURS = 365


def avertissements(fiches=None, aujourd_hui=None):
    """Signaux d'obsolescence (non bloquants) : fiche non relue depuis plus d'un an, date écrite en dur dans le texte.
    La commande roue_verifier les affiche ; la vérification mensuelle (GitHub Actions) les fait remonter."""
    from datetime import date
    aujourd_hui = aujourd_hui or date.today()
    resultat = []
    for f in fiches if fiches is not None else charger():
        if f.mise_a_jour != "généré":
            try:
                relue = date.fromisoformat(f.mise_a_jour)
            except ValueError:
                resultat.append(f"{f.id} : mise_a_jour illisible ({f.mise_a_jour!r}), format attendu AAAA-MM-JJ")
            else:
                age = (aujourd_hui - relue).days
                if age > RELECTURE_MAX_JOURS:
                    resultat.append(f"{f.id} : non relue depuis {age} jours (le {f.mise_a_jour}) : vérifier qu'elle est toujours exacte")
        for s in f.sections:
            if RE_ANNEE.search(s.texte):
                resultat.append(f"{f.id} / {s.titre or 'introduction'} : année écrite en dur ({RE_ANNEE.search(s.texte).group(0)}) : "
                                "elle vieillira ; préférer une formulation relative ou une valeur lue en direct")
    return resultat
