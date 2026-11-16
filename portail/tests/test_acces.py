"""Connexion, rôles, blocage : qui entre, qui est refusé."""
from django.test import override_settings

from portail.models import TentativeConnexion

from .outils import MOT_DE_PASSE, TestPortail


class Connexion(TestPortail):
    def test_connexion_par_email_et_redirection_par_role(self):
        for nom, cible in (("user_a1", "/accueil/"), ("gestionnaire", "/gestion/"), ("president", "/bureau/")):
            r = self.client.post("/connexion/", {"username": f"{nom}@essai.gipame.ci", "password": MOT_DE_PASSE})
            self.assertRedirects(r, cible, fetch_redirect_response=False)
            self.client.logout()

    def test_email_insensible_a_la_casse_et_aux_espaces(self):
        r = self.client.post("/connexion/", {"username": "  USER_A1@Essai.GIPAME.ci ", "password": MOT_DE_PASSE})
        self.assertEqual(r.status_code, 302)

    def test_anonyme_redirige_vers_connexion(self):
        for url in ("/accueil/", "/declarer/", "/mon-annee/", "/gestion/", "/bureau/"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertTrue(r["Location"].startswith("/connexion/"))

    def test_mauvais_mot_de_passe_journalise_sans_reveler_le_compte(self):
        r = self.client.post("/connexion/", {"username": "user_a1@essai.gipame.ci", "password": "faux"})
        self.assertContains(r, "Adresse e-mail ou mot de passe incorrect")
        r2 = self.client.post("/connexion/", {"username": "inconnu@essai.gipame.ci", "password": "faux"})
        self.assertContains(r2, "Adresse e-mail ou mot de passe incorrect")  # même message, compte existant ou non
        self.assertEqual(TentativeConnexion.objects.filter(reussie=False).count(), 2)

    def test_blocage_apres_cinq_echecs(self):
        for _ in range(5):
            self.client.post("/connexion/", {"username": "user_a1@essai.gipame.ci", "password": "faux"})
        r = self.client.post("/connexion/", {"username": "user_a1@essai.gipame.ci", "password": MOT_DE_PASSE})
        self.assertContains(r, "Trop de tentatives")
        self.assertFalse(r.wsgi_request.user.is_authenticated)

    def test_journal_des_tentatives_ne_se_modifie_pas(self):
        from django.db import IntegrityError, transaction
        self.client.post("/connexion/", {"username": "user_a1@essai.gipame.ci", "password": "faux"})
        t = TentativeConnexion.objects.first()
        with self.assertRaises(Exception), transaction.atomic():
            t.reussie = True
            t.save()
        with self.assertRaises(Exception), transaction.atomic():
            t.delete()

    def test_compte_desactive(self):
        u = self.connecter("user_a1")
        self.client.logout()
        u.is_active = False
        u.save()
        r = self.client.post("/connexion/", {"username": u.username, "password": MOT_DE_PASSE})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.wsgi_request.user.is_authenticated)


class Roles(TestPortail):
    def test_membre_ne_voit_pas_gestion_ni_bureau(self):
        self.connecter("user_a1")
        for url in ("/gestion/", "/gestion/propositions/", "/gestion/catalogue/", "/bureau/", "/bureau/approbations/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_gestion_ne_voit_pas_les_ecrans_membre_ni_bureau(self):
        self.connecter("gestionnaire")
        for url in ("/accueil/", "/declarer/", "/declarer/gabarit/", "/mon-annee/", "/le-marche/", "/mes-produits/", "/bureau/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_bureau_ne_voit_pas_gestion_ni_membre(self):
        self.connecter("president")
        for url in ("/gestion/", "/accueil/", "/declarer/gabarit/"):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_technique_voit_la_gestion(self):
        self.connecter("technicien")
        self.assertEqual(self.client.get("/gestion/").status_code, 200)

    @override_settings(DEBUG=False)
    def test_galerie_invisible_hors_developpement(self):
        self.connecter("user_a1")
        self.assertEqual(self.client.get("/_galerie/").status_code, 404)

    def test_deconnexion_en_post_seulement(self):
        self.connecter("user_a1")
        self.assertEqual(self.client.get("/deconnexion/").status_code, 405)
        r = self.client.post("/deconnexion/")
        self.assertRedirects(r, "/connexion/", fetch_redirect_response=False)
