"""Le cycle complet, du gabarit à la publication, chaque étape avec le rôle PostgreSQL de son acteur."""
import io

from django.test import TestCase
from openpyxl import load_workbook

from collecte.contexte import en_role
from collecte.cycle import executer_cycle_demo
from collecte.demo import VENTES, charger_demo
from collecte.models import CelluleAgregat, Declaration, DepotFichier, Publication


class CycleComplet(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()

    def test_cycle_complet(self):
        resultat = executer_cycle_demo()
        # 1. chaque membre : fichier accepté et déclaration soumise (les alertes de copie du mois précédent n'empêchent rien)
        for code, rapport in resultat.rapports.items():
            self.assertTrue(rapport.ok, f"{code}: {rapport.en_texte()}")
            self.assertEqual(rapport.statut_declaration, "SOUMISE", code)
            self.assertEqual(rapport.total_unites, sum(VENTES[code].values()), code)
        self.assertEqual(Declaration.objects.filter(mois=resultat.mois, statut="SOUMISE").count(), 6)
        # 2. le fichier volontairement faux de A1 est rejeté, avec des messages exploitables, et n'a rien écrit
        self.assertEqual(resultat.rapport_faux.resultat, "REJETE")
        self.assertEqual([p.code for p in resultat.rapport_faux.erreurs], ["QUANTITE", "QUANTITE"])
        self.assertEqual(DepotFichier.objects.filter(resultat="REJETE").count(), 1)
        # 3. la publication reprend les règles de confidentialité
        pub = Publication.objects.get(pk=resultat.publication_id)
        cellules = {(c.dimension, c.cle): c for c in CelluleAgregat.objects.filter(publication=pub)}
        self.assertEqual(pub.couverture_pct, 100)
        self.assertEqual((cellules[("TOTAL", "ALL")].total, cellules[("SEGMENT", "AB")].total), (551, 270))
        self.assertTrue(cellules[("SEGMENT", "M1")].supprime and cellules[("SEGMENT", "M1")].total is None)
        # 4. les 9 fichiers d'export sont lisibles et propres à leur destinataire
        exports = {nom: contenu for sous, nom, contenu in resultat.fichiers if sous == "exports"}
        self.assertEqual(len(exports), 9)
        annee_a1 = load_workbook(io.BytesIO(exports[f"annee_A1_{resultat.mois.year}.xlsx"]))["MES VENTES"]
        self.assertEqual({r[0].value for r in annee_a1.iter_rows(min_row=7) if r[0].value not in (None, "TOTAL")}, {"P01", "P14"})
        bureau = load_workbook(io.BytesIO(exports[f"publication_{resultat.mois:%Y-%m}_bureau.xlsx"]))
        self.assertNotIn("Contributeurs", [c.value for c in bureau["Segments"][1]])
        suivi = load_workbook(io.BytesIO(exports["suivi_depots.xlsx"]))["SUIVI"]
        self.assertTrue(any(r[0].value == "B3" and r[2].value == "SOUMISE" for r in suivi.iter_rows(min_row=5)))
