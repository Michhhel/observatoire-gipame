"""Mode démonstration : bandeau, comptes d'essai sur la connexion, comptes protégés, commandes autorisées."""
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from collecte.models import Utilisateur

from .outils import TestPortail


class SansDemo(TestCase):
    @override_settings(MODE_DEMO=False)
    def test_ni_bandeau_ni_comptes_d_essai(self):
        for url in ("/", "/connexion/"):
            r = self.client.get(url)
            self.assertNotContains(r, "bandeau-demo")
            self.assertNotContains(r, "demo-2026")

    @override_settings(MODE_DEMO=False, DEBUG=False)
    def test_commandes_de_demo_refusees_sur_une_base_reelle(self):
        for commande in ("seed_demo", "comptes_demo"):
            with self.assertRaises(CommandError):
                call_command(commande)


@override_settings(MODE_DEMO=True)
class AvecDemo(TestPortail):
    def test_bandeau_sur_la_presentation_et_la_connexion(self):
        for url in ("/", "/connexion/"):
            self.assertContains(self.client.get(url), "bandeau-demo")

    def test_comptes_d_essai_sur_la_connexion(self):
        r = self.client.get("/connexion/")
        self.assertContains(r, 'data-remplir-email="user_a1@demo.gipame.ci"')
        self.assertContains(r, 'data-remplir-mdp="demo-2026"')

    def test_un_compte_de_demonstration_ne_peut_pas_etre_desactive(self):
        cible = self.d.users["B1"]
        Utilisateur.objects.filter(pk=cible.pk).update(email="user_b1@demo.gipame.ci")
        self.connecter("technicien")
        r = self.client.post(f"/administration/comptes/{cible.pk}/action/", {"action": "desactiver", "motif": "essai"}, follow=True)
        self.assertContains(r, "ne peuvent être ni désactivés")
        cible.refresh_from_db()
        self.assertTrue(cible.is_active)

    def test_un_compte_ordinaire_reste_gerable_en_demonstration(self):
        cible = self.d.users["B1"]
        self.connecter("technicien")
        self.client.post(f"/administration/comptes/{cible.pk}/action/", {"action": "desactiver", "motif": "essai"})
        cible.refresh_from_db()
        self.assertFalse(cible.is_active)
