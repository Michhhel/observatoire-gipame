"""Écrans « Membres » de la gestion : créer un membre, clore / rouvrir une adhésion, ajouter / retirer une marque.
Les refus de la base (chevauchement, code en double) deviennent des messages ; rien n'est supprimé."""
from collecte.models import Concession, Marque, Membre, PeriodeAdhesion

from .outils import TestPortail


class EcransMembres(TestPortail):
    def test_creer_un_membre_avec_ses_marques(self):
        self.connecter("gestionnaire")
        marque = Marque.objects.order_by("id").first()
        r = self.client.post("/gestion/membres/nouveau/", {"code": "nv 1", "raison_sociale": "Nouvelle Auto (démo)",
                                                            "groupe": "Groupe Neuf", "debut": "2027-01", "marques": [marque.id]})
        m = Membre.objects.get(code="NV_1")
        self.assertRedirects(r, f"/gestion/membres/{m.id}/")
        self.assertEqual(m.groupe.nom, "Groupe Neuf")
        self.assertTrue(PeriodeAdhesion.objects.filter(membre=m, date_debut="2027-01-01", date_fin__isnull=True).exists())
        self.assertTrue(Concession.objects.filter(membre=m, marque=marque).exists())
        r = self.client.post("/gestion/membres/nouveau/", {"code": "NV_1", "raison_sociale": "Doublon", "debut": "2027-01"})
        self.assertContains(r, "existe déjà")

    def test_clore_rouvrir_adhesion_et_chevauchement_refuse(self):
        self.connecter("gestionnaire")
        m = self.d.membres["B2"]
        p = PeriodeAdhesion.objects.get(membre=m, date_fin__isnull=True)
        url = f"/gestion/membres/{m.id}/action/"
        self.client.post(url, {"action": "clore_adhesion", "periode": p.id, "mois": "2030-06"})
        p.refresh_from_db()
        self.assertEqual(str(p.date_fin), "2030-06-30")
        r = self.client.post(url, {"action": "ouvrir_adhesion", "mois": "2030-03"}, follow=True)
        self.assertContains(r, "chevauche")
        self.client.post(url, {"action": "ouvrir_adhesion", "mois": "2030-09"})
        self.assertEqual(PeriodeAdhesion.objects.filter(membre=m).count(), 2)

    def test_marques_et_page_sans_quantite(self):
        self.connecter("gestionnaire")
        m = self.d.membres["A1"]
        url = f"/gestion/membres/{m.id}/action/"
        self.client.post(url, {"action": "creer_marque", "code": "essai", "nom": "Essai", "origine": Marque.objects.first().origine_id})
        nouvelle = Marque.objects.get(code="ESSAI")
        self.client.post(url, {"action": "ajouter_concession", "marque": nouvelle.id, "mois": "2027-02"})
        c = Concession.objects.get(membre=m, marque=nouvelle)
        self.client.post(url, {"action": "clore_concession", "concession": c.id, "mois": "2027-12"})
        c.refresh_from_db()
        self.assertEqual(str(c.date_fin), "2027-12-31")
        for page in ("/gestion/membres/", f"/gestion/membres/{m.id}/"):
            r = self.client.get(page)
            self.assertEqual(r.status_code, 200)
            self.assertNotContains(r, "quantite")

    def test_reserve_a_la_gestion(self):
        for nom in ("user_a1", "president"):
            self.client.logout()
            self.connecter(nom)
            self.assertEqual(self.client.get("/gestion/membres/").status_code, 403)
            self.client.post("/gestion/membres/nouveau/", {"code": "PIRATE", "raison_sociale": "x", "debut": "2027-01"})
        self.assertFalse(Membre.objects.filter(code="PIRATE").exists())
