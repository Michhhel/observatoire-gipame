"""
Contrôle de divulgation statistique : quelles cellules d'agrégats peut-on publier ?

Règles (paramétrables, voir ParametreSysteme) :
1. Suppression primaire
   - SEUIL      : moins de k contributeurs INDÉPENDANTS (un groupe économique = 1 contributeur)
   - DOMINANCE  : un contributeur pèse plus de d % de la cellule
2. Suppression complémentaire : dans chaque relation « parent = somme des enfants », il doit y
   avoir 0 ou au moins 2 cellules masquées. Avec une seule cellule masquée, on la retrouverait
   par différence : on masque alors aussi la plus petite cellule restante. On itère jusqu'à
   stabilité (un masquage peut en déclencher un autre).

Limites assumées de la v1 : pas de protection d'intervalle (un attaquant qui connaît la somme de
deux cellules masquées en déduit des bornes) et choix de la cellule complémentaire par plus petite
valeur (pas d'optimisation de la perte d'information). Les données de test ne dépendent d'aucune
base : cette logique est une fonction pure.
"""
from dataclasses import dataclass, field


@dataclass
class Cellule:
    dimension: str
    cle: str
    par_entite: dict = field(default_factory=dict)  # {contributeur indépendant: quantité}
    parent: str | None = None
    supprime: bool = False
    motif: str = ""

    @property
    def id(self) -> str:
        return f"{self.dimension}:{self.cle}"

    @property
    def total(self) -> int:
        return sum(self.par_entite.values())

    @property
    def n(self) -> int:
        return sum(1 for v in self.par_entite.values() if v > 0)

    @property
    def part_max_pct(self) -> float:
        return 100 * max(self.par_entite.values()) / self.total if self.total else 0.0


def construire_relations(cellules):
    """Relations (parent, enfants) où le parent est la somme des enfants."""
    par_dimension = {}
    for c in cellules:
        par_dimension.setdefault(c.dimension, []).append(c.id)
    relations = []
    if "TOTAL" in par_dimension:
        total_id = par_dimension["TOTAL"][0]
        for dim in ("CATEGORIE", "SEGMENT", "ORIGINE", "ENERGIE"):
            if dim in par_dimension:
                relations.append((total_id, par_dimension[dim]))
    enfants = {}
    for c in cellules:
        if c.dimension == "SEGMENT" and c.parent:
            enfants.setdefault(c.parent, []).append(c.id)
    relations.extend(enfants.items())
    return relations


def appliquer_controle(cellules, k_min=3, dominance_pct=80):
    """Marque `supprime` / `motif` sur chaque cellule (modifie les objets et les renvoie)."""
    par_id = {c.id: c for c in cellules}
    for c in cellules:
        if c.n < k_min:
            c.supprime, c.motif = True, "SEUIL"
        elif c.part_max_pct > dominance_pct:
            c.supprime, c.motif = True, "DOMINANCE"
    relations = construire_relations(cellules)
    modifie = True
    while modifie:
        modifie = False
        for parent_id, enfants_ids in relations:
            membres = [par_id[i] for i in [parent_id, *enfants_ids] if i in par_id]
            if len(membres) < 2:
                continue
            masquees = [m for m in membres if m.supprime]
            if len(masquees) == 1:
                restantes = [m for m in membres if not m.supprime]
                cible = min(restantes, key=lambda m: m.total)
                cible.supprime, cible.motif = True, "COMPLEMENTAIRE"
                modifie = True
    return cellules


def relations_valides(cellules):
    """Contrôle d'invariant : aucune relation ne contient exactement une cellule masquée."""
    par_id = {c.id: c for c in cellules}
    for parent_id, enfants_ids in construire_relations(cellules):
        membres = [par_id[i] for i in [parent_id, *enfants_ids] if i in par_id]
        if len(membres) >= 2 and sum(m.supprime for m in membres) == 1:
            return False
    return True
