"""Exports Excel.

- exporter_annee_membre : le fichier annuel cumulatif, version « mes données seulement » + le marché publié
  (ce que reçoit le membre en échange de ses déclarations) ;
- exporter_publication : une publication figée (bureau : sans détail de suppression ; gestion : avec) ;
- exporter_suivi_depots : qui a déposé quoi, qui est en retard (statuts uniquement, jamais de quantités).

Chaque fonction s'exécute dans le contexte du rôle concerné : un export ne peut contenir que ce que ce rôle
a le droit de lire. Les cellules supprimées s'affichent « c » (confidentiel) ; la valeur n'existe pas.
"""
import calendar
from datetime import date

from django.db import connection, transaction
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

from ..contexte import garantir_contexte_membre
from ..models import (Categorie, CelluleAgregat, Energie, LigneVente, Declaration, Origine, Produit, Publication,
                      Segment)
from . import commun as c

MOIS_COURTS = ["Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin", "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc."]
CONFIDENTIEL = "c"
DIMENSIONS = [("CATEGORIE", "Catégories"), ("SEGMENT", "Segments"), ("ORIGINE", "Origines des marques"),
              ("ENERGIE", "Énergies")]


def _octets(wb):
    return c.en_octets(wb)


def _titre(ws, texte, largeur):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=largeur)
    ws["A1"] = texte
    c.style_titre(ws["A1"])
    ws.row_dimensions[1].height = 26


def _entete(ws, ligne, valeurs, hauteur=30):
    for i, v in enumerate(valeurs, 1):
        ws.cell(ligne, i, v)
        c.style_entete(ws.cell(ligne, i))
    ws.row_dimensions[ligne].height = hauteur


def _libelles(segmentation_id):
    """Libellés lisibles des clés de cellules."""
    return {
        ("TOTAL", "ALL"): "Total du marché GIPAME",
        **{("CATEGORIE", x.code): x.libelle for x in Categorie.objects.filter(segmentation_id=segmentation_id)},
        **{("SEGMENT", s.code): s.libelle for s in Segment.objects.filter(categorie__segmentation_id=segmentation_id)},
        **{("ORIGINE", o.code): o.libelle for o in Origine.objects.all()},
        **{("ENERGIE", e.code): e.libelle for e in Energie.objects.all()},
        ("CATEGORIE", "NON_CLASSE"): "Non classé", ("SEGMENT", "NON_CLASSE"): "Non classé",
        ("ORIGINE", "NON_CLASSE"): "Non renseignée", ("ENERGIE", "NON_RENSEIGNE"): "Non renseignée",
    }


def _ordre_cles(segmentation_id):
    """Ordre d'affichage (catégories, segments dans l'ordre de la grille)."""
    ordre = {}
    for x in Categorie.objects.filter(segmentation_id=segmentation_id):
        ordre[("CATEGORIE", x.code)] = x.ordre
    for s in Segment.objects.filter(categorie__segmentation_id=segmentation_id).select_related("categorie"):
        ordre[("SEGMENT", s.code)] = s.categorie.ordre * 100 + s.ordre
    return ordre


# ------------------------------------------------------------------------------------ mon année
def exporter_annee_membre(membre, annee):
    """Fichier annuel du membre : SES ventes mois par mois + le marché publié. Renvoie des octets .xlsx."""
    with transaction.atomic():
        garantir_contexte_membre(membre.id)
        declarations = {d.mois.month: d for d in Declaration.objects.filter(membre=membre, mois__year=annee, statut="SOUMISE")}
        ventes = {}
        for produit_id, mois, q in LigneVente.objects.filter(declaration__in=list(declarations.values())).values_list(
                "produit_id", "declaration__mois", "quantite"):
            ventes.setdefault(produit_id, {})[mois.month] = q
        mois_ref = date(annee, max(declarations), 1) if declarations else date(annee, 12, 1)
        with connection.cursor() as cur:  # lignes actives du membre, même sans vente : on garde la structure connue
            cur.execute("SELECT l_produit_id FROM gipame_lignes_gabarit(%s)", [mois_ref])
            actifs = {r[0] for r in cur.fetchall()}
        ids = set(ventes) | actifs
        produits = list(Produit.objects.filter(id__in=ids).select_related("modele__marque", "energie", "boite", "marque_proposee"))
        publications = _meilleures_publications(annee)
        cellules = _cellules(publications)
        libelles, ordre = {}, {}
        for pub in publications.values():
            libelles.update(_libelles(pub.segmentation_id))
            ordre.update(_ordre_cles(pub.segmentation_id))
    produits.sort(key=lambda p: (c.normaliser(p.modele.marque.nom if p.modele else p.marque_proposee.nom if p.marque_proposee else ""),
                                 c.normaliser(p.libelle_affiche), p.code))

    wb = Workbook()
    wb.properties.creator = "GIPAME"
    ws = wb.active
    ws.title = "MES VENTES"
    _titre(ws, f"Mes ventes de véhicules neufs - {annee} - {membre.code}", 19)
    ws["A2"] = "Vos données uniquement. Case vide = mois non déclaré ; 0 = mois déclaré sans vente."
    ws["A2"].font = c.police(italique=True)
    ws["A3"] = "Part en % = part de chaque ligne dans VOS ventes cumulées (ce n'est pas une part de marché)."
    ws["A3"].font = c.police(italique=True)
    _entete(ws, 5, ["Code produit", "Marque", "Désignation", "Énergie", "Boîte", *MOIS_COURTS, "Cumul", "Part en %"])
    ws.cell(6, 1, "Version déclarée")
    for m in range(1, 13):
        ws.cell(6, 5 + m, f"v{declarations[m].version}" if m in declarations else "—")
    for col in range(1, 20):
        ws.cell(6, col).font = c.police(italique=True, couleur="7F7F7F")
        ws.cell(6, col).fill = c.FOND_GRIS
        ws.cell(6, col).alignment = Alignment(horizontal="center" if col > 5 else "left")
    premiere = 7
    derniere = premiere + len(produits) - 1
    total = derniere + 1
    for k, p in enumerate(produits):
        r = premiere + k
        marque = p.modele.marque.nom if p.modele else (p.marque_proposee.nom if p.marque_proposee else "")
        for col, valeur in ((1, p.code), (2, marque), (3, p.libelle_affiche), (4, p.energie.code if p.energie else ""),
                            (5, p.boite.code if p.boite else "")):
            c.ecrire_texte(ws.cell(r, col), valeur)
            ws.cell(r, col).font = c.police()
        for m in range(1, 13):
            if m in declarations:
                ws.cell(r, 5 + m, ventes.get(p.id, {}).get(m, 0))
            ws.cell(r, 5 + m).font = c.police()
        ws.cell(r, 18, f"=SUM(F{r}:Q{r})")
        ws.cell(r, 19, f"=IF($R${total}=0,0,R{r}/$R${total})")
        ws.cell(r, 19).number_format = "0.0%"
        ws.cell(r, 18).font = c.police(gras=True)
        ws.cell(r, 19).font = c.police()
    ws.cell(total, 1, "TOTAL")
    for col in range(6, 19):
        lettre = get_column_letter(col)
        ws.cell(total, col, f"=SUM({lettre}{premiere}:{lettre}{derniere})" if produits else 0)
    for col in range(1, 20):
        ws.cell(total, col).font = c.police(gras=True)
        ws.cell(total, col).fill = c.FOND_GRIS
    for lettre, largeur in {"A": 15, "B": 16, "C": 44, "D": 11, "E": 8, "R": 10, "S": 10}.items():
        ws.column_dimensions[lettre].width = largeur
    for col in range(6, 18):
        ws.column_dimensions[get_column_letter(col)].width = 8
    ws.freeze_panes = "F7"

    wm = wb.create_sheet("MARCHE")
    _titre(wm, f"Le marché GIPAME - {annee} (totaux publiés)", 14)
    wm["A2"] = ("c = confidentiel : trop peu de contributeurs, ou un contributeur dominant (aucun chiffre individuel n'est "
                "jamais publié). « Provisoire » : tous les membres n'ont pas encore déclaré.")
    wm["A2"].font = c.police(italique=True)
    wm["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    wm.merge_cells("A2:N2")
    wm.row_dimensions[2].height = 30
    _entete(wm, 4, ["Indicateur", "Clé", *MOIS_COURTS])
    wm.cell(5, 1, "Statut de la publication")
    for m in range(1, 13):
        pub = publications.get(m)
        wm.cell(5, 2 + m, ("définitive" if pub.statut == "DEFINITIVE" else "provisoire") if pub else "—")
    for col in range(1, 15):
        wm.cell(5, col).font = c.police(italique=True, couleur="7F7F7F")
        wm.cell(5, col).fill = c.FOND_GRIS
    cles = sorted({k for cs in cellules.values() for k in cs},
                  key=lambda k: ([x[0] for x in [("TOTAL",), ("CATEGORIE",), ("SEGMENT",), ("ORIGINE",), ("ENERGIE",)]].index(k[0]),
                                 ordre.get(k, 9999), k[1]))
    r = 6
    for cle in cles:
        c.ecrire_texte(wm.cell(r, 1), libelles.get(cle, cle[1]))
        c.ecrire_texte(wm.cell(r, 2), f"{cle[0]}:{cle[1]}")
        for m in range(1, 13):
            if m in cellules and cle in cellules[m]:
                total_cellule, supprime = cellules[m][cle]
                wm.cell(r, 2 + m, CONFIDENTIEL if supprime else total_cellule)
                wm.cell(r, 2 + m).alignment = Alignment(horizontal="right")
        for col in range(1, 15):
            wm.cell(r, col).font = c.police(gras=cle[0] == "TOTAL")
        r += 1
    for lettre, largeur in {"A": 36, "B": 22}.items():
        wm.column_dimensions[lettre].width = largeur
    for col in range(3, 15):
        wm.column_dimensions[get_column_letter(col)].width = 9
    wm.freeze_panes = "C6"
    return _octets(wb)


def _meilleures_publications(annee):
    """Une publication par mois : la définitive la plus récente, sinon la provisoire la plus récente."""
    meilleures = {}
    for p in Publication.objects.filter(mois__year=annee, segmentation__statut="COURANTE"):
        courante = meilleures.get(p.mois.month)
        cle = (p.statut == "DEFINITIVE", p.version)
        if courante is None or cle > (courante.statut == "DEFINITIVE", courante.version):
            meilleures[p.mois.month] = p
    return meilleures


def _cellules(publications):
    """{mois: {(dimension, clé): (total, supprimé)}} - colonnes autorisées uniquement."""
    par_id = {p.id: m for m, p in publications.items()}
    resultat = {m: {} for m in publications}
    for pub_id, dimension, cle, total, supprime in CelluleAgregat.objects.filter(
            publication_id__in=list(par_id)).values_list("publication_id", "dimension", "cle", "total", "supprime"):
        resultat[par_id[pub_id]][(dimension, cle)] = (total, supprime)
    return resultat


# ------------------------------------------------------------------------------------ publication
def exporter_publication(publication, detail=False):
    """Une publication figée. `detail=True` ajoute n de contributeurs et motif : réservé à la gestion."""
    libelles, ordre = _libelles(publication.segmentation_id), _ordre_cles(publication.segmentation_id)
    colonnes = ("dimension", "cle", "total", "supprime") + (("n_contributeurs", "motif_suppression") if detail else ())
    cellules = list(CelluleAgregat.objects.filter(publication=publication).values_list(*colonnes))
    wb = Workbook()
    wb.properties.creator = "GIPAME"
    ws = wb.active
    ws.title = "RESUME"
    _titre(ws, f"Marché GIPAME - {c.libelle_mois(publication.mois)} - publication {publication.get_statut_display().lower()} "
               f"(version {publication.version})", 6)
    infos = [("Mois", c.libelle_mois(publication.mois)), ("Statut", publication.get_statut_display()),
             ("Version", publication.version), ("Grille de segments", publication.segmentation.code),
             ("Membres attendus", publication.nb_membres_attendus), ("Membres ayant déclaré", publication.nb_membres_declarants),
             ("Couverture (%)", float(publication.couverture_pct)),
             ("Calculée le", publication.calculee_le.strftime("%d/%m/%Y %H:%M"))]
    for i, (cle, valeur) in enumerate(infos, 3):
        ws.cell(i, 1, cle).font = c.police(gras=True)
        ws.cell(i, 2, valeur).font = c.police()
    fin = 3 + len(infos) + 1
    ws.cell(fin, 1, "Lecture").font = c.police(gras=True)
    notes = [f"« {CONFIDENTIEL} » = confidentiel : trop peu de contributeurs indépendants (moins de "
             f"{publication.parametres.get('k_min', 3)}), ou un contributeur dominant (plus de "
             f"{publication.parametres.get('dominance_pct', 80)} % de la cellule), ou masquage complémentaire pour empêcher de "
             "retrouver une valeur par différence.",
             "Les chiffres concernent les membres du GIPAME ayant déclaré, pas le marché national.",
             "Une publication est figée : une correction tardive donne une nouvelle version."]
    for i, texte in enumerate(notes, fin + 1):
        c.ecrire_texte(ws.cell(i, 1), texte)
        ws.cell(i, 1).font = c.police(italique=True)
        ws.cell(i, 1).alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=6)
        ws.row_dimensions[i].height = 42
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 26
    for dimension, titre in [("TOTAL", "Total")] + DIMENSIONS:
        lignes = sorted((x for x in cellules if x[0] == dimension), key=lambda x: (ordre.get((x[0], x[1]), 9999), x[1]))
        feuille = wb.create_sheet(titre[:28])
        _entete(feuille, 1, ["Clé", "Libellé", "Total", *(["Contributeurs", "Motif de suppression"] if detail else [])], 24)
        for i, ligne in enumerate(lignes, 2):
            c.ecrire_texte(feuille.cell(i, 1), ligne[1])
            c.ecrire_texte(feuille.cell(i, 2), libelles.get((dimension, ligne[1]), ligne[1]))
            feuille.cell(i, 3, CONFIDENTIEL if ligne[3] else ligne[2])
            feuille.cell(i, 3).alignment = Alignment(horizontal="right")
            if detail:
                feuille.cell(i, 4, ligne[4])
                c.ecrire_texte(feuille.cell(i, 5), ligne[5])
            for col in range(1, 6 if detail else 4):
                feuille.cell(i, col).font = c.police()
        feuille.column_dimensions["A"].width = 22
        feuille.column_dimensions["B"].width = 34
        feuille.column_dimensions["C"].width = 12
        feuille.freeze_panes = "A2"
    return _octets(wb)


# ------------------------------------------------------------------------------------ suivi des dépôts
def exporter_suivi_depots():
    """Suivi mensuel pour la gestion : statuts et dates uniquement (vue collecte_v_suivi_depots)."""
    with connection.cursor() as cur:
        cur.execute("SELECT membre_code, mois, statut_depot, version, soumise_le, date_limite, en_retard "
                    "FROM collecte_v_suivi_depots ORDER BY mois DESC, membre_code")
        lignes = cur.fetchall()
    wb = Workbook()
    wb.properties.creator = "GIPAME"
    ws = wb.active
    ws.title = "SUIVI"
    _titre(ws, "Suivi des déclarations mensuelles", 7)
    ws["A2"] = "Statuts et dates uniquement : aucune quantité n'apparaît dans ce fichier."
    ws["A2"].font = c.police(italique=True)
    _entete(ws, 4, ["Membre", "Mois", "Statut du dépôt", "Version", "Soumise le", "Date limite (délai de grâce inclus)", "En retard"], 36)
    for i, (code, mois, statut, version, soumise_le, limite, retard) in enumerate(lignes, 5):
        valeurs = [code, c.libelle_mois(mois), statut or "Non déposée", version, soumise_le.strftime("%d/%m/%Y %H:%M") if soumise_le else "",
                   limite.strftime("%d/%m/%Y"), "OUI" if retard else "NON"]
        for col, v in enumerate(valeurs, 1):
            if isinstance(v, str):
                c.ecrire_texte(ws.cell(i, col), v)
            else:
                ws.cell(i, col, v)
            ws.cell(i, col).font = c.police()
    if lignes:
        ws.conditional_formatting.add(f"A5:G{4 + len(lignes)}", FormulaRule(formula=['$G5="OUI"'], fill=c.FOND_ALERTE))
    for lettre, largeur in {"A": 12, "B": 18, "C": 16, "D": 9, "E": 18, "F": 30, "G": 10}.items():
        ws.column_dimensions[lettre].width = largeur
    ws.freeze_panes = "A5"
    return _octets(wb)
