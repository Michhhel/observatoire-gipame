"""Tests de non-fuite : aucune page du portail ne montre à un compte une donnée qui n'est pas la sienne.

Méthode : on fait déclarer à A2 des quantités « signature » (nombres improbables), puis on parcourt
toutes les pages accessibles à A1, à la gestion et au bureau en vérifiant que ces nombres n'y
apparaissent jamais. Les URL d'objets d'A2 (rapport, confirmation) répondent 404 à A1.
"""
import re

from collecte.models import Declaration, DepotFichier, LigneVente
from portail.formats import INSECABLE, premier_du_mois

from .outils import TestPortail

SIGNATURES = (7919, 7907)  # quantités signature d'A2 (nombres premiers, jamais produits par le jeu de démo)


def contient_signature(html):
    texte = html.replace(INSECABLE, "").replace(" ", "")
    return any(re.search(rf"\b{s}\b", texte) for s in SIGNATURES)


class NonFuite(TestPortail):
    def setUp(self):
        self.mois = premier_du_mois(decalage=-1)
        self.connecter("user_a2")
        self.deposer(self.mois, quantites={"P02": SIGNATURES[0], "P15": SIGNATURES[1]}, motif="correction signature")
        self.depot_a2 = DepotFichier.objects.filter(membre=self.d.membres["A2"]).latest("cree_le")
        self.decl_a2 = self.depot_a2.declaration
        self.client.post(f"/declarer/soumettre/{self.decl_a2.id}/", {"attestation": "on"})
        self.client.logout()
        assert LigneVente.objects.filter(declaration=self.decl_a2, quantite=SIGNATURES[0]).exists()

    def pages_membre(self):
        annee = self.mois.year
        return ["/accueil/", "/declarer/", f"/declarer/?mois={self.mois:%Y-%m}", "/historique/", f"/mon-annee/?annee={annee}",
                f"/le-marche/?annee={annee}", "/mes-produits/"]

    def test_a1_ne_voit_rien_d_a2(self):
        self.connecter("user_a1")
        for url in self.pages_membre():
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertFalse(contient_signature(r.content.decode()), f"fuite sur {url}")
        self.assertEqual(self.client.get(f"/declarer/rapport/{self.depot_a2.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/declarer/confirmation/{self.decl_a2.id}/").status_code, 404)
        self.assertEqual(self.client.post(f"/declarer/soumettre/{self.decl_a2.id}/", {"attestation": "on"}).status_code, 404)
        self.decl_a2.refresh_from_db()
        self.assertEqual(self.decl_a2.statut, "SOUMISE")

    def test_export_annee_d_a1_ne_contient_pas_a2(self):
        self.connecter("user_a1")
        r = self.client.get("/mon-annee/export/", {"annee": self.mois.year})
        from openpyxl import load_workbook
        import io
        wb = load_workbook(io.BytesIO(r.content))
        valeurs = {str(c.value) for ws in wb.worksheets for row in ws.iter_rows() for c in row if c.value is not None}
        self.assertFalse(any(str(s) in valeurs for s in SIGNATURES))

    def test_gestion_ne_voit_aucune_quantite(self):
        self.connecter("gestionnaire")
        for url in ("/gestion/", "/gestion/propositions/", "/gestion/catalogue/", "/gestion/demandes-acces/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            self.assertFalse(contient_signature(r.content.decode()), f"fuite sur {url}")
        # les objets du membre ne lui sont pas accessibles
        self.assertEqual(self.client.get(f"/declarer/rapport/{self.depot_a2.id}/").status_code, 403)

    def test_bureau_ne_voit_ni_quantite_ni_motif_de_masquage(self):
        self.connecter("president")
        for url in (f"/bureau/?annee={self.mois.year}", "/bureau/approbations/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 200, url)
            html = r.content.decode()
            self.assertFalse(contient_signature(html), f"fuite sur {url}")
            self.assertNotIn("nb_contributeurs", html)
            self.assertNotIn("motif_suppression", html)

    def test_aucune_quantite_dans_les_urls_ni_les_messages(self):
        """Les identifiants d'URL sont des clés techniques ; les messages flash ne citent aucun nombre de véhicules."""
        self.connecter("user_a2")
        r = self.client.get(f"/declarer/confirmation/{self.decl_a2.id}/")
        for m in r.context["messages"] if "messages" in r.context else []:
            self.assertFalse(contient_signature(str(m)))
        self.assertNotIn(str(SIGNATURES[0]), r.request["PATH_INFO"])
