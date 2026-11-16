"""Page de présentation publique : accessible sans compte, ne lit aucune donnée, mène à la connexion."""
from django.test import TestCase

from portail.vues import vitrine as module_vitrine

from .outils import TestPortail


class VitrinePublique(TestCase):
    def test_accessible_sans_compte_et_sans_aucune_requete_sql(self):
        # Zéro requête : la page ne peut rien révéler de la base, ni données de membre ni nombre de contributeurs.
        with self.assertNumQueries(0):
            r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "portail/vitrine/accueil.html")
        self.assertContains(r, 'href="/connexion/"')
        self.assertContains(r, "Accéder au portail")

    def test_chiffres_et_segments_viennent_du_module(self):
        r = self.client.get("/")
        for c in module_vitrine.CHIFFRES:
            self.assertContains(r, c["valeur"])
        for s in module_vitrine.SEGMENTS:
            self.assertContains(r, s["nom"])
        self.assertContains(r, 'id="serie-mensuelle"')

    def test_mention_illustration_tant_que_les_chiffres_ne_sont_pas_officiels(self):
        self.assertContains(self.client.get("/"), "Valeurs d'illustration")
        ancien = module_vitrine.CHIFFRES_ILLUSTRATIFS
        module_vitrine.CHIFFRES_ILLUSTRATIFS = False
        try:
            self.assertNotContains(self.client.get("/"), "illustration")
        finally:
            module_vitrine.CHIFFRES_ILLUSTRATIFS = ancien

    def test_chaque_famille_a_une_photo_ou_a_defaut_un_dessin(self):
        r = self.client.get("/")
        photos = sum(1 for s in module_vitrine.SEGMENTS if module_vitrine._photo(s["cle"]))
        self.assertContains(r, 'class="vehicule__visuel', count=len(module_vitrine.SEGMENTS))
        self.assertContains(r, "/static/portail/vitrine/photos/", count=photos)
        self.assertContains(r, 'class="silhouette"', count=len(module_vitrine.SEGMENTS) - photos)


class VitrineEtComptes(TestPortail):
    def test_une_personne_connectee_va_directement_a_son_espace(self):
        self.connecter("user_a1")
        r = self.client.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertNotEqual(r["Location"], "/")

    def test_la_page_de_connexion_ramene_a_la_presentation(self):
        self.assertContains(self.client.get("/connexion/"), "Découvrir l'observatoire")
