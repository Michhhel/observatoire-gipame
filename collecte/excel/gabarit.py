"""Génération du gabarit mensuel de déclaration (fichier .xlsx) pour UN membre.

Contenu : uniquement les produits du membre (jamais ceux des autres), ses propres quantités du mois
précédent à titre de repère, un onglet AJOUTS pour proposer de nouveaux produits, des protections et
contrôles de saisie. La protection d'Excel n'est qu'un garde-fou de confort : la vraie validation se
fait à l'import (voir depot.py).
"""
import calendar
from dataclasses import dataclass
from datetime import timedelta

from django.db import connection, transaction
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Protection
from openpyxl.worksheet.datavalidation import DataValidation

from ..contexte import garantir_contexte_membre, parametres_publics
from ..models import Boite, Concession, Declaration, Energie, LigneVente, Produit
from . import commun as c

# Emplacements fixes (relus à l'import via l'onglet _META)
LIGNE_ENTETE, PREMIERE_LIGNE = 7, 8
COL_CODE, COL_QTE, COL_COMMENTAIRE, COL_PRECEDENT = 1, 7, 8, 6
CELLULE_ATTESTATION, CELLULE_AUCUNE_VENTE, CELLULE_MOTIF = "G2", "G3", "G4"
AJOUTS_ENTETE, AJOUTS_PREMIERE = 5, 7
COLONNES_AJOUTS = ["Marque", "Modèle", "Version / finition", "Énergie", "Boîte", "Cylindrée (cm³)",
                   "Puissance fiscale (CV)", "Charge utile (kg)", "PTAC (kg)", "Places", "Motricité",
                   "Segment / type (suggestion)", "Quantité vendue ce mois", "Note"]


@dataclass
class LigneGabarit:
    produit_id: int
    code: str
    marque: str
    designation: str
    energie: str
    boite: str
    precedent: int | None
    valeur: int
    statut: str


def _mois_precedent(mois):
    return (mois.replace(day=1) - timedelta(days=1)).replace(day=1)


def _etat_declaration(membre, mois):
    """(version du gabarit, est une correction, quantités à pré-remplir)."""
    declarations = list(Declaration.objects.filter(membre=membre, mois=mois))
    soumise = next((d for d in declarations if d.statut == "SOUMISE"), None)
    brouillon = next((d for d in declarations if d.statut == "BROUILLON"), None)
    version = brouillon.version if brouillon else max((d.version for d in declarations), default=0) + 1
    base = brouillon or soumise
    quantites = {}
    if base:
        quantites = dict(LigneVente.objects.filter(declaration=base).values_list("produit_id", "quantite"))
    return version, soumise is not None, quantites


def lignes_gabarit(membre, mois):
    """Lignes du gabarit du membre pour ce mois (à appeler dans une transaction)."""
    garantir_contexte_membre(membre.id)
    version, correction, prefill = _etat_declaration(membre, mois)
    with connection.cursor() as cur:
        cur.execute("SELECT l_produit_id, l_statut FROM gipame_lignes_gabarit(%s)", [mois])
        trouvees = cur.fetchall()
    statuts = dict(trouvees)
    produits = Produit.objects.filter(id__in=list(statuts)).select_related(
        "modele__marque", "energie", "boite", "marque_proposee")
    precedent = dict(LigneVente.objects.filter(
        declaration__membre=membre, declaration__mois=_mois_precedent(mois), declaration__statut="SOUMISE",
    ).values_list("produit_id", "quantite"))
    lignes = []
    for p in produits:
        marque = p.modele.marque.nom if p.modele else (p.marque_proposee.nom if p.marque_proposee else "")
        lignes.append(LigneGabarit(
            produit_id=p.id, code=p.code, marque=marque, designation=p.libelle_affiche,
            energie=p.energie.code if p.energie else "", boite=p.boite.code if p.boite else "",
            precedent=precedent.get(p.id), valeur=prefill.get(p.id, 0), statut=statuts[p.id]))
    lignes.sort(key=lambda x: (c.normaliser(x.marque), c.normaliser(x.designation), x.code))
    return version, correction, lignes


def generer_gabarit(membre, mois):
    """Renvoie (contenu .xlsx en octets, version de déclaration, nombre de lignes)."""
    with transaction.atomic():
        garantir_contexte_membre(membre.id)
        params = parametres_publics()
        version, correction, lignes = lignes_gabarit(membre, mois)
        fin_mois = mois.replace(day=calendar.monthrange(mois.year, mois.month)[1])
        marques = sorted({
            c.texte_propre(m) for m in Concession.objects.filter(membre=membre, date_debut__lte=fin_mois)
            .exclude(date_fin__lt=mois).values_list("marque__nom", flat=True)})
        energies = list(Energie.objects.filter(actif=True).values_list("code", flat=True))
        boites = list(Boite.objects.filter(actif=True).values_list("code", flat=True))
    qmax = int(params["import_quantite_max"])
    max_ajouts = int(params["import_max_ajouts"])
    wb = Workbook()
    wb.properties.creator = "GIPAME"
    wb.properties.title = f"Déclaration {c.libelle_mois(mois)} - {membre.code}"
    _feuille_declaration(wb, membre, mois, version, correction, lignes, params, qmax)
    _feuille_ajouts(wb, mois, max_ajouts, qmax, len(marques))
    _feuille_lisez_moi(wb, params)
    codes = [x.code for x in lignes]
    _feuille_listes(wb, energies, boites, marques, codes)
    _feuille_meta(wb, membre, mois, version, correction, codes, max_ajouts)
    return c.en_octets(wb), version, len(lignes)


# --------------------------------------------------------------------------- feuilles
def _largeurs(ws, largeurs):
    for lettre, largeur in largeurs.items():
        ws.column_dimensions[lettre].width = largeur


def _saisie(cellule, nombre=False):
    cellule.fill = c.FOND_SAISIE
    cellule.border = c.BORDURE
    cellule.font = c.police()
    cellule.protection = Protection(locked=False)
    if nombre:
        cellule.number_format = "0"
        cellule.alignment = Alignment(horizontal="right")


def _fixe(cellule, gras=False, gris=False):
    cellule.font = c.police(gras=gras)
    cellule.border = c.BORDURE
    if gris:
        cellule.fill = c.FOND_GRIS


def _feuille_declaration(wb, membre, mois, version, correction, lignes, params, qmax):
    ws = wb.active
    ws.title = c.FEUILLE_DECLARATION
    ws.merge_cells("A1:H1")
    ws["A1"] = f"Déclaration mensuelle des ventes de véhicules neufs - {c.libelle_mois(mois)}"
    c.style_titre(ws["A1"])
    ws.row_dimensions[1].height = 26
    etiquettes = {"A2": "Membre", "A3": "Mois", "A4": "Version"}
    for adresse, texte in etiquettes.items():
        ws[adresse] = texte
        ws[adresse].font = c.police(gras=True)
    c.ecrire_texte(ws["B2"], f"{membre.code} - {membre.raison_sociale}")
    ws["B3"] = c.libelle_mois(mois)
    ws["B4"] = f"{version}" + (" (correction d'une déclaration déjà soumise)" if correction else "")
    for adresse in ("B2", "B3", "B4"):
        ws[adresse].font = c.police()
    for ligne, texte in ((2, "Déclaration complète et exacte ?"), (3, "Aucune vente ce mois-ci ?"),
                         (4, "Motif de la correction" + (" (obligatoire)" if correction else ""))):
        ws.merge_cells(start_row=ligne, start_column=4, end_row=ligne, end_column=6)
        ws.cell(ligne, 4, texte).font = c.police(gras=True)
        ws.cell(ligne, 4).alignment = Alignment(horizontal="right", vertical="center")
    _saisie(ws[CELLULE_ATTESTATION])
    _saisie(ws[CELLULE_AUCUNE_VENTE])
    ws[CELLULE_AUCUNE_VENTE] = "NON"
    ws.merge_cells("G4:H4")
    _saisie(ws[CELLULE_MOTIF])
    ws["H4"].fill = c.FOND_SAISIE
    ws["H4"].protection = Protection(locked=False)
    ws.merge_cells("A5:H5")
    c.ecrire_texte(ws["A5"], "Définition d'une vente : " + params["definition_vente"])
    ws["A5"].font = c.police(italique=True)
    ws["A5"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[5].height = 30
    ws.merge_cells("A6:H6")
    ws["A6"] = ("Remplissez uniquement les cases jaunes (colonne QUANTITÉ : un nombre entier, 0 si aucune vente). "
                "Lisez l'onglet LISEZ-MOI avant de commencer.")
    ws["A6"].font = c.police(italique=True, couleur="C00000")
    ws["A6"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[6].height = 30
    entetes = ["Code produit", "Marque", "Désignation", "Énergie", "Boîte", "Mois précédent (repère)",
               "QUANTITÉ VENDUE", "Commentaire"]
    for i, texte in enumerate(entetes, 1):
        ws.cell(LIGNE_ENTETE, i, texte)
        c.style_entete(ws.cell(LIGNE_ENTETE, i))
    ws.row_dimensions[LIGNE_ENTETE].height = 32
    for k, ligne in enumerate(lignes):
        r = PREMIERE_LIGNE + k
        for col, valeur in ((1, ligne.code), (2, ligne.marque), (3, ligne.designation), (4, ligne.energie), (5, ligne.boite)):
            c.ecrire_texte(ws.cell(r, col), valeur)
            _fixe(ws.cell(r, col), gris=True)
        precedent = ws.cell(r, COL_PRECEDENT, ligne.precedent)
        _fixe(precedent, gris=True)
        precedent.number_format = "0"
        _saisie(ws.cell(r, COL_QTE, ligne.valeur), nombre=True)
        _saisie(ws.cell(r, COL_COMMENTAIRE))
    derniere = PREMIERE_LIGNE + len(lignes) - 1
    total = derniere + 1
    ws.cell(total, 1, "TOTAL")
    ws.cell(total, COL_PRECEDENT, f"=SUM(F{PREMIERE_LIGNE}:F{derniere})" if lignes else 0)
    ws.cell(total, COL_QTE, f"=SUM(G{PREMIERE_LIGNE}:G{derniere})" if lignes else 0)
    for col in range(1, 9):
        _fixe(ws.cell(total, col), gras=True, gris=True)
    if lignes:
        zone = f"G{PREMIERE_LIGNE}:G{derniere}"
        dv = DataValidation(type="whole", operator="between", formula1="0", formula2=str(qmax), allow_blank=False,
                            showErrorMessage=True, errorTitle="Quantité invalide",
                            error=f"Saisissez un nombre entier entre 0 et {qmax} (0 si aucune vente).",
                            showInputMessage=True, promptTitle="Quantité vendue", prompt="Nombre entier, 0 si aucune vente.")
        ws.add_data_validation(dv)
        dv.add(zone)
        pct = int(params["import_variation_alerte_pct"])
        mini = int(params["import_variation_min_unites"])
        ws.conditional_formatting.add(zone, FormulaRule(
            formula=[f"AND(N($G{PREMIERE_LIGNE})>0,MAX(N($F{PREMIERE_LIGNE}),N($G{PREMIERE_LIGNE}))>={mini},"
                     f"ABS(N($G{PREMIERE_LIGNE})-N($F{PREMIERE_LIGNE}))>=N($F{PREMIERE_LIGNE})*{pct}/100,"
                     f"LEN($H{PREMIERE_LIGNE})=0)"], fill=c.FOND_ALERTE))
    oui_non = DataValidation(type="list", formula1='"OUI,NON"', allow_blank=True, showErrorMessage=True,
                             errorTitle="Réponse attendue", error="Répondez OUI ou NON.")
    ws.add_data_validation(oui_non)
    oui_non.add(CELLULE_ATTESTATION)
    oui_non.add(CELLULE_AUCUNE_VENTE)
    _largeurs(ws, {"A": 16, "B": 18, "C": 44, "D": 14, "E": 10, "F": 14, "G": 18, "H": 34})
    ws.freeze_panes = f"A{PREMIERE_LIGNE}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToHeight = 0
    ws.protection.sheet = True


def _feuille_ajouts(wb, mois, max_ajouts, qmax, nb_marques):
    ws = wb.create_sheet(c.FEUILLE_AJOUTS)
    ws.merge_cells("A1:N1")
    ws["A1"] = "Nouveaux produits que vous vendez et qui ne figurent pas dans l'onglet DECLARATION"
    c.style_titre(ws["A1"])
    ws.row_dimensions[1].height = 26
    ws.merge_cells("A2:N3")
    ws["A2"] = ("Une ligne par produit (version). Ces produits sont vérifiés par le GIPAME avant d'entrer au catalogue ; "
                "vos concurrents ne les voient pas. Saisissez aussi la quantité vendue ce mois : elle est enregistrée "
                "avec votre déclaration. Ne rien saisir ici s'il n'y a pas de nouveauté.")
    ws["A2"].font = c.police(italique=True)
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    for i, texte in enumerate(COLONNES_AJOUTS, 1):
        ws.cell(AJOUTS_ENTETE, i, texte)
        c.style_entete(ws.cell(AJOUTS_ENTETE, i))
    ws.row_dimensions[AJOUTS_ENTETE].height = 42
    exemple = ["EXEMPLE", "Modèle X", "LIFE", "ESSENCE", "BVA", 1400, 6, None, None, 5, "4X2", "Citadine", 3,
               "Ligne d'exemple : ne pas remplir ici"]
    for i, valeur in enumerate(exemple, 1):
        cellule = ws.cell(AJOUTS_ENTETE + 1, i)
        if isinstance(valeur, str):
            c.ecrire_texte(cellule, valeur)
        else:
            cellule.value = valeur
        cellule.font = c.police(italique=True, couleur="7F7F7F")
        cellule.fill = c.FOND_GRIS
        cellule.border = c.BORDURE
    derniere = AJOUTS_PREMIERE + max_ajouts - 1
    for r in range(AJOUTS_PREMIERE, derniere + 1):
        for col in range(1, 15):
            _saisie(ws.cell(r, col), nombre=col in (6, 7, 8, 9, 10, 13))
    nb_marques = max(2, nb_marques)
    plage = f"{AJOUTS_PREMIERE}:{derniere}"
    for lettre, formule in (("A", f"'{c.FEUILLE_LISTES}'!$C$2:$C${nb_marques + 1}"),
                            ("D", f"'{c.FEUILLE_LISTES}'!$A$2:$A$20"), ("E", f"'{c.FEUILLE_LISTES}'!$B$2:$B$20")):
        dv = DataValidation(type="list", formula1=formule, allow_blank=True, showErrorMessage=True,
                            errorTitle="Valeur non reconnue", error="Choisissez une valeur dans la liste.")
        ws.add_data_validation(dv)
        dv.add(f"{lettre}{AJOUTS_PREMIERE}:{lettre}{derniere}")
    nombres = DataValidation(type="whole", operator="between", formula1="0", formula2=str(qmax * 10), allow_blank=True,
                             showErrorMessage=True, errorTitle="Nombre invalide", error="Saisissez un nombre entier positif.")
    ws.add_data_validation(nombres)
    for lettre in "FGHIJM":
        nombres.add(f"{lettre}{AJOUTS_PREMIERE}:{lettre}{derniere}")
    _largeurs(ws, {"A": 18, "B": 18, "C": 20, "D": 14, "E": 10, "F": 12, "G": 12, "H": 12, "I": 10, "J": 8,
                   "K": 11, "L": 24, "M": 14, "N": 30})
    ws.freeze_panes = f"A{AJOUTS_PREMIERE}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.protection.sheet = True


def _feuille_lisez_moi(wb, params):
    ws = wb.create_sheet(c.FEUILLE_LISEZ)
    ws.column_dimensions["A"].width = 110
    lignes = [
        ("Comment remplir ce fichier", "titre"),
        ("1. Onglet DECLARATION : pour chaque ligne, saisissez dans la colonne jaune QUANTITÉ VENDUE le nombre de véhicules "
         "neufs vendus pendant le mois. Saisissez 0 si vous n'avez rien vendu : aucune case ne doit rester vide.", ""),
        ("2. Si vous n'avez eu aucune vente ce mois-ci, mettez « Aucune vente ce mois-ci » à OUI (toutes les quantités à 0).", ""),
        ("3. Un produit que vous vendez et qui n'est pas listé : onglet AJOUTS, une ligne par produit. Il est vérifié par le "
         "GIPAME ; vos concurrents ne le voient pas.", ""),
        ("4. Répondez OUI à « Déclaration complète et exacte ? » quand vous avez terminé, enregistrez au format .xlsx (pas de "
         "CSV) puis déposez le fichier sur le portail. Le portail vous renvoie un rapport de contrôle.", ""),
        ("5. Une erreur ? Déposez de nouveau le fichier corrigé tant que la déclaration n'est pas soumise. Après soumission, "
         "téléchargez le gabarit de correction : il garde l'historique et exige un motif.", ""),
        ("À ne pas faire", "titre"),
        ("Renommer les onglets · supprimer, déplacer ou modifier la colonne « Code produit » · supprimer des lignes · ajouter "
         "des lignes dans DECLARATION · utiliser le fichier d'un autre mois ou d'un autre membre · ajouter des macros.", ""),
        ("Les cases orange signalent une variation forte par rapport au mois précédent : ajoutez un commentaire.", ""),
        ("Confidentialité", "titre"),
        ("Ce fichier ne contient que vos propres données. Elles ne sont visibles que de votre société ; le GIPAME ne publie "
         "que des totaux agrégés, et jamais un total qui permettrait de retrouver les chiffres d'un membre.", ""),
        ("Exemple de ligne correctement remplie (valeurs fictives)", "titre"),
        ("Code produit : EX-001  |  Marque : MARQUE  |  Désignation : MODELE VERSION  |  Énergie : ESSENCE  |  Boîte : BVA  |  "
         "QUANTITÉ VENDUE : 12  |  Commentaire : (vide)", "exemple"),
        ("Définition d'une vente : " + params["definition_vente"], ""),
        ("Contact : " + params["contact_gipame"], ""),
    ]
    for i, (texte, genre) in enumerate(lignes, 1):
        cellule = ws.cell(i, 1)
        c.ecrire_texte(cellule, texte)
        cellule.alignment = Alignment(wrap_text=True, vertical="top")
        if genre == "titre":
            cellule.font = c.police(gras=True, taille=11)
            cellule.fill = c.FOND_GRIS
        elif genre == "exemple":
            cellule.font = c.police(italique=True, couleur="7F7F7F")
        else:
            cellule.font = c.police()
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.protection.sheet = True


def _feuille_listes(wb, energies, boites, marques, codes):
    ws = wb.create_sheet(c.FEUILLE_LISTES)
    for col, (titre, valeurs) in enumerate((("energies", energies), ("boites", boites), ("marques", marques),
                                            ("codes_attendus", codes)), 1):
        ws.cell(1, col, titre)
        for i, v in enumerate(valeurs, 2):
            c.ecrire_texte(ws.cell(i, col), v)
    ws.sheet_state = "veryHidden"


def _feuille_meta(wb, membre, mois, version, correction, codes, max_ajouts):
    ws = wb.create_sheet(c.FEUILLE_META)
    meta = [
        ("format", c.FORMAT_DECLARATION), ("gabarit_version", c.GABARIT_VERSION), ("membre_code", membre.code),
        ("mois", mois.isoformat()), ("version_declaration", str(version)), ("correction", "1" if correction else "0"),
        ("signature", c.signer(c.GABARIT_VERSION, membre.code, mois, version, codes)),
        ("premiere_ligne", str(PREMIERE_LIGNE)), ("colonne_code", str(COL_CODE)), ("colonne_quantite", str(COL_QTE)),
        ("colonne_commentaire", str(COL_COMMENTAIRE)), ("cellule_attestation", CELLULE_ATTESTATION),
        ("cellule_aucune_vente", CELLULE_AUCUNE_VENTE), ("cellule_motif", CELLULE_MOTIF),
        ("ajouts_premiere_ligne", str(AJOUTS_PREMIERE)), ("ajouts_max", str(max_ajouts)),
    ]
    for i, (cle, valeur) in enumerate(meta, 1):
        c.ecrire_texte(ws.cell(i, 1), cle)
        c.ecrire_texte(ws.cell(i, 2), valeur)
    ws.sheet_state = "veryHidden"
