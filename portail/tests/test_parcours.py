"""Parcours déclarant de bout en bout, via le client HTTP (le middleware de bascule de rôle est exercé)."""
from collecte.models import Declaration, DepotFichier, Produit, ProduitMembre
from portail.formats import premier_du_mois

from .outils import TestPortail


class ParcoursDeclarant(TestPortail):
    def setUp(self):
        self.connecter("user_b3")  # B3 n'a pas encore déclaré le mois écoulé
        self.mois = premier_du_mois(decalage=-1)
        self.membre = self.d.membres["B3"]

    def test_accueil_propose_de_declarer_le_mois_ecoule(self):
        r = self.client.get("/accueil/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Déclarer")
        self.assertContains(r, "Vos ventes ne sont visibles que de votre société")

    def test_depot_rapport_attestation_confirmation(self):
        # 1 + 3 : gabarit téléchargé puis déposé, quantités en hausse pour provoquer une alerte
        r = self.deposer(self.mois, quantites={"P06": 150})
        self.assertEqual(r.status_code, 302)
        depot = DepotFichier.objects.get(membre=self.membre, mois=self.mois)
        self.assertRedirects(r, f"/declarer/rapport/{depot.id}/", fetch_redirect_response=False)
        r = self.client.get(f"/declarer/rapport/{depot.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Fichier accepté")
        self.assertNotContains(r, "VARIATION")  # jamais de code technique
        decl = depot.declaration
        self.assertEqual(decl.statut, "BROUILLON")
        # soumission sans attestation : refusée, le brouillon reste
        r = self.client.post(f"/declarer/soumettre/{decl.id}/", {"commentaire": "hausse liée à une flotte"})
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, "attestation est nécessaire", status_code=400)
        decl.refresh_from_db()
        self.assertEqual(decl.statut, "BROUILLON")
        # avec attestation : soumise, commentaire conservé, confirmation
        r = self.client.post(f"/declarer/soumettre/{decl.id}/", {"attestation": "on", "commentaire": "hausse liée à une flotte"})
        self.assertRedirects(r, f"/declarer/confirmation/{decl.id}/", fetch_redirect_response=False)
        decl.refresh_from_db()
        self.assertEqual(decl.statut, "SOUMISE")
        self.assertTrue(decl.attestation_complete)
        self.assertEqual(decl.commentaire_portail, "hausse liée à une flotte")
        r = self.client.get(f"/declarer/confirmation/{decl.id}/")
        self.assertContains(r, "reçue")
        # le rapport d'un dépôt soumis renvoie vers la confirmation ; l'accueil dit « reçue »
        self.assertRedirects(self.client.get(f"/declarer/rapport/{depot.id}/"), f"/declarer/confirmation/{decl.id}/", fetch_redirect_response=False)
        self.assertContains(self.client.get("/accueil/"), "Reçue, merci")

    def test_fichier_errone_refuse_avec_conseils(self):
        r = self.deposer(self.mois, quantites={"P06": -3})
        depot = DepotFichier.objects.get(membre=self.membre, mois=self.mois)
        self.assertEqual(depot.resultat, "REJETE")
        r = self.client.get(f"/declarer/rapport/{depot.id}/")
        self.assertContains(r, "n'a pas pu être accepté")
        self.assertContains(r, "Comment corriger")
        self.assertContains(r, "Quantité invalide")
        self.assertFalse(Declaration.objects.filter(membre=self.membre, mois=self.mois).exists())

    def test_correction_avec_motif_saisi_sur_la_page(self):
        self.deposer(self.mois, quantites={"P06": 10})
        decl = Declaration.objects.get(membre=self.membre, mois=self.mois)
        self.client.post(f"/declarer/soumettre/{decl.id}/", {"attestation": "on"})
        # correction : sans motif → formulaire refusé avant tout dépôt
        r = self.deposer(self.mois, quantites={"P06": 12})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "motif de la correction")
        self.assertEqual(DepotFichier.objects.filter(membre=self.membre, mois=self.mois).count(), 1)
        # avec motif : v2 acceptée, v1 remplacée après soumission
        r = self.deposer(self.mois, quantites={"P06": 12}, motif="Une livraison oubliée")
        self.assertEqual(r.status_code, 302)
        v2 = Declaration.objects.get(membre=self.membre, mois=self.mois, version=2)
        self.assertEqual(v2.motif_correction, "Une livraison oubliée")
        self.client.post(f"/declarer/soumettre/{v2.id}/", {"attestation": "on"})
        decl.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual((decl.statut, v2.statut), ("REMPLACEE", "SOUMISE"))
        r = self.client.get("/historique/")
        self.assertContains(r, "Remplacée")
        self.assertContains(r, "Une livraison oubliée")

    def test_mois_hors_fenetre_refuse(self):
        self.assertEqual(self.client.get("/declarer/", {"mois": premier_du_mois().strftime("%Y-%m")}).status_code, 404)
        self.assertEqual(self.client.get("/declarer/gabarit/", {"mois": "2015-01"}).status_code, 404)
        self.assertEqual(self.client.get("/declarer/", {"mois": "n'importe"}).status_code, 404)

    def test_mon_annee_marche_export(self):
        from collecte.services import calculer_publication
        calculer_publication(self.d.mois_plein)
        annee = self.d.mois_plein.year
        r = self.client.get("/mon-annee/", {"annee": annee})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Mon année")
        r = self.client.get("/mon-annee/export/", {"annee": annee})
        self.assertIn("spreadsheetml", r["Content-Type"])
        r = self.client.get("/le-marche/", {"annee": annee})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Pourquoi des « c »")

    def test_mes_produits_masquer_et_proposer(self):
        r = self.client.get("/mes-produits/")
        self.assertEqual(r.status_code, 200)
        produit = Produit.objects.get(code="P06")
        r = self.client.post(f"/mes-produits/{produit.id}/affichage/", {"action": "masquer"})
        self.assertRedirects(r, "/mes-produits/", fetch_redirect_response=False)
        self.assertEqual(ProduitMembre.objects.get(membre=self.membre, produit=produit).etat, "MASQUE")
        self.client.post(f"/mes-produits/{produit.id}/affichage/", {"action": "afficher"})
        self.assertEqual(ProduitMembre.objects.get(membre=self.membre, produit=produit).etat, "AFFICHE_FORCE")
        # produit d'une marque qui n'est pas la sienne : refusé
        autre = Produit.objects.get(code="P01")
        self.assertEqual(self.client.post(f"/mes-produits/{autre.id}/affichage/", {"action": "masquer"}).status_code, 404)
        # proposition
        marque = produit.modele.marque
        energie = produit.energie
        r = self.client.post("/mes-produits/", {"marque": marque.id, "modele": "Nouveau", "finition": "Base", "energie": energie.id})
        self.assertRedirects(r, "/mes-produits/", fetch_redirect_response=False)
        p = Produit.objects.get(statut="PROPOSE", propose_par=self.membre)
        self.assertEqual(p.finition, "BASE")
        # doublon exact d'un produit existant : refusé avec message
        r = self.client.post("/mes-produits/", {"marque": marque.id, "modele": produit.modele.nom, "finition": produit.finition,
                                                "energie": produit.energie_id, "boite": produit.boite_id or "",
                                                "cylindree": produit.cylindree_cm3 or "", "puissance": produit.puissance_fiscale_cv or "",
                                                "motricite": produit.motricite})
        self.assertContains(r, "existe déjà au catalogue")


class FichiersTelechargesIntacts(TestPortail):
    """Un fichier téléchargé doit être exactement l'archive produite : rien après la fin du zip, sinon Excel le refuse."""

    def _verifier(self, contenu):
        import io
        import zipfile
        fin = contenu.rfind(b"PK\x05\x06")
        self.assertGreater(fin, 0)
        self.assertEqual(len(contenu), fin + 22, "octets en trop après la fin de l'archive")
        self.assertIsNone(zipfile.ZipFile(io.BytesIO(contenu)).testzip())

    def test_gabarit_telecharge(self):
        self.connecter("user_a1")
        mois = self.d.mois_partiel
        r = self.client.get("/declarer/gabarit/", {"mois": mois.strftime("%Y-%m")})
        self.assertEqual(r.status_code, 200)
        self._verifier(r.content)
        self.assertIn(f"declaration_A1_{mois:%Y-%m}_v", r["Content-Disposition"])

    def test_export_mon_annee(self):
        self.connecter("user_a1")
        r = self.client.get("/mon-annee/export/")
        self.assertEqual(r.status_code, 200)
        self._verifier(r.content)
