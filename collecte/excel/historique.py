"""Reprise de l'historique : anciens fichiers annuels cumulatifs -> base.

Trois étapes, pour que rien ne passe en silence :
1. lire_historique          : lit l'ancien fichier (feuille « MTM <année> ») et en extrait des lignes propres ;
                              les totaux et sous-totaux de l'ancien fichier sont IGNORÉS (ils sont faux) ;
2. ecrire_rapprochement     : produit un classeur de rapprochement (membres, marques, produits) avec des
                              propositions automatiques qu'un humain valide ou corrige ;
3. charger_historique       : applique le rapprochement validé (a_blanc=True pour simuler).

Le rapprochement n'est fait qu'UNE fois : chaque libellé validé devient un alias, les années suivantes se
rapprochent seules. Ce chargement est une opération privilégiée (compte propriétaire), pas un acte de membre.
"""
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date

from django.db import IntegrityError, connection, transaction
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment
from openpyxl.worksheet.datavalidation import DataValidation

from ..models import (AliasProduit, Boite, ClassementProduit, Concession, Declaration, DepotFichier, Energie,
                      LigneVente, Marque, Membre, Modele, Origine, PeriodeAdhesion, Produit, Segment, Segmentation)
from . import commun as c
from .depot import Probleme

REGLES_SEGMENT = [
    (r"^SEGMENT A B\b", "AB"), (r"^SEGMENT M1\b", "M1"), (r"^SEGMENT M2\b", "M2"), (r"^SEGMENT H\b", "H"),
    (r"^SEGMENT SUV\b", "SUV"), (r"^SEGMENT 4X4 MEDIUM\b", "4X4_MEDIUM"), (r"^SEGMENT 4X4 LARGE\b", "4X4_LARGE"),
    (r"^SEGMENT PICK UP 4X2\b", "PU_4X2"), (r"^SEGMENT PICK UP 4X4\b", "PU_4X4"),
    (r"^SEGMENT PICK UP HEAVY DUTY\b", "PU_HD"), (r"^CATEGORIES VEHICULES VAN\b", "VAN"),
    (r"^SEGMENT BUS < 22", "BUS_MOINS_22"), (r"^SEGMENT BUS 23 TO 34", "BUS_23_34"), (r"^SEGMENT BUS > 34", "BUS_PLUS_34"),
    (r"^CATEGORIES TRUCKS LIGHT", "CAMION_3_6T"), (r"^SEGMENT TRUCKS MEDIUM", "CAMION_6_15T"),
    (r"^SEGMENT TRACTEURS", "TRACTEUR_PLUS_15T"), (r"^SEGMENT PORTEURS", "PORTEUR_PLUS_15T"),
]
ENERGIES = {"ESS": "ESSENCE", "ESSENCE": "ESSENCE", "PETROL": "ESSENCE", "GASOLINE": "ESSENCE", "DIESEL": "DIESEL",
            "GASOIL": "DIESEL", "GAZOLE": "DIESEL", "DID": "DIESEL", "DIE": "DIESEL", "TDI": "DIESEL", "HYBRIDE": "HYBRIDE",
            "HYB": "HYBRIDE", "HEV": "HYBRIDE", "PHEV": "HYBRIDE_RECHARGEABLE", "ELECTRIQUE": "ELECTRIQUE", "ELEC": "ELECTRIQUE",
            "EV": "ELECTRIQUE", "GPL": "GAZ", "GAZ": "GAZ", "CNG": "GAZ"}
BOITES = {"BVA": "BVA", "AT": "BVA", "AUTO": "BVA", "AUTOMATIQUE": "BVA", "CVT": "BVA", "DCT": "BVA", "AMT": "BVA",
          "BVM": "BVM", "MT": "BVM", "MANUELLE": "BVM", "MANUAL": "BVM"}
MOTS_SANS_VALEUR = {"BUS", "TRUCKS", "TRUCK", "VL", "VU", "PL"}  # suffixes d'usage qui ne font pas partie de la marque
DEBUT_MOIS_COL = 9  # colonne J (index 0) = janvier


@dataclass
class LectureHistorique:
    annee: int
    feuille: str
    lignes: list = field(default_factory=list)  # lignes produit fusionnées
    anomalies: list = field(default_factory=list)
    nb_lignes_source: int = 0
    nb_ignorees: int = 0


@dataclass
class RapportHistorique:
    problemes: list = field(default_factory=list)
    a_blanc: bool = False
    membres_crees: int = 0
    marques_creees: int = 0
    produits_crees: int = 0
    produits_rapproches: int = 0
    declarations_creees: int = 0
    declarations_ignorees: int = 0
    lignes_creees: int = 0
    totaux: dict = field(default_factory=dict)  # {(code membre, 'AAAA-MM'): unités} : à réconcilier avec l'ancien fichier

    def ajouter(self, gravite, code, message, feuille="", ligne=None):
        self.problemes.append(Probleme(gravite, code, message, feuille, ligne))

    @property
    def erreurs(self):
        return [p for p in self.problemes if p.gravite == "ERREUR"]

    @property
    def alertes(self):
        return [p for p in self.problemes if p.gravite == "ALERTE"]

    def en_texte(self):
        tete = (f"{'SIMULATION' if self.a_blanc else 'CHARGEMENT'} : {self.membres_crees} membre(s), {self.marques_creees} marque(s), "
                f"{self.produits_crees} produit(s) créés ({self.produits_rapproches} rapprochés), {self.declarations_creees} "
                f"déclaration(s) ({self.declarations_ignorees} déjà existantes), {self.lignes_creees} lignes")
        return "\n".join([tete, *[str(p) for p in self.problemes[:60]]])


# ------------------------------------------------------------------------------ conversions
def _texte(v):
    return c.texte_propre(v, 250)


def segment_depuis_libelle(libelle_norm):
    return next((code for motif, code in REGLES_SEGMENT if re.search(motif, libelle_norm)), None)


def origine_depuis_mot(mot):
    mot = c.normaliser(mot)
    for debut, code in (("JAPON", "JAPONAISE"), ("EUROP", "EUROPEENNE"), ("COREE", "COREENNE"), ("CHINO", "CHINOISE"),
                        ("AUTRE", "AUTRES")):
        if mot.startswith(debut):
            return code
    return None


def parse_cylindree(brut):
    if brut in (None, ""):
        return None
    s = str(brut).upper().replace(",", ".").replace("CM3", "").replace("CC", "").replace("L", "").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    if v <= 0:
        return None
    return int(round(v * 1000)) if v < 20 else int(round(v))


def parse_entier_positif(brut):
    try:
        v = int(float(str(brut).replace(",", ".")))
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def parse_vocabulaire(brut, table):
    return table.get(c.normaliser(brut)) if brut not in (None, "", 0, "0") else None


def decouper_modele(libelle):
    """Heuristique de départ (à corriger dans le rapprochement) : le premier mot est le modèle, le reste la version."""
    mots = c.normaliser(libelle).split()
    if not mots:
        return "", ""
    n = 2 if mots[0] in ("NEW", "ALL", "ALLNEW") and len(mots) > 1 else 1
    return " ".join(mots[:n]), " ".join(mots[n:])


def slug(texte, longueur):
    return re.sub(r"[^A-Z0-9]+", "-", c.normaliser(texte)).strip("-")[:longueur]


def marque_canonique(marque_brute, mots_distributeurs):
    mots = c.normaliser(marque_brute).split()
    while len(mots) > 1 and (mots[-1].isdigit() or mots[-1] in MOTS_SANS_VALEUR or mots[-1] in mots_distributeurs):
        mots.pop()
    return " ".join(mots)


# ------------------------------------------------------------------------------ 1. lecture
def lire_historique(contenu: bytes, annee=None, feuille=None, taille_max_ko=30720):
    """Lit un ancien fichier annuel et renvoie des lignes propres (totaux ignorés)."""
    wb = c.lire_classeur_sur(contenu, taille_max_ko, lecture_seule=True)
    nom = feuille or next((n for n in wb.sheetnames if n.strip().upper().startswith("MTM")), wb.sheetnames[0])
    ws = wb[nom]
    lignes_brutes = list(ws.iter_rows(min_row=1, max_row=min(ws.max_row or 6000, 6000), min_col=1, max_col=23, values_only=True))
    if annee is None:
        trouve = re.search(r"(20\d\d)", f"{lignes_brutes[0][0] if lignes_brutes else ''} {nom}")
        annee = int(trouve.group(1)) if trouve else date.today().year
    lecture = LectureHistorique(annee=annee, feuille=nom)
    segment, en_attente = None, []
    for numero, row in enumerate(lignes_brutes, 1):
        if numero < 4:
            continue
        libelle_a = _texte(row[0])
        if libelle_a:
            na = c.normaliser(libelle_a)
            if na.startswith("CATEGORIE"):
                segment = segment_depuis_libelle(na)
            elif na.startswith("SEGMENT"):
                segment = segment_depuis_libelle(na)
                if segment is None:
                    lecture.anomalies.append({"type": "SEGMENT_INCONNU", "ligne": numero, "detail": libelle_a,
                                              "traitement": "lignes suivantes sans segment : à compléter au rapprochement"})
            else:
                m = re.match(r"^TOTAL ORIGINE ?(\w+)", na)
                if m:  # fin d'un bloc : l'origine s'applique aux lignes du bloc
                    origine = origine_depuis_mot(m.group(1))
                    for ligne in en_attente:
                        ligne["origine"] = origine
                    en_attente = []
            continue
        marque, libelle, distributeur = _texte(row[1]), _texte(row[2]), _texte(row[3])
        if not marque or not libelle or "TOTAL" in c.normaliser(marque) or "TOTAL" in c.normaliser(libelle):
            lecture.nb_ignorees += 1 if (marque or libelle) else 0
            continue
        lecture.nb_lignes_source += 1
        mois, anomalies = {}, []
        for m in range(1, 13):
            brut = row[DEBUT_MOIS_COL + m - 1]
            if brut is None or (isinstance(brut, str) and not brut.strip()):
                mois[m] = None
            elif isinstance(brut, (int, float)) and not isinstance(brut, bool):
                if abs(brut - round(brut)) > 1e-9:
                    anomalies.append((m, "DECIMAL", brut, "arrondi"))
                v = int(round(brut))
                if v < 0:
                    anomalies.append((m, "NEGATIF", brut, "mis à 0 (correction à saisir à la main)"))
                    v = 0
                mois[m] = v
            else:
                anomalies.append((m, "TEXTE", str(brut)[:30], "ignoré (considéré non renseigné)"))
                mois[m] = None
        for m, genre, brut, traitement in anomalies:
            lecture.anomalies.append({"type": genre, "ligne": numero, "detail": f"{marque} / {libelle} / mois {m} : {brut}",
                                      "traitement": traitement})
        if not distributeur:
            lecture.anomalies.append({"type": "DISTRIBUTEUR_ABSENT", "ligne": numero, "detail": f"{marque} / {libelle}",
                                      "traitement": "ligne ignorée"})
            continue
        ligne = {"ligne": numero, "segment": segment, "origine": None, "marque": marque, "libelle": libelle,
                 "distributeur": distributeur, "cylindree": row[4], "energie": row[5], "chevaux": row[6], "boite": row[7],
                 "charge": row[8], "mois": mois, "nb_source": 1}
        lecture.lignes.append(ligne)
        en_attente.append(ligne)
    lecture.lignes = _fusionner(lecture)
    return lecture


def cle_ligne(l):
    return f"{c.normaliser(l['marque'])}|{c.normaliser(l['libelle'])}|{c.normaliser(l['distributeur'])}"


def _fusionner(lecture):
    """Une ligne par (marque, libellé, distributeur) : les doublons sont additionnés et signalés."""
    uniques = {}
    for l in lecture.lignes:
        k = cle_ligne(l)
        if k not in uniques:
            uniques[k] = l
            continue
        base = uniques[k]
        base["nb_source"] += 1
        for m in range(1, 13):
            a, b = base["mois"][m], l["mois"][m]
            base["mois"][m] = None if a is None and b is None else (a or 0) + (b or 0)
        if base["segment"] != l["segment"]:
            lecture.anomalies.append({"type": "DOUBLON_SEGMENTS_DIFFERENTS", "ligne": l["ligne"],
                                      "detail": f"{l['marque']} / {l['libelle']} : segments {base['segment']} et {l['segment']}",
                                      "traitement": f"fusionné, segment {base['segment']} conservé"})
        base["origine"] = base["origine"] or l["origine"]
    fusions = [l for l in uniques.values() if l["nb_source"] > 1]
    for l in fusions:
        lecture.anomalies.append({"type": "DOUBLON_FUSIONNE", "ligne": l["ligne"],
                                  "detail": f"{l['marque']} / {l['libelle']} ({l['distributeur']}) : {l['nb_source']} lignes",
                                  "traitement": "quantités additionnées (vérifier qu'il ne s'agit pas d'une double saisie)"})
    return list(uniques.values())


# ------------------------------------------------------------------------------ 2. rapprochement
def ecrire_rapprochement(lecture: LectureHistorique):
    """Classeur de rapprochement avec propositions automatiques (cellules jaunes = à valider ou corriger)."""
    existants = {c.normaliser(m.raison_sociale): m for m in Membre.objects.all()}
    marques_existantes = {c.normaliser(m.code): m for m in Marque.objects.all()}
    alias = {}
    for a in AliasProduit.objects.filter(membre__isnull=False).select_related("produit"):
        alias[(a.membre_id, a.libelle_normalise)] = a.produit
    mots_distributeurs = {c.normaliser(l["distributeur"]).split()[0] for l in lecture.lignes}
    wb = Workbook()
    wb.properties.creator = "GIPAME"
    ws = wb.active
    ws.title = "LISEZ-MOI"
    ws.column_dimensions["A"].width = 120
    consignes = [
        "Rapprochement de l'historique " + str(lecture.annee),
        "Les cellules jaunes sont des PROPOSITIONS automatiques : validez-les ou corrigez-les, puis rechargez le fichier.",
        "MEMBRES : un code court et immuable par distributeur (ex. CFAO), sa raison sociale ; GROUPE si plusieurs membres appartiennent au même groupe.",
        "MARQUES : l'ancien fichier mélange parfois marque et distributeur (« SUZUKI CFAO », « FOTON SIFF », « ZHONGTONG 2 ») : corrigez le NOM_MARQUE.",
        "PRODUITS : une ligne par produit de l'ancien fichier. MODELE = famille (ex. STARLET) ; FINITION = le reste. Deux lignes qui désignent le même produit "
        "pour des distributeurs différents doivent avoir le même MODELE, la même FINITION et les mêmes caractéristiques.",
        "SEGMENT : code de la grille GIPAME-V1 (AB, M1, M2, H, SUV, 4X4_MEDIUM, 4X4_LARGE, PU_4X2, PU_4X4, PU_HD, VAN, BUS_MOINS_22, BUS_23_34, BUS_PLUS_34, "
        "CAMION_3_6T, CAMION_6_15T, TRACTEUR_PLUS_15T, PORTEUR_PLUS_15T).",
        "Ne modifiez ni la colonne CLE ni l'ordre des colonnes. Les quantités ne sont PAS dans ce fichier : elles sont relues dans l'ancien fichier.",
        "Les totaux de l'ancien fichier sont ignorés (ils ne se réconcilient pas) : le chargement affiche des totaux recalculés à comparer.",
    ]
    for i, texte in enumerate(consignes, 1):
        c.ecrire_texte(ws.cell(i, 1), texte)
        ws.cell(i, 1).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(i, 1).font = c.police(gras=i == 1, taille=12 if i == 1 else 10)

    def saisie(cellule):
        cellule.fill = c.FOND_SAISIE
        cellule.border = c.BORDURE
        cellule.font = c.police()

    # --- MEMBRES
    wm = wb.create_sheet("MEMBRES")
    for i, titre in enumerate(["Distributeur (ancien fichier)", "Nb lignes", "Total unités", "CODE_MEMBRE", "RAISON_SOCIALE",
                               "GROUPE (facultatif)", "Statut"], 1):
        wm.cell(1, i, titre)
        c.style_entete(wm.cell(1, i))
    distributeurs = {}
    for l in lecture.lignes:
        d = distributeurs.setdefault(c.normaliser(l["distributeur"]), {"brut": l["distributeur"], "n": 0, "total": 0})
        d["n"] += 1
        d["total"] += sum(v or 0 for v in l["mois"].values())
    for r, (norm, d) in enumerate(sorted(distributeurs.items()), 2):
        membre = existants.get(norm)
        for col, v in ((1, norm), (2, d["n"]), (3, d["total"]), (4, membre.code if membre else slug(d["brut"], 20)),
                       (5, membre.raison_sociale if membre else d["brut"]), (6, ""), (7, "EXISTE" if membre else "A CREER")):
            if isinstance(v, str):
                c.ecrire_texte(wm.cell(r, col), v)
            else:
                wm.cell(r, col, v)
            wm.cell(r, col).font = c.police()
        for col in (4, 5, 6):
            saisie(wm.cell(r, col))
    # --- MARQUES
    wk = wb.create_sheet("MARQUES")
    for i, titre in enumerate(["Marque (ancien fichier)", "Nb lignes", "CODE_MARQUE", "NOM_MARQUE", "ORIGINE", "Statut"], 1):
        wk.cell(1, i, titre)
        c.style_entete(wk.cell(1, i))
    marques = {}
    for l in lecture.lignes:
        m = marques.setdefault(c.normaliser(l["marque"]), {"n": 0, "origines": {}})
        m["n"] += 1
        if l["origine"]:
            m["origines"][l["origine"]] = m["origines"].get(l["origine"], 0) + 1
    for r, (norm, m) in enumerate(sorted(marques.items()), 2):
        canon = marque_canonique(norm, mots_distributeurs)
        origine = max(m["origines"], key=m["origines"].get) if m["origines"] else ""
        statut = "EXISTE" if slug(canon, 30) in marques_existantes else ("A VERIFIER" if canon != norm else "A CREER")
        for col, v in ((1, norm), (2, m["n"]), (3, slug(canon, 30)), (4, canon), (5, origine), (6, statut)):
            if isinstance(v, str):
                c.ecrire_texte(wk.cell(r, col), v)
            else:
                wk.cell(r, col, v)
            wk.cell(r, col).font = c.police()
        for col in (3, 4, 5):
            saisie(wk.cell(r, col))
    # --- PRODUITS
    wp = wb.create_sheet("PRODUITS")
    titres = ["CLE", "Distributeur", "Marque (ancien)", "Libellé (ancien)", "Nb lignes source", "Total unités",
              "CODE_PRODUIT_EXISTANT", "MODELE", "FINITION", "ENERGIE", "BOITE", "CYLINDREE_CM3", "PUISSANCE_CV",
              "CHARGE_UTILE_KG", "MOTRICITE", "SEGMENT", "Statut", "Commentaire"]
    for i, titre in enumerate(titres, 1):
        wp.cell(1, i, titre)
        c.style_entete(wp.cell(1, i))
    wp.row_dimensions[1].height = 32
    nb_a_completer = 0
    for r, l in enumerate(sorted(lecture.lignes, key=lambda x: (c.normaliser(x["distributeur"]), c.normaliser(x["marque"]),
                                                                  c.normaliser(x["libelle"]))), 2):
        modele, finition = decouper_modele(l["libelle"])
        membre = existants.get(c.normaliser(l["distributeur"]))
        produit_alias = alias.get((membre.id, " ".join(l["libelle"].upper().split()))) if membre else None
        energie, boite = parse_vocabulaire(l["energie"], ENERGIES), parse_vocabulaire(l["boite"], BOITES)
        complet = bool(modele and l["segment"] and (energie or produit_alias))
        nb_a_completer += 0 if complet else 1
        valeurs = [cle_ligne(l), c.normaliser(l["distributeur"]), c.normaliser(l["marque"]), l["libelle"], l["nb_source"],
                   sum(v or 0 for v in l["mois"].values()), produit_alias.code if produit_alias else "", modele, finition,
                   energie or "", boite or "", parse_cylindree(l["cylindree"]), parse_entier_positif(l["chevaux"]),
                   parse_entier_positif(l["charge"]), "", l["segment"] or "",
                   "RAPPROCHE" if produit_alias else ("AUTO" if complet else "A COMPLETER"), ""]
        for col, v in enumerate(valeurs, 1):
            if isinstance(v, str):
                c.ecrire_texte(wp.cell(r, col), v)
            else:
                wp.cell(r, col, v)
            wp.cell(r, col).font = c.police()
        for col in range(7, 19):
            saisie(wp.cell(r, col))
    derniere = max(2, len(lecture.lignes) + 1)
    for lettre, valeurs in (("J", ",".join(Energie.objects.values_list("code", flat=True))),
                            ("K", ",".join(Boite.objects.values_list("code", flat=True)))):
        dv = DataValidation(type="list", formula1=f'"{valeurs}"', allow_blank=True)
        wp.add_data_validation(dv)
        dv.add(f"{lettre}2:{lettre}{derniere}")
    codes_segments = ",".join(Segment.objects.filter(categorie__segmentation__statut="COURANTE").values_list("code", flat=True))
    if codes_segments and len(codes_segments) < 250:
        dv = DataValidation(type="list", formula1=f'"{codes_segments}"', allow_blank=True)
        wp.add_data_validation(dv)
        dv.add(f"P2:P{derniere}")
    for lettre, largeur in {"A": 8, "B": 18, "C": 16, "D": 44, "E": 8, "F": 10, "G": 16, "H": 16, "I": 22, "J": 12, "K": 8,
                            "L": 11, "M": 10, "N": 11, "O": 10, "P": 18, "Q": 13, "R": 30}.items():
        wp.column_dimensions[lettre].width = largeur
    wp.freeze_panes = "E2"
    for feuille, largeurs in ((wm, {"A": 26, "B": 9, "C": 11, "D": 20, "E": 34, "F": 18, "G": 12}),
                              (wk, {"A": 24, "B": 9, "C": 22, "D": 24, "E": 14, "F": 12})):
        for lettre, largeur in largeurs.items():
            feuille.column_dimensions[lettre].width = largeur
    # --- ANOMALIES
    wa = wb.create_sheet("ANOMALIES")
    for i, titre in enumerate(["Type", "Ligne source", "Détail", "Traitement appliqué"], 1):
        wa.cell(1, i, titre)
        c.style_entete(wa.cell(1, i))
    for r, a in enumerate(lecture.anomalies, 2):
        for col, v in enumerate((a["type"], a["ligne"], a["detail"], a["traitement"]), 1):
            if isinstance(v, str):
                c.ecrire_texte(wa.cell(r, col), v)
            else:
                wa.cell(r, col, v)
            wa.cell(r, col).font = c.police()
    for lettre, largeur in {"A": 28, "B": 11, "C": 80, "D": 60}.items():
        wa.column_dimensions[lettre].width = largeur
    sortie = io.BytesIO()
    wb.save(sortie)
    return sortie.getvalue(), nb_a_completer


def lire_rapprochement(contenu: bytes):
    """Relit le rapprochement validé : {membres, marques, produits} indexés par clé normalisée."""
    wb = c.lire_classeur_sur(contenu, 30720)
    for nom in ("MEMBRES", "MARQUES", "PRODUITS"):
        if nom not in wb.sheetnames:
            raise c.FichierInvalide(f"Onglet « {nom} » absent du fichier de rapprochement.")

    def lignes(feuille, n):
        return [tuple(r) for r in wb[feuille].iter_rows(min_row=2, max_col=n, values_only=True) if r[0] not in (None, "")]

    membres = {_texte(r[0]): {"code": _texte(r[3]), "raison": _texte(r[4]), "groupe": _texte(r[5])} for r in lignes("MEMBRES", 7)}
    marques = {_texte(r[0]): {"code": _texte(r[2]), "nom": _texte(r[3]), "origine": _texte(r[4])} for r in lignes("MARQUES", 6)}
    produits = {}
    for r in lignes("PRODUITS", 18):
        produits[_texte(r[0])] = {
            "code_existant": _texte(r[6]), "modele": _texte(r[7]), "finition": _texte(r[8]).upper(), "energie": _texte(r[9]),
            "boite": _texte(r[10]), "cylindree": parse_entier_positif(r[11]), "puissance": parse_entier_positif(r[12]),
            "charge": parse_entier_positif(r[13]), "motricite": _texte(r[14]).upper(), "segment": _texte(r[15])}
    return {"membres": membres, "marques": marques, "produits": produits}


# ------------------------------------------------------------------------------ 3. chargement
def charger_historique(contenu_historique: bytes, contenu_rapprochement: bytes, annee=None, a_blanc=False, utilisateur=None,
                       nom_fichier="historique.xlsx"):
    """Applique le rapprochement validé. a_blanc=True : contrôles et comptages, aucune écriture."""
    lecture = lire_historique(contenu_historique, annee)
    mapping = lire_rapprochement(contenu_rapprochement)
    rapport = RapportHistorique(a_blanc=a_blanc)
    plan = _construire_plan(lecture, mapping, rapport)
    for a in lecture.anomalies:
        rapport.ajouter("ALERTE", a["type"], f"ligne {a['ligne']} : {a['detail']} → {a['traitement']}")
    if rapport.erreurs:
        return rapport
    try:
        with transaction.atomic():
            if utilisateur is not None:
                with connection.cursor() as cur:
                    cur.execute("SELECT set_config('app.utilisateur_id', %s, true)", [str(utilisateur.pk)])
            _appliquer(plan, lecture, contenu_historique, nom_fichier, utilisateur, a_blanc, rapport)
            if a_blanc:
                transaction.set_rollback(True)
    except _Abandon:
        pass  # le rapport contient l'erreur ; la transaction est annulée
    return rapport


def _construire_plan(lecture, mapping, rapport):
    """Valide le rapprochement ligne par ligne et prépare ce qu'il faut créer."""
    plan = []
    for l in lecture.lignes:
        cle, marque_n, distrib_n = cle_ligne(l), c.normaliser(l["marque"]), c.normaliser(l["distributeur"])
        p, m, k = mapping["produits"].get(cle), mapping["membres"].get(distrib_n), mapping["marques"].get(marque_n)
        if p is None or m is None or k is None:
            rapport.ajouter("ERREUR", "SANS_RAPPROCHEMENT", f"ligne {l['ligne']} : « {l['marque']} / {l['libelle']} / "
                            f"{l['distributeur']} » absente du fichier de rapprochement : relancez l'analyse.")
            continue
        manques = [nom for nom, valeur in (("CODE_MEMBRE", m["code"]), ("CODE_MARQUE", k["code"]), ("NOM_MARQUE", k["nom"]),
                                           ("ORIGINE", k["origine"]), ("MODELE", p["modele"] or p["code_existant"]),
                                           ("SEGMENT", p["segment"] or p["code_existant"])) if not valeur]
        if manques:
            rapport.ajouter("ERREUR", "RAPPROCHEMENT_INCOMPLET", f"ligne {l['ligne']} ({l['marque']} / {l['libelle']}) : "
                            f"{', '.join(manques)} à renseigner.")
            continue
        plan.append((l, m, k, p))
    return plan


def _appliquer(plan, lecture, contenu_historique, nom_fichier, utilisateur, a_blanc, rapport):
    seg = Segmentation.objects.get(statut="COURANTE")
    segments = {s.code: s for s in Segment.objects.filter(categorie__segmentation=seg)}
    energies, boites = {e.code: e for e in Energie.objects.all()}, {b.code: b for b in Boite.objects.all()}
    origines = {o.code: o for o in Origine.objects.all()}
    debut = date(lecture.annee, 1, 1)
    membres, marques, modeles, produits_par_ligne = {}, {}, {}, {}
    for l, m, k, p in plan:
        if m["code"] not in membres:
            membre, cree = Membre.objects.get_or_create(code=m["code"], defaults={"raison_sociale": m["raison"] or m["code"]})
            rapport.membres_crees += cree
            if not membre.periodes.exists():
                PeriodeAdhesion.objects.create(membre=membre, date_debut=debut)
            membres[m["code"]] = membre
        if k["code"] not in marques:
            if k["origine"] not in origines:
                rapport.ajouter("ERREUR", "ORIGINE_INCONNUE", f"Origine « {k['origine']} » inconnue pour la marque {k['nom']}.")
                raise _Abandon()
            marque, cree = Marque.objects.get_or_create(code=k["code"], defaults={"nom": k["nom"], "origine": origines[k["origine"]]})
            rapport.marques_creees += cree
            marques[k["code"]] = marque
        membre, marque = membres[m["code"]], marques[k["code"]]
        if not Concession.objects.filter(membre=membre, marque=marque).exists():
            Concession.objects.create(membre=membre, marque=marque, date_debut=debut)
        produits_par_ligne[cle_ligne(l)] = _produit_pour(l, p, membre, marque, modeles, segments, seg, energies, boites, rapport)
    # déclarations : (membre, produit) -> quantités mensuelles, sommées si deux lignes visent le même produit
    cumuls = {}
    for l, m, k, p in plan:
        produit = produits_par_ligne[cle_ligne(l)]
        for mois, valeur in l["mois"].items():
            par_mois = cumuls.setdefault((m["code"], mois), {"declare": False, "lignes": {}})
            if valeur is not None:
                par_mois["declare"] = True
            par_mois["lignes"][produit.id] = par_mois["lignes"].get(produit.id, 0) + (valeur or 0)
    empreinte = hashlib.sha256(contenu_historique).hexdigest()
    for (code, mois), info in sorted(cumuls.items()):
        if not info["declare"]:
            continue  # aucun chiffre pour ce mois : pas de déclaration (≠ zéro)
        premier = date(lecture.annee, mois, 1)
        if premier > date.today().replace(day=1):
            rapport.ajouter("ALERTE", "MOIS_FUTUR", f"{code} {premier:%Y-%m} : mois futur ignoré.")
            continue
        membre = membres[code]
        if Declaration.objects.filter(membre=membre, mois=premier, statut="SOUMISE").exists():
            rapport.declarations_ignorees += 1
            rapport.ajouter("ALERTE", "DECLARATION_EXISTANTE", f"{code} {premier:%Y-%m} : une déclaration soumise existe déjà, ignorée.")
            continue
        decl = Declaration.objects.create(membre=membre, mois=premier, version=1, source="IMPORT_HISTORIQUE",
                                          version_gabarit="HISTORIQUE", empreinte_fichier=empreinte)
        LigneVente.objects.bulk_create([LigneVente(declaration=decl, produit_id=pid, quantite=q) for pid, q in info["lignes"].items()])
        total = sum(info["lignes"].values())
        decl.attestation_complete, decl.aucune_vente_confirmee, decl.statut = True, total == 0, "SOUMISE"
        decl.save()
        rapport.declarations_creees += 1
        rapport.lignes_creees += len(info["lignes"])
        rapport.totaux[(code, f"{premier:%Y-%m}")] = total
    if not a_blanc:
        DepotFichier.objects.create(
            type_depot="HISTORIQUE", nom_fichier=c.texte_propre(nom_fichier, 255) or "historique.xlsx", taille_octets=len(contenu_historique),
            empreinte_sha256=empreinte, resultat="ACCEPTE_AVEC_ALERTES" if rapport.alertes else "ACCEPTE",
            nb_erreurs=0, nb_alertes=len(rapport.alertes), depose_par=utilisateur,
            rapport=[{"gravite": p.gravite, "code": p.code, "message": p.message} for p in rapport.problemes[:200]])


class _Abandon(Exception):
    pass


def _produit_pour(l, p, membre, marque, modeles, segments, seg, energies, boites, rapport):
    """Trouve ou crée le produit d'une ligne de l'ancien fichier (alias, puis signature, puis création)."""
    libelle_alias = c.texte_propre(l["libelle"], 200)
    produit = None
    if p["code_existant"]:
        produit = Produit.objects.filter(code=p["code_existant"]).first()
    if produit is None:
        alias = AliasProduit.objects.filter(membre=membre, libelle_normalise=" ".join(libelle_alias.upper().split())).select_related("produit").first()
        produit = alias.produit if alias else None
    if produit is None:
        nom_modele = p["modele"]
        modele = modeles.get((marque.id, c.normaliser(nom_modele)))
        if modele is None:
            modele = next((x for x in Modele.objects.filter(marque=marque) if c.normaliser(x.nom) == c.normaliser(nom_modele)), None)
            if modele is None:
                code = f"{marque.code}-{slug(nom_modele, 30)}"[:40]
                n = 1
                while Modele.objects.filter(code=code).exists():
                    n += 1
                    code = f"{marque.code}-{slug(nom_modele, 28)}-{n}"[:40]
                modele = Modele.objects.create(marque=marque, code=code, nom=c.texte_propre(nom_modele, 120))
            modeles[(marque.id, c.normaliser(nom_modele))] = modele
        energie, boite = energies.get(p["energie"]), boites.get(p["boite"])
        candidats = Produit.objects.filter(modele=modele, statut__in=["ACTIF", "ARCHIVE"], finition=p["finition"], energie=energie,
                                           boite=boite, cylindree_cm3=p["cylindree"], puissance_fiscale_cv=p["puissance"],
                                           motricite=p["motricite"])
        produit = candidats.first()
        if produit is None:
            produit = Produit.objects.create(
                code="", modele=modele, finition=p["finition"], energie=energie, boite=boite, cylindree_cm3=p["cylindree"],
                puissance_fiscale_cv=p["puissance"], charge_utile_kg=p["charge"], motricite=p["motricite"],
                libelle_affiche=libelle_alias, statut="ACTIF")
            rapport.produits_crees += 1
            segment = segments.get(p["segment"])
            if segment is None:
                rapport.ajouter("ERREUR", "SEGMENT_INCONNU", f"Segment « {p['segment']} » inconnu pour {libelle_alias}.")
                raise _Abandon()
            ClassementProduit.objects.create(produit=produit, segmentation=seg, segment=segment, source="IMPORT",
                                             justification="Reprise de l'historique (rapprochement validé)")
        else:
            rapport.produits_rapproches += 1
    else:
        rapport.produits_rapproches += 1
    try:
        with transaction.atomic():
            AliasProduit.objects.create(membre=membre, libelle_brut=libelle_alias, produit=produit, source="IMPORT_HISTORIQUE")
    except IntegrityError:
        pass  # alias déjà connu
    return produit
