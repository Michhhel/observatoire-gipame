"""Recherche des passages utiles (le « R » du RAG) : BM25 sur les fiches, en français, sans dépendance.

Pourquoi pas des « embeddings » (recherche vectorielle) ? La base est petite (quelques dizaines de fiches), écrite
avec le vocabulaire du portail, et chaque fiche liste les façons dont les gens posent la question (`questions:`).
Une recherche lexicale bien réglée suffit, elle est instantanée, gratuite, explicable et testable (evaluation.py).
Si la base dépasse quelques centaines de fiches ou si l'évaluation se dégrade, on pourra ajouter un score vectoriel
à côté de celui-ci sans changer le reste.
"""
import math
import re
from collections import Counter
from dataclasses import dataclass

from .connaissances import sans_accents

MOTS_VIDES = set("""
a ai aie aies ait alors au aucun aussi aux avec avoir avez avons c ca ce cela celle celles celui ces cet cette ceux
chaque comme comment d dans de des doit dois donc du elle elles en encore est et etc etes etre eu faire fait
faut il ils j je l la le les leur leurs lui m ma mais me meme mes moi mon n ne ni nos notre nous on ont ou par pas
peut peux plus pour pourquoi puis puisque qu quand que quel quelle quelles quels qui quoi s sa sans se ses si son
sont suis sur t ta te tes toi ton tous tout toute toutes tu un une vos votre vous y svp merci bonjour bonsoir
salut stp aide aider besoin veux voudrais voulais souhaite ici ceci the is ensuite apres
""".split())

# Familles de mots équivalents dans le vocabulaire des utilisateurs (après normalisation, avant racinisation).
SYNONYMES = [
    "gabarit fichier excel classeur tableur xlsx modele formulaire",
    "deposer depot deposez envoyer envoi transmettre charger televerser uploader importer",
    "soumettre soumission soumis soumise valider validation finaliser",
    "declarer declaration declarations declare",
    "vente ventes vendu vendus vendre",
    "erreur erreurs rouge refuse refusee rejete rejet bloquant",
    "alerte alertes orange avertissement",
    "mdp motdepasse password",
    "bloque blocage verrouille",
    "corriger correction modifier rectifier changer",
    "confidentiel confidentialite masque cache secret c",
    "concurrent concurrents autres",
    "produit produits vehicule vehicules reference article version finition",
    "ajouter ajout ajouts nouveau absent manque manquant",
    "limite delai echeance retard",
    "marche publication publications publie totaux",
    "connexion connecter connecte login identifier",
    "rappel rappels relance relancer",
    "approuver approbation accord accords",
    "compte comptes utilisateur utilisateurs",
    "zero rien aucune",
]
POIDS_SYNONYME = 0.45
K1, B = 1.2, 0.75
BONUS_QUESTION = 8.0   # la question ressemble à une des formulations listées par la fiche (`questions:`)
BONUS_TITRE = 6.0      # la question contient le titre de la section (message d'erreur recopié, par exemple)
COUVERTURE_MIN = 0.4   # une question d'au moins 3 mots doit en retrouver 40 % dans le passage (sinon : hors sujet)


def raciner(mot):
    """Racinisation légère du français : pluriels puis une terminaison courante."""
    if len(mot) <= 3 or mot.isdigit():
        return mot
    if mot[-1] in "sx" and len(mot) > 4:
        mot = mot[:-1]
    for suffixe in ("issement", "ations", "ation", "ements", "ement", "atrice", "ateur", "ances", "ance", "ences",
                    "ence", "ites", "ite", "euse", "eur", "ives", "ive", "ees", "ee", "er", "ez", "es", "e"):
        if mot.endswith(suffixe) and len(mot) - len(suffixe) >= 4:
            return mot[: -len(suffixe)]
    return mot


RE_C = re.compile(r"([«\"“']\s*c\s*[»\"”'])|\b(?:les|des|une?|la|le|en|case|cases|cellule|cellules|lettre)\s+c\b")


def mots(texte):
    texte = RE_C.sub(" confidentiel ", texte)  # la case « c » (confidentiel), sinon perdue comme mot vide
    texte = sans_accents(texte.lower()).replace("mot de passe", "motdepasse").replace("mots de passe", "motdepasse")
    return [m for m in re.findall(r"[a-z0-9]+", texte) if m not in MOTS_VIDES]


def termes(texte):
    return [raciner(m) for m in mots(texte)]


_GROUPES = {}
for _ligne in SYNONYMES:
    _racines = {raciner(m) for m in _ligne.split()}
    for _r in _racines:
        _GROUPES.setdefault(_r, set()).update(_racines)


def termes_requete(texte, poids=1.0):
    """Un groupe par mot de la question : {le mot: poids, ses équivalents: poids × POIDS_SYNONYME}.
    Chaque groupe compte une seule fois (son meilleur terme) : une famille de synonymes ne s'additionne pas."""
    groupes = {}
    for t in termes(texte):
        if t in groupes:
            continue
        groupe = {s: poids * POIDS_SYNONYME for s in _GROUPES.get(t, ())}
        groupe[t] = poids
        groupes[t] = groupe
    return list(groupes.values())


@dataclass
class Resultat:
    section: object
    score: float


class Index:
    """Index BM25 d'une liste de sections. Champs pondérés par répétition : titres ×3, questions ×2, texte ×1."""

    def __init__(self, sections):
        self.sections = list(sections)
        self.docs, self.formulations, self.titres = [], [], []
        for s in self.sections:
            self.formulations.append([set(termes(q)) for q in s.questions if termes(q)])
            self.titres.append(set(termes(s.titre)))
            sac = termes(s.titre_fiche) * 2 + termes(s.titre) * 3 + termes(" ".join(s.questions)) * 2 + termes(s.texte)
            self.docs.append(Counter(sac))
        self.longueurs = [sum(d.values()) for d in self.docs]
        self.moyenne = (sum(self.longueurs) / len(self.longueurs)) if self.docs else 1.0
        n = len(self.docs)
        frequence = Counter(t for d in self.docs for t in d)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in frequence.items()}

    def chercher(self, question, role, k=5, seuil=1.5, contexte=""):
        """Les k meilleures sections visibles par `role`. `contexte` (question précédente) aide à comprendre une
        relance courte (« et ensuite ? ») sans écraser une vraie nouvelle question."""
        requete = termes_requete(question)
        nb_question = len(requete)
        dans_question = {t for g in requete for t in g}
        poids_contexte = 0.8 if nb_question <= 2 else 0.5  # « et ensuite ? » dépend presque entièrement du contexte
        requete += [g for g in termes_requete(contexte, poids_contexte) if not set(g) & dans_question]
        saisis = set(termes(question))
        resultats = []
        for s, doc, longueur, formulations, titre in zip(self.sections, self.docs, self.longueurs, self.formulations, self.titres):
            if not s.visible_par(role):
                continue
            score, couverts = 0.0, 0
            for i, groupe in enumerate(requete):
                meilleur_terme = 0.0
                for t, w in groupe.items():
                    tf = doc.get(t)
                    if tf:
                        meilleur_terme = max(meilleur_terme, w * self.idf[t] * tf * (K1 + 1) / (tf + K1 * (1 - B + B * longueur / self.moyenne)))
                score += meilleur_terme
                if meilleur_terme and i < nb_question:
                    couverts += 1
            if score <= 0 or (nb_question >= 3 and couverts / nb_question < COUVERTURE_MIN):
                continue
            if saisis and formulations:  # coefficient de Dice avec la formulation la plus proche
                score += BONUS_QUESTION * max(2 * len(saisis & f) / (len(saisis) + len(f)) for f in formulations)
            if len(titre) >= 2 and titre <= saisis:
                score += BONUS_TITRE
            if score > 0:
                resultats.append(Resultat(s, score))
        resultats.sort(key=lambda r: -r.score)
        if not resultats or resultats[0].score < seuil:
            return []
        meilleur = resultats[0].score
        retenus, par_fiche = [], Counter()
        for r in resultats:
            if r.score < max(seuil, 0.3 * meilleur) or len(retenus) >= k:
                break
            if par_fiche[r.section.fiche_id] >= 3:
                continue
            par_fiche[r.section.fiche_id] += 1
            retenus.append(r)
        return retenus
