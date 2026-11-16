"""Gabarit Excel : ce que le membre reçoit, et ce qu'il ne doit JAMAIS contenir."""
import io
import zipfile

from django.test import TestCase
from openpyxl import load_workbook

from collecte.demo import VENTES, charger_demo, premier_du_mois
from collecte.excel import commun as c
from collecte.models import Concession, Marque, Modele, Produit

from .outils import generer


class Gabarit(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()
        cls.mois = premier_du_mois(0)

    def test_structure_onglets_et_cachettes(self):
        wb = load_workbook(io.BytesIO(generer(self.d, "A1", self.mois)))
        self.assertEqual(wb.sheetnames, ["DECLARATION", "AJOUTS", "LISEZ-MOI", "_LISTES", "_META"])
        self.assertEqual([ws.sheet_state for ws in wb.worksheets], ["visible", "visible", "visible", "veryHidden", "veryHidden"])
        self.assertEqual(wb.properties.creator, "GIPAME")

    def test_le_fichier_ne_contient_que_les_donnees_du_membre(self):
        wb = load_workbook(io.BytesIO(generer(self.d, "A1", self.mois)))
        textes, nombres = set(), []
        for ws in wb.worksheets:
            for ligne in ws.iter_rows(values_only=True):
                for v in ligne:
                    (textes.add(v) if isinstance(v, str) else nombres.append(v)) if v is not None else None
        interdits = {f"P{n:02d}" for n in range(1, 20)} - {"P01", "P14"}
        self.assertFalse(interdits & textes)
        for nom in ("Beta", "Gamma", "Delta", "Alpha Trucks", "Alpha Auto", "BETA", "GAMMA", "DELTA", "SIGMA"):
            self.assertFalse(any(nom in t for t in textes if isinstance(t, str) and not t.startswith("Alpha Motors")),
                             f"« {nom} » ne doit pas apparaître dans le fichier de A1")
        for valeur in (80, 70, 40, 90, 15):  # chiffres des autres membres
            self.assertNotIn(valeur, nombres)

    def test_lignes_prerempli_a_zero_et_repere_du_mois_precedent(self):
        ws = load_workbook(io.BytesIO(generer(self.d, "A1", self.mois)))["DECLARATION"]
        lignes = {ws.cell(r, 1).value: (ws.cell(r, 6).value, ws.cell(r, 7).value) for r in (8, 9)}
        self.assertEqual(lignes, {"P01": (VENTES["A1"]["P01"], 0), "P14": (VENTES["A1"]["P14"], 0)})
        self.assertEqual(ws.cell(10, 1).value, "TOTAL")
        self.assertEqual(ws.cell(10, 7).value, "=SUM(G8:G9)")

    def test_protection_controles_de_saisie_et_signature(self):
        wb = load_workbook(io.BytesIO(generer(self.d, "A1", self.mois)))
        ws = wb["DECLARATION"]
        self.assertTrue(ws.protection.sheet)
        self.assertTrue(ws["A8"].protection.locked)          # code produit : verrouillé
        self.assertFalse(ws["G8"].protection.locked)         # quantité : saisissable
        self.assertFalse(ws["G2"].protection.locked)
        types = {dv.type for dv in ws.data_validations.dataValidation}
        self.assertEqual(types, {"whole", "list"})
        meta = {r[0]: r[1] for r in wb["_META"].iter_rows(values_only=True)}
        codes = [r[0] for r in wb["_LISTES"].iter_rows(min_row=2, min_col=4, max_col=4, values_only=True) if r[0]]
        self.assertTrue(c.signature_valide(meta["signature"], meta["gabarit_version"], "A1", self.mois, 1, codes))
        self.assertFalse(c.signature_valide(meta["signature"], meta["gabarit_version"], "B1", self.mois, 1, codes))
        self.assertFalse(c.signature_valide(meta["signature"], meta["gabarit_version"], "A1", self.mois, 2, codes))

    def test_les_textes_sont_ecrits_comme_du_texte_jamais_comme_formule(self):
        marque = Marque.objects.get(code="ALPHA-M")
        Produit.objects.create(code="PX", modele=Modele.objects.get(code="ALPHA-M-CITADINE"), finition="PIEGE",
                               libelle_affiche="=HYPERLINK(\"http://exemple\",\"x\")+1", statut="ACTIF")
        wb = load_workbook(io.BytesIO(generer(self.d, "A1", self.mois)))
        ws = wb["DECLARATION"]
        cellule = next(ws.cell(r, 3) for r in range(8, 12) if ws.cell(r, 1).value == "PX")
        self.assertEqual(cellule.data_type, "s")
        self.assertTrue(cellule.value.startswith("=HYPERLINK"))

    def test_ni_macro_ni_lien_externe(self):
        with zipfile.ZipFile(io.BytesIO(generer(self.d, "A1", self.mois))) as z:
            noms = " ".join(z.namelist()).lower()
        for interdit in ("vbaproject", "externallinks", "embeddings", "activex"):
            self.assertNotIn(interdit, noms)

    def test_un_membre_sans_marque_obtient_un_gabarit_vide_et_non_une_erreur(self):
        Concession.objects.filter(membre=self.d.membres["A3"]).update(date_fin=premier_du_mois(-6))
        wb = load_workbook(io.BytesIO(generer(self.d, "A3", self.mois)))
        self.assertEqual(wb["DECLARATION"].cell(8, 1).value, "TOTAL")
