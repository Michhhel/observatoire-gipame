"""Commande gerer_compte : création par l'administrateur, activation par lien, désactivation, traçabilité."""
import re
from io import StringIO

from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from collecte.demo import charger_demo
from collecte.models import JournalAcces, TitulairePoste, Utilisateur


def gerer(*args):
    sortie = StringIO()
    call_command("gerer_compte", *args, stdout=sortie)
    return sortie.getvalue()


class GererCompte(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()

    def test_creation_activation_connexion(self):
        sortie = gerer("creer", "--email", " Awa.Kone@Societe.CI ", "--prenom", "Awa", "--nom", "Koné", "--role", "MEMBRE", "--membre", "A1")
        u = Utilisateur.objects.get(username="awa.kone@societe.ci")
        self.assertEqual((u.membre.code, u.role_metier, u.has_usable_password()), ("A1", "MEMBRE", False))
        lien = re.search(r"https?://\S+/activation/\S+/", sortie).group(0)
        chemin = lien.split("://", 1)[1].split("/", 1)[1]
        r = self.client.get("/" + chemin, follow=True)
        self.assertContains(r, "Activer mon compte")
        r = self.client.post(r.redirect_chain[-1][0], {"new_password1": "Abidjan-2027!", "new_password2": "Abidjan-2027!"})
        self.assertRedirects(r, "/mot-de-passe-change/", fetch_redirect_response=False)
        self.assertTrue(self.client.login(username="awa.kone@societe.ci", password="Abidjan-2027!"))
        self.assertEqual(self.client.get("/accueil/").status_code, 200)
        # le lien ne sert qu'une fois
        self.client.logout()
        self.assertContains(self.client.get("/" + chemin, follow=True), "Lien expiré")
        self.assertTrue(JournalAcces.objects.filter(action="COMPTE_CREE", details__email="awa.kone@societe.ci").exists())
        # le lien ne peut plus être régénéré une fois le mot de passe choisi
        with self.assertRaises(CommandError):
            gerer("renvoyer", "--email", "awa.kone@societe.ci")

    def test_envoi_par_email_sans_quantite(self):
        gerer("creer", "--email", "b@societe.ci", "--role", "MEMBRE", "--membre", "B1", "--envoyer")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/activation/", mail.outbox[0].body)
        self.assertNotRegex(mail.outbox[0].body, r"\b\d{2,}\s*(véhicules|unités)")

    def test_refus(self):
        with self.assertRaises(CommandError):
            gerer("creer", "--email", "x@societe.ci", "--role", "MEMBRE")  # membre manquant
        with self.assertRaises(CommandError):
            gerer("creer", "--email", "pas-une-adresse", "--role", "GESTION")
        gerer("creer", "--email", "y@societe.ci", "--role", "GESTION")
        with self.assertRaises(CommandError):
            gerer("creer", "--email", "Y@societe.ci", "--role", "GESTION")  # doublon (casse ignorée)
        with self.assertRaises(CommandError):
            gerer("creer", "--email", "z@gipame.ci", "--role", "BUREAU", "--poste", "PRESIDENT")  # poste déjà tenu

    def test_desactivation_bloque_la_connexion_et_clot_le_poste(self):
        president = self.d.users["president"]
        president.username = president.email = "president@gipame.ci"
        president.set_password("x-12345678")
        president.save()
        with self.assertRaises(CommandError):
            gerer("desactiver", "--email", "president@gipame.ci")  # motif obligatoire
        gerer("desactiver", "--email", "president@gipame.ci", "--motif", "fin de mandat")
        self.assertFalse(self.client.login(username="president@gipame.ci", password="x-12345678"))
        self.assertFalse(TitulairePoste.objects.filter(utilisateur=president, date_fin__isnull=True).exists())
        self.assertTrue(Utilisateur.objects.filter(pk=president.pk).exists())  # jamais supprimé
        self.assertEqual(JournalAcces.objects.get(action="COMPTE_DESACTIVE").details["motif"], "fin de mandat")
        # un poste désormais libre ; le nouveau mandat commence après la fin du précédent
        gerer("creer", "--email", "nouveau.president@gipame.ci", "--role", "BUREAU", "--poste", "PRESIDENT")
        nouveau = TitulairePoste.objects.get(utilisateur__username="nouveau.president@gipame.ci", date_fin__isnull=True)
        self.assertGreater(nouveau.date_debut, TitulairePoste.objects.get(utilisateur=president).date_fin)


class EcranComptes(TestCase):
    """L'écran « Comptes » : réservé au rôle TECHNIQUE, mêmes garanties que la commande, via gipame_app → fonctions SQL."""

    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()
        for nom in ("technicien", "gestionnaire", "A1"):
            u = cls.d.users[nom]
            u.username = u.email = f"{nom.lower()}@essai.gipame.ci"
            u.set_password("essai-portail-2026")
            u.save()

    def connecter(self, nom):
        self.assertTrue(self.client.login(username=f"{nom}@essai.gipame.ci", password="essai-portail-2026"))

    def test_reserve_a_l_administrateur(self):
        for nom in ("gestionnaire", "a1"):
            self.connecter(nom)
            self.assertEqual(self.client.get("/administration/comptes/").status_code, 403)
            r = self.client.post("/administration/comptes/", {"email": "x@y.ci", "role": "GESTION"})
            self.assertEqual(r.status_code, 403)
            self.client.logout()
        self.assertFalse(Utilisateur.objects.filter(username="x@y.ci").exists())

    def test_creation_lien_affiche_puis_activation(self):
        self.connecter("technicien")
        r = self.client.get("/administration/comptes/")
        self.assertContains(r, "Nouveau compte")
        membre = self.d.membres["A2"]
        r = self.client.post("/administration/comptes/", {"email": "Nouveau@A2.ci", "prenom": "Nana", "nom": "Diallo", "role": "MEMBRE",
                                                          "membre": membre.id})  # sans « envoyer » → lien affiché
        u = Utilisateur.objects.get(username="nouveau@a2.ci")
        self.assertRedirects(r, f"/administration/comptes/{u.id}/", fetch_redirect_response=False)
        r = self.client.get(f"/administration/comptes/{u.id}/")
        self.assertContains(r, "Lien d'activation pour nouveau@a2.ci")
        lien = re.search(r"https?://[^\s<]+/activation/[^\s<]+/", r.content.decode()).group(0)
        self.assertNotContains(self.client.get(f"/administration/comptes/{u.id}/"), "Lien d'activation pour")  # affiché une seule fois
        self.client.logout()
        chemin = "/" + lien.split("://", 1)[1].split("/", 1)[1]
        r = self.client.get(chemin, follow=True)
        self.assertContains(r, "Activer mon compte")
        r = self.client.post(r.redirect_chain[-1][0], {"new_password1": "Abidjan-2027!", "new_password2": "Abidjan-2027!"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.client.login(username="nouveau@a2.ci", password="Abidjan-2027!"))
        self.assertContains(self.client.get("/accueil/"), membre.code)
        self.assertTrue(JournalAcces.objects.filter(action="COMPTE_CREE", details__email="nouveau@a2.ci").exists())

    def test_creation_avec_envoi_email(self):
        self.connecter("technicien")
        self.client.post("/administration/comptes/", {"email": "g@gipame.ci", "role": "GESTION", "envoyer": "on"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("/activation/", mail.outbox[0].body)

    def test_refus_coherents(self):
        self.connecter("technicien")
        r = self.client.post("/administration/comptes/", {"email": "m@a1.ci", "role": "MEMBRE"})
        self.assertContains(r, "Choisissez la société")
        r = self.client.post("/administration/comptes/", {"email": "technicien@essai.gipame.ci", "role": "GESTION"})
        self.assertContains(r, "existe déjà")

    def test_desactiver_reactiver_modifier(self):
        self.connecter("technicien")
        cible = self.d.users["A1"]
        url = f"/administration/comptes/{cible.id}/action/"
        r = self.client.post(url, {"action": "desactiver"})  # sans motif
        self.assertContains(self.client.get(f"/administration/comptes/{cible.id}/"), "motif est obligatoire")
        self.client.post(url, {"action": "desactiver", "motif": "a quitté la société"})
        cible.refresh_from_db()
        self.assertFalse(cible.is_active)
        self.client.post(url, {"action": "reactiver"})
        cible.refresh_from_db()
        self.assertTrue(cible.is_active)
        self.client.post(f"/administration/comptes/{cible.id}/", {"email": "a1.nouveau@essai.gipame.ci", "prenom": "Ali", "nom": "Koffi"})
        cible.refresh_from_db()
        self.assertEqual((cible.username, cible.first_name), ("a1.nouveau@essai.gipame.ci", "Ali"))
        # lien impossible : le compte a déjà un mot de passe
        self.client.post(url, {"action": "lien"})
        self.assertContains(self.client.get(f"/administration/comptes/{cible.id}/"), "déjà activé")
        # l'administrateur ne se désactive pas lui-même
        moi = self.d.users["technicien"]
        self.client.post(f"/administration/comptes/{moi.id}/action/", {"action": "desactiver", "motif": "x"})
        moi.refresh_from_db()
        self.assertTrue(moi.is_active)
