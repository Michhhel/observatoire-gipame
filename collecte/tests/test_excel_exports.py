"""Exports Excel : chaque destinataire ne reçoit que ce que son rôle a le droit de lire."""
import io

from django.db import ProgrammingError
from django.test import TestCase
from openpyxl import load_workbook

from collecte.contexte import en_role
from collecte.demo import VENTES, charger_demo
from collecte.excel import commun as c_
from collecte.excel import exports
from collecte.models import ParametreSysteme, Publication
from collecte.services import calculer_publication

from .outils import doit_echouer

libelle_mois = c_.libelle_mois


def lignes_de(ws, premiere=1):
    return [[c.value for c in row] for row in ws.iter_rows(min_row=premiere)]


class ExportsExcel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()
        with en_role("gipame_calcul"):
            cls.pub = calculer_publication(cls.d.mois_plein)

    def _annee(self, code="A1"):
        m, u = self.d.membres[code], self.d.users[code]
        with en_role("gipame_membre", membre_id=m.id, utilisateur_id=u.id):
            return load_workbook(io.BytesIO(exports.exporter_annee_membre(m, self.d.mois_plein.year)))

    def test_mon_annee_ne_contient_que_mes_ventes_et_le_marche_publie(self):
        wb = self._annee("A1")
        self.assertEqual(wb.sheetnames, ["MES VENTES", "MARCHE"])
        ws = wb["MES VENTES"]
        lignes = {r[0]: r for r in lignes_de(ws, 7) if r[0] not in (None, "TOTAL")}
        self.assertEqual(set(lignes), {"P01", "P14"})
        m_plein, m_partiel = 5 + self.d.mois_plein.month, 5 + self.d.mois_partiel.month
        self.assertEqual((lignes["P01"][m_plein - 1], lignes["P14"][m_partiel - 1]), (100, 10))
        self.assertEqual(ws.cell(6, m_plein).value, "v1")
        autres_mois = [m for m in range(1, 13) if m not in (self.d.mois_plein.month, self.d.mois_partiel.month)]
        self.assertTrue(all(lignes["P01"][5 + m - 1] is None for m in autres_mois))  # mois non déclaré = case vide
        self.assertTrue(str(lignes["P01"][17]).startswith("=SUM("))                    # cumul = formule
        marche = {r[1]: r for r in lignes_de(wb["MARCHE"], 6) if r[1]}
        col = 2 + self.d.mois_plein.month
        self.assertEqual(marche["TOTAL:ALL"][col - 1], 551)
        self.assertEqual(marche["SEGMENT:AB"][col - 1], 270)
        self.assertEqual(marche["SEGMENT:M1"][col - 1], "c")      # confidentiel : jamais de chiffre
        self.assertEqual(marche["ORIGINE:JAPONAISE"][col - 1], "c")
        toutes_les_valeurs = [v for r in lignes_de(wb["MES VENTES"]) + lignes_de(wb["MARCHE"]) for v in r if v is not None]
        for chiffre_d_un_autre in (80, 70, 90):
            self.assertNotIn(chiffre_d_un_autre, toutes_les_valeurs)

    def test_les_exports_de_deux_membres_sont_distincts(self):
        codes_b1 = {r[0] for r in lignes_de(self._annee("B1")["MES VENTES"], 7) if r[0] not in (None, "TOTAL")}
        self.assertEqual(codes_b1, {"P04", "P07", "P17", "P10", "P11", "P18"})
        self.assertEqual(self._annee("B1")["MES VENTES"]["B2"].value, None)

    def test_publication_pour_le_bureau_sans_detail_pour_la_gestion_avec_detail(self):
        with en_role("gipame_bureau", utilisateur_id=self.d.users["president"].id):
            pub = Publication.objects.get(pk=self.pub.pk)
            wb = load_workbook(io.BytesIO(exports.exporter_publication(pub)))
            doit_echouer_detail = lambda: exports.exporter_publication(pub, detail=True)  # noqa: E731
            doit_echouer(self, doit_echouer_detail, ProgrammingError)  # n_contributeurs et motifs : interdits au bureau
        self.assertEqual(wb.sheetnames, ["RESUME", "Total", "Catégories", "Segments", "Origines des marques", "Énergies"])
        segments = {r[0]: r for r in lignes_de(wb["Segments"], 2)}
        self.assertEqual((segments["AB"][2], segments["M1"][2], segments["VAN"][2]), (270, "c", "c"))
        self.assertEqual(lignes_de(wb["Segments"], 1)[0], ["Clé", "Libellé", "Total"])
        with en_role("gipame_gestion"):
            pub = Publication.objects.get(pk=self.pub.pk)
            wb2 = load_workbook(io.BytesIO(exports.exporter_publication(pub, detail=True)))
        detail = {r[0]: r for r in lignes_de(wb2["Segments"], 2)}
        self.assertEqual(lignes_de(wb2["Segments"], 1)[0], ["Clé", "Libellé", "Total", "Contributeurs", "Motif de suppression"])
        self.assertEqual((detail["M1"][3], detail["M1"][4], detail["SUV"][4]), (2, "SEUIL", "DOMINANCE"))

    def test_suivi_des_depots_ne_contient_aucune_quantite(self):
        with en_role("gipame_gestion", utilisateur_id=self.d.users["gestionnaire"].id):
            ParametreSysteme.objects.filter(cle="jours_grace_depot").update(valeur="-1")  # (-1 : indépendant du jour du test)
            wb = load_workbook(io.BytesIO(exports.exporter_suivi_depots()))
        lignes = lignes_de(wb["SUIVI"], 5)
        mois_partiel = libelle_mois(self.d.mois_partiel)
        b3 = [r for r in lignes if r[0] == "B3" and r[1] == mois_partiel]
        self.assertEqual([(r[2], r[6]) for r in b3], [("Non déposée", "OUI")])      # mois échu, rien déposé : en retard
        a1 = [r for r in lignes if r[0] == "A1" and r[1] == mois_partiel]
        self.assertEqual([(r[2], r[6]) for r in a1], [("SOUMISE", "NON")])
        self.assertEqual(lignes_de(wb["SUIVI"], 4)[0],
                         ["Membre", "Mois", "Statut du dépôt", "Version", "Soumise le", "Date limite (délai de grâce inclus)", "En retard"])
        valeurs_numeriques = {v for r in lignes for v in r if isinstance(v, (int, float))}
        self.assertTrue(valeurs_numeriques <= {1})  # seule colonne numérique : le n° de version, jamais une quantité
