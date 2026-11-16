"""Outils communs aux tests du portail : jeu de démonstration, connexion par e-mail, dépôt d'un gabarit."""
from django.test import TestCase

from collecte.cycle import remplir_gabarit
from collecte.demo import charger_demo
from collecte.models import Utilisateur

MOT_DE_PASSE = "essai-portail-2026"


class TestPortail(TestCase):
    """Charge le jeu de démonstration et donne un e-mail + mot de passe à chaque compte."""

    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()
        for u in Utilisateur.objects.all():
            u.email = f"{u.username}@essai.gipame.ci"
            u.username = u.email
            u.set_password(MOT_DE_PASSE)
            u.save()

    def connecter(self, nom):
        """nom : « user_a1 », « gestionnaire », « president »…"""
        ok = self.client.login(username=f"{nom}@essai.gipame.ci", password=MOT_DE_PASSE)
        self.assertTrue(ok, f"connexion impossible pour {nom}")
        return Utilisateur.objects.get(username=f"{nom}@essai.gipame.ci")

    def deposer(self, mois, quantites=None, attestation="OUI", motif=None):
        """Télécharge le gabarit du mois via le portail, le remplit, le dépose. Renvoie la réponse de redirection."""
        r = self.client.get("/declarer/gabarit/", {"mois": mois.strftime("%Y-%m")})
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        rempli = remplir_gabarit(r.content, quantites=quantites or {}, attestation=attestation)
        from django.core.files.uploadedfile import SimpleUploadedFile
        fichier = SimpleUploadedFile("declaration.xlsx", rempli, content_type=r["Content-Type"])
        donnees = {"fichier": fichier, "mois": mois.strftime("%Y-%m")}
        if motif:
            donnees["motif"] = motif
        return self.client.post("/declarer/", donnees)
