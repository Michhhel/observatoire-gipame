"""Gestion : validation / fusion / rejet des produits proposés, demandes d'accès. Bureau : approbations."""
from collecte.models import ApprobationAcces, ClassementProduit, DemandeAccesExceptionnel, Produit, Segment
from portail.formats import premier_du_mois

from .outils import TestPortail


class Propositions(TestPortail):
    def proposer(self, modele="Nouveau", finition="Base"):
        self.connecter("user_a1")
        p01 = Produit.objects.get(code="P01")
        r = self.client.post("/mes-produits/", {"marque": p01.modele.marque_id, "modele": modele, "finition": finition,
                                                "energie": p01.energie_id})
        self.assertEqual(r.status_code, 302)
        self.client.logout()
        return Produit.objects.get(statut="PROPOSE", propose_par=self.d.membres["A1"])

    def test_valider(self):
        produit = self.proposer()
        self.connecter("gestionnaire")
        r = self.client.get("/gestion/propositions/")
        self.assertContains(r, "Nouveau BASE")
        segment = Segment.objects.filter(categorie__segmentation__statut="COURANTE").first()
        r = self.client.post(f"/gestion/propositions/{produit.id}/", {"decision": "VALIDER", "segment": segment.id,
                                                                     "nom_modele": "Nouveau", "finition": "Base"})
        self.assertRedirects(r, "/gestion/propositions/", fetch_redirect_response=False)
        produit.refresh_from_db()
        self.assertEqual(produit.statut, "ACTIF")
        self.assertTrue(produit.code)
        self.assertEqual(produit.modele.nom, "Nouveau")
        self.assertTrue(ClassementProduit.objects.filter(produit=produit, segment=segment).exists())
        # le membre le voit dans son gabarit
        self.client.logout()
        self.connecter("user_a1")
        self.assertContains(self.client.get("/mes-produits/"), produit.code)

    def test_le_membre_ne_peut_pas_proposer_un_doublon_exact(self):
        p01 = Produit.objects.get(code="P01")
        self.connecter("user_a1")
        r = self.client.post("/mes-produits/", {"marque": p01.modele.marque_id, "modele": p01.modele.nom, "finition": p01.finition.lower(),
                                                "energie": p01.energie_id, "boite": p01.boite_id})
        self.assertContains(r, "existe déjà au catalogue")
        self.assertFalse(Produit.objects.filter(statut="PROPOSE").exists())

    def test_fusionner(self):
        p01 = Produit.objects.get(code="P01")
        produit = self.proposer(modele="Citadine", finition="Life ed. spéciale")
        self.connecter("gestionnaire")
        r = self.client.post(f"/gestion/propositions/{produit.id}/", {"decision": "FUSIONNER"})
        self.assertContains(r, "Indiquez le produit existant")
        r = self.client.post(f"/gestion/propositions/{produit.id}/", {"decision": "FUSIONNER", "cible": p01.id})
        self.assertEqual(r.status_code, 302)
        produit.refresh_from_db()
        self.assertEqual((produit.statut, produit.fusionne_dans_id), ("FUSIONNE", p01.id))

    def test_rejeter_exige_un_motif(self):
        produit = self.proposer()
        self.connecter("gestionnaire")
        r = self.client.post(f"/gestion/propositions/{produit.id}/", {"decision": "REJETER"})
        self.assertContains(r, "motif est obligatoire")
        r = self.client.post(f"/gestion/propositions/{produit.id}/", {"decision": "REJETER", "motif": "Hors périmètre v1"})
        self.assertEqual(r.status_code, 302)
        produit.refresh_from_db()
        self.assertEqual((produit.statut, produit.motif_decision), ("REJETE", "Hors périmètre v1"))

    def test_membre_ne_peut_pas_decider(self):
        produit = self.proposer()
        self.connecter("user_a1")
        self.assertEqual(self.client.post(f"/gestion/propositions/{produit.id}/", {"decision": "REJETER", "motif": "x"}).status_code, 403)


class AccesExceptionnel(TestPortail):
    def test_demande_puis_approbations(self):
        mois = premier_du_mois(decalage=-2)
        self.connecter("gestionnaire")
        r = self.client.post("/gestion/demandes-acces/", {"membre_cible": self.d.membres["A1"].id, "mois_debut": f"{mois:%Y-%m}",
                                                          "mois_fin": f"{mois:%Y-%m}", "duree_minutes": 60,
                                                          "motif": "Écart à expliquer avant publication"})
        self.assertRedirects(r, "/gestion/demandes-acces/", fetch_redirect_response=False)
        demande = DemandeAccesExceptionnel.objects.get()
        self.assertEqual(demande.mois_debut, mois)
        self.client.logout()
        # président : approuve
        self.connecter("president")
        r = self.client.get("/bureau/approbations/")
        self.assertContains(r, "Écart à expliquer")
        r = self.client.post(f"/bureau/approbations/{demande.id}/", {"decision": "APPROUVEE", "commentaire": "ok"})
        self.assertRedirects(r, "/bureau/approbations/", fetch_redirect_response=False)
        self.assertEqual(ApprobationAcces.objects.filter(demande=demande, decision="APPROUVEE").count(), 1)
        # un second vote du même poste est ignoré
        self.client.post(f"/bureau/approbations/{demande.id}/", {"decision": "REFUSEE"})
        self.assertEqual(ApprobationAcces.objects.filter(demande=demande).count(), 1)
        self.client.logout()
        # vice-président : approuve → fenêtre ouverte (2 sur 3)
        self.connecter("vice_president")
        self.client.post(f"/bureau/approbations/{demande.id}/", {"decision": "APPROUVEE"})
        self.assertEqual(ApprobationAcces.objects.filter(demande=demande, decision="APPROUVEE").count(), 2)
        self.assertContains(self.client.get("/bureau/approbations/"), "2 accords")

    def test_bureau_sans_poste_ne_peut_pas_approuver(self):
        self.connecter("gestionnaire")
        self.client.post("/gestion/demandes-acces/", {"mois_debut": "2026-01", "mois_fin": "2026-01", "duree_minutes": 30, "motif": "m"})
        demande = DemandeAccesExceptionnel.objects.get()
        self.client.logout()
        # le délégué général a un poste ; on retire sa titularité pour le test
        from collecte.models import TitulairePoste
        TitulairePoste.objects.filter(utilisateur__username="delegue_general@essai.gipame.ci").update(date_fin=premier_du_mois(decalage=-3))
        self.connecter("delegue_general")
        r = self.client.post(f"/bureau/approbations/{demande.id}/", {"decision": "APPROUVEE"})
        self.assertEqual(ApprobationAcces.objects.count(), 0)


class LectureApresAccord(TestPortail):
    """Écran de lecture des données individuelles : seulement après accord, seulement le demandeur, journalisé."""

    def setUp(self):
        mois = self.d.mois_plein
        self.connecter("technicien")
        self.client.post("/gestion/demandes-acces/", {"membre_cible": self.d.membres["B1"].id, "mois_debut": f"{mois:%Y-%m}",
                                                      "mois_fin": f"{mois:%Y-%m}", "duree_minutes": 60, "motif": "Écart à expliquer"})
        self.demande = DemandeAccesExceptionnel.objects.get()
        self.url = f"/gestion/demandes-acces/{self.demande.id}/lecture/"

    def approuver(self, *noms):
        self.client.logout()
        for nom in noms:
            self.connecter(nom)
            self.client.post(f"/bureau/approbations/{self.demande.id}/", {"decision": "APPROUVEE"})
            self.client.logout()
        self.connecter("technicien")

    def test_affichage_ne_lit_rien(self):
        from collecte.models import JournalAcces
        self.approuver("president", "vice_president")
        r = self.client.get(self.url)
        self.assertContains(r, "Lire maintenant")
        self.assertNotContains(r, "P18")
        self.assertFalse(JournalAcces.objects.filter(action="LECTURE_EXCEPTIONNELLE").exists())
        self.assertIn("no-cache", r["Cache-Control"])

    def test_refus_tant_que_l_accord_est_insuffisant(self):
        self.approuver("president")
        r = self.client.post(self.url)
        self.assertContains(r, "Accord insuffisant")
        self.assertNotContains(r, "<th class=\"num\">Quantité</th>")

    def test_lecture_apres_accord_et_journal(self):
        from collecte.models import JournalAcces
        self.approuver("president", "vice_president")
        r = self.client.post(self.url)
        self.assertContains(r, "6 lignes")
        self.assertContains(r, "P18")
        self.assertEqual(JournalAcces.objects.get(action="LECTURE_EXCEPTIONNELLE").nb_lignes, 6)

    def test_un_autre_agent_ne_peut_pas_lire(self):
        self.approuver("president", "vice_president")
        self.client.logout()
        self.connecter("gestionnaire")
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.client.logout()
        self.connecter("user_b1")
        self.assertEqual(self.client.post(self.url).status_code, 403)
