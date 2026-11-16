"""Sécurité par ligne : chacun ne voit que ce qui le concerne ; l'échec est toujours « fermé »."""
from django.db import ProgrammingError
from django.test import TestCase

from collecte.demo import charger_demo, premier_du_mois
from collecte.models import Declaration, LigneVente

from .outils import doit_echouer, en_tant_que, requete


class SecuriteParLigne(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()

    def test_le_membre_ne_voit_que_ses_declarations(self):
        a1 = self.d.membres["A1"].id
        with en_tant_que("gipame_membre", membre_id=a1):
            vus = requete("SELECT DISTINCT membre_id FROM collecte_declaration")
        self.assertEqual(vus, [(a1,)])

    def test_le_membre_ne_voit_que_ses_lignes(self):
        a1 = self.d.membres["A1"]
        attendu = LigneVente.objects.filter(declaration__membre=a1).count()
        with en_tant_que("gipame_membre", membre_id=a1.id):
            vu = requete("SELECT count(*) FROM collecte_lignevente")[0][0]
        self.assertEqual(vu, attendu)
        self.assertLess(vu, LigneVente.objects.count())

    def test_un_membre_ne_peut_pas_ecrire_pour_un_autre(self):
        a1, b1 = self.d.membres["A1"], self.d.membres["B1"]
        with en_tant_que("gipame_membre", membre_id=a1.id):
            doit_echouer(self, lambda: Declaration.objects.create(membre=b1, mois=premier_du_mois(0), version=1))

    def test_un_membre_ne_modifie_pas_les_lignes_d_un_autre(self):
        a1, b1 = self.d.membres["A1"], self.d.membres["B1"]
        decl_b1 = Declaration.objects.filter(membre=b1).first()
        with en_tant_que("gipame_membre", membre_id=a1.id):
            touchees = requete("UPDATE collecte_lignevente SET quantite = 999 WHERE declaration_id = %s", [decl_b1.id])
        self.assertEqual(touchees, 0)
        self.assertFalse(LigneVente.objects.filter(quantite=999).exists())

    def test_le_membre_ne_peut_pas_falsifier_l_horodatage_de_soumission(self):
        a1 = self.d.membres["A1"]
        decl = Declaration.objects.create(membre=a1, mois=premier_du_mois(0), version=1)
        with en_tant_que("gipame_membre", membre_id=a1.id):
            doit_echouer(self, lambda: requete("UPDATE collecte_declaration SET soumise_le = now() WHERE id = %s", [decl.id]),
                         ProgrammingError)

    def test_la_gestion_voit_les_statuts_mais_jamais_les_quantites(self):
        with en_tant_que("gipame_gestion", utilisateur_id=self.d.users["gestionnaire"].id):
            n = requete("SELECT count(*) FROM collecte_declaration")[0][0]
            doit_echouer(self, lambda: requete("SELECT * FROM collecte_lignevente"), ProgrammingError)
        self.assertEqual(n, Declaration.objects.count())

    def test_le_bureau_n_a_aucun_acces_aux_donnees_brutes(self):
        with en_tant_que("gipame_bureau", utilisateur_id=self.d.users["president"].id):
            doit_echouer(self, lambda: requete("SELECT * FROM collecte_declaration"), ProgrammingError)
            doit_echouer(self, lambda: requete("SELECT * FROM collecte_lignevente"), ProgrammingError)

    def test_l_application_sans_bascule_de_role_n_a_aucun_droit(self):
        with en_tant_que("gipame_app"):
            doit_echouer(self, lambda: requete("SELECT count(*) FROM collecte_lignevente"), ProgrammingError)
            doit_echouer(self, lambda: requete("SELECT count(*) FROM collecte_membre"), ProgrammingError)

    def test_le_journal_d_audit_ne_montre_pas_les_quantites_a_la_gestion(self):
        a1 = self.d.membres["A1"]
        decl = Declaration.objects.create(membre=a1, mois=premier_du_mois(0), version=1)
        ligne = LigneVente.objects.create(declaration=decl, produit=self.d.produits["P01"], quantite=5)
        LigneVente.objects.filter(pk=ligne.pk).update(quantite=7)
        sql = "SELECT count(*) FROM collecte_journalmodification WHERE table_nom = 'collecte_lignevente'"
        self.assertGreaterEqual(requete(sql)[0][0], 1)  # le propriétaire voit tout
        with en_tant_que("gipame_gestion", utilisateur_id=self.d.users["gestionnaire"].id):
            self.assertEqual(requete(sql)[0][0], 0)
            self.assertGreater(requete("SELECT count(*) FROM collecte_journalmodification")[0][0], 0)
