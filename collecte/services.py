"""Calcul des publications (agrégats) à partir des déclarations SOUMISES.

À exécuter avec le rôle PostgreSQL gipame_calcul (seul rôle batch autorisé à lire les lignes
individuelles). Les cellules supprimées sont stockées SANS valeur.
"""
import calendar
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Q

from .confidentialite import Cellule, appliquer_controle
from .models import (CelluleAgregat, ClassementProduit, Declaration, LigneVente, Membre,
                     ParametreSysteme, Publication, Segmentation)


def _parametres():
    p = dict(ParametreSysteme.objects.values_list("cle", "valeur"))
    return {
        "k_min": int(p.get("confidentialite_min_contributeurs", 3)),
        "dominance_pct": int(p.get("confidentialite_dominance_pct", 80)),
        "couverture_min_pct": int(p.get("couverture_min_publication_pct", 80)),
    }


def membres_attendus(mois):
    fin = mois.replace(day=calendar.monthrange(mois.year, mois.month)[1])
    return Membre.objects.filter(
        Q(periodes__date_fin__isnull=True) | Q(periodes__date_fin__gte=mois),
        famille=Membre.Famille.VEHICULES,
        periodes__declaration_obligatoire=True,
        periodes__date_debut__lte=fin,
    ).distinct()


def calculer_publication(mois, segmentation=None, statut=Publication.Statut.PROVISOIRE):
    """Calcule et FIGE une publication. Une correction tardive donne une nouvelle version."""
    prm = _parametres()
    seg = segmentation or Segmentation.objects.get(statut=Segmentation.Statut.COURANTE)
    attendus = set(membres_attendus(mois).values_list("id", flat=True))
    declarants = set(
        Declaration.objects.filter(statut=Declaration.Statut.SOUMISE, mois=mois, membre_id__in=attendus)
        .values_list("membre_id", flat=True)
    )
    couverture = Decimal(100 * len(declarants) / len(attendus)).quantize(Decimal("0.01")) if attendus else Decimal("0")
    if statut == Publication.Statut.DEFINITIVE and couverture < prm["couverture_min_pct"]:
        raise ValueError(f"Couverture {couverture} % < {prm['couverture_min_pct']} % : publication définitive impossible")

    classement = {
        c.produit_id: (c.segment.code, c.segment.categorie.code)
        for c in ClassementProduit.objects.filter(segmentation=seg).select_related("segment__categorie")
    }
    lignes = (
        LigneVente.objects.filter(declaration__statut=Declaration.Statut.SOUMISE, declaration__mois=mois, quantite__gt=0)
        .values_list("produit_id", "quantite", "declaration__membre_id", "declaration__membre__groupe_id",
                     "produit__energie__code", "produit__modele__marque__origine__code")
    )
    cellules = {}

    def ajouter(dimension, cle, entite, quantite, parent=None):
        c = cellules.setdefault((dimension, cle), Cellule(dimension, cle, parent=parent))
        c.par_entite[entite] = c.par_entite.get(entite, 0) + quantite

    for produit_id, q, membre_id, groupe_id, energie, origine in lignes:
        entite = f"G{groupe_id}" if groupe_id else f"M{membre_id}"  # un groupe = un contributeur
        seg_code, cat_code = classement.get(produit_id, ("NON_CLASSE", "NON_CLASSE"))
        ajouter("TOTAL", "ALL", entite, q)
        ajouter("CATEGORIE", cat_code, entite, q)
        ajouter("SEGMENT", seg_code, entite, q, parent=f"CATEGORIE:{cat_code}")
        ajouter("ORIGINE", origine or "NON_CLASSE", entite, q)
        ajouter("ENERGIE", energie or "NON_RENSEIGNE", entite, q)

    appliquer_controle(list(cellules.values()), prm["k_min"], prm["dominance_pct"])

    with transaction.atomic():
        version = (Publication.objects.filter(mois=mois, segmentation=seg).aggregate(m=Max("version"))["m"] or 0) + 1
        pub = Publication.objects.create(
            mois=mois, segmentation=seg, statut=statut, version=version,
            nb_membres_attendus=len(attendus), nb_membres_declarants=len(declarants), couverture_pct=couverture,
            parametres={"k_min": prm["k_min"], "dominance_pct": prm["dominance_pct"]},
        )
        CelluleAgregat.objects.bulk_create([
            CelluleAgregat(
                publication=pub, dimension=c.dimension, cle=c.cle,
                total=None if c.supprime else c.total, supprime=c.supprime,
                n_contributeurs=c.n, motif_suppression=c.motif,
            )
            for c in cellules.values()
        ])
    return pub
