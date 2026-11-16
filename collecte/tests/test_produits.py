"""Catalogue : propositions des membres, validation, masquage sans suppression, grilles de segments."""
from django.db import IntegrityError, ProgrammingError, transaction
from django.test import TestCase

from collecte.demo import charger_demo
from collecte.models import (AliasProduit, Categorie, ClassementProduit, LigneVente, Modele,
                             ParametreSysteme, Produit, ProduitMembre, Segment, Segmentation)

from .outils import doit_echouer, en_tant_que, requete


class ProduitsEtGabarit(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()

    def _ctx(self, code):
        return dict(membre_id=self.d.membres[code].id, utilisateur_id=self.d.users[code].id)

    def _proposer(self, code="A1", **champs):
        base = dict(code="", modele=Modele.objects.get(code="ALPHA-M-CITADINE"), finition="NOUVELLE",
                    libelle_affiche="ALPHA-M Citadine NOUVELLE", statut="PROPOSE",
                    propose_par=self.d.membres[code], note_proposition="lancement prévu")
        base.update(champs)
        return Produit.objects.create(**base)

    def _gabarit(self, code, mois=None):
        with en_tant_que("gipame_membre", **self._ctx(code)):
            return {r[0] for r in requete("SELECT l_code FROM gipame_lignes_gabarit(%s)", [mois or self.d.mois_plein])}

    # --- ajout d'un nouveau modèle par un membre
    def test_un_membre_propose_un_nouveau_modele_de_sa_marque(self):
        with en_tant_que("gipame_membre", **self._ctx("A1")):
            p = self._proposer("A1")
        p.refresh_from_db()
        self.assertTrue(p.code.startswith("PRD-"))
        self.assertEqual(p.statut, "PROPOSE")

    def test_une_proposition_n_est_visible_que_de_son_auteur_et_de_la_gestion(self):
        with en_tant_que("gipame_membre", **self._ctx("A1")):
            p = self._proposer("A1")

        def visibles(role, **ctx):
            with en_tant_que(role, **ctx):
                return requete("SELECT count(*) FROM collecte_produit WHERE id = %s", [p.id])[0][0]

        self.assertEqual(visibles("gipame_membre", **self._ctx("A1")), 1)
        self.assertEqual(visibles("gipame_membre", **self._ctx("B1")), 0)  # un concurrent ne voit pas le lancement
        self.assertEqual(visibles("gipame_gestion", utilisateur_id=self.d.users["gestionnaire"].id), 1)
        with en_tant_que("gipame_bureau", utilisateur_id=self.d.users["president"].id):  # le bureau n'a pas accès au catalogue
            doit_echouer(self, lambda: requete("SELECT count(*) FROM collecte_produit"), ProgrammingError)

    def test_la_proposition_apparait_dans_le_gabarit_de_son_auteur_seulement(self):
        with en_tant_que("gipame_membre", **self._ctx("A1")):
            p = self._proposer("A1")
        self.assertIn(Produit.objects.get(pk=p.pk).code, self._gabarit("A1"))
        self.assertNotIn(Produit.objects.get(pk=p.pk).code, self._gabarit("B1"))

    def test_un_membre_ne_peut_pas_s_auto_valider(self):
        with en_tant_que("gipame_membre", **self._ctx("A1")):
            doit_echouer(self, lambda: self._proposer("A1", statut="ACTIF"))

    def test_un_membre_ne_propose_rien_pour_une_marque_qu_il_ne_detient_pas(self):
        with en_tant_que("gipame_membre", **self._ctx("A1")):
            doit_echouer(self, lambda: self._proposer("A1", modele=Modele.objects.get(code="BETA-BERLINE")))

    def test_la_gestion_valide_la_decision_est_horodatee_et_tous_la_voient(self):
        with en_tant_que("gipame_membre", **self._ctx("A1")):
            p = self._proposer("A1")
        g = self.d.users["gestionnaire"]
        with en_tant_que("gipame_gestion", utilisateur_id=g.id):
            Produit.objects.filter(pk=p.pk).update(statut="ACTIF", motif_decision="Nouvelle version confirmée")
        p.refresh_from_db()
        self.assertEqual((p.statut, p.decide_par_id), ("ACTIF", g.id))
        self.assertIsNotNone(p.decide_le)
        with en_tant_que("gipame_membre", **self._ctx("B1")):
            self.assertEqual(requete("SELECT count(*) FROM collecte_produit WHERE id = %s", [p.id])[0][0], 1)

    def test_un_doublon_est_refuse_par_la_signature_du_produit(self):
        existant = self.d.produits["P01"]
        with self.assertRaises(IntegrityError), transaction.atomic():
            Produit.objects.create(code="P01-BIS", modele=existant.modele, finition=existant.finition,
                                   energie=existant.energie, boite=existant.boite,
                                   libelle_affiche="doublon", statut="ACTIF")

    def test_la_finition_est_stockee_en_majuscules_sans_espaces_parasites(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Produit.objects.create(code="X1", modele=self.d.produits["P01"].modele, finition="  luxe ",
                                   libelle_affiche="x", statut="ACTIF")

    # --- gabarit, masquage, paramètres
    def test_le_gabarit_contient_les_produits_des_marques_du_membre(self):
        self.assertEqual(self._gabarit("A1"), {"P01", "P14"})
        self.assertEqual(self._gabarit("B1"), {"P04", "P07", "P17", "P10", "P11", "P18"})

    def test_masquer_un_produit_le_retire_du_gabarit_sans_rien_supprimer(self):
        ProduitMembre.objects.create(membre=self.d.membres["A1"], produit=self.d.produits["P14"],
                                     etat="MASQUE", motif="plus vendu")
        self.assertEqual(self._gabarit("A1"), {"P01"})
        self.assertTrue(Produit.objects.filter(code="P14").exists())
        self.assertTrue(LigneVente.objects.filter(produit__code="P14").exists())  # historique intact
        with self.assertRaises(IntegrityError), transaction.atomic():
            requete("DELETE FROM collecte_produit WHERE code = 'P14'")

    def test_l_interrupteur_toutes_lignes_est_un_parametre_operationnel(self):
        with en_tant_que("gipame_gestion", utilisateur_id=self.d.users["gestionnaire"].id):
            n = requete("UPDATE collecte_parametresysteme SET valeur = 'oui' WHERE cle = 'gabarit_toutes_lignes'")
        self.assertEqual(n, 1)
        self.assertEqual(len(self._gabarit("A1")), 19)

    def test_la_gestion_ne_modifie_jamais_les_parametres_de_securite(self):
        with en_tant_que("gipame_gestion", utilisateur_id=self.d.users["gestionnaire"].id):
            n = requete("UPDATE collecte_parametresysteme SET valeur = '1' WHERE cle = 'seuil_approbations_acces'")
        self.assertEqual(n, 0)
        self.assertEqual(ParametreSysteme.objects.get(cle="seuil_approbations_acces").valeur, "2")

    def test_les_produits_sans_vente_sont_signales_jamais_supprimes(self):
        Produit.objects.create(code="P98", modele=self.d.produits["P01"].modele, finition="ORPHELINE",
                               libelle_affiche="sans vente", statut="ACTIF")
        with en_tant_que("gipame_gestion", utilisateur_id=self.d.users["gestionnaire"].id):
            codes = {r[0] for r in requete("SELECT code FROM collecte_v_produits_sans_vente")}
        self.assertEqual(codes, {"P98"})

    # --- alias (rapprochement des libellés libres)
    def test_les_alias_sont_normalises_et_uniques_par_membre(self):
        a1, p01 = self.d.membres["A1"], self.d.produits["P01"]
        alias = AliasProduit.objects.create(membre=a1, libelle_brut="  citadine   life  ", produit=p01)
        alias.refresh_from_db()
        self.assertEqual(alias.libelle_normalise, "CITADINE LIFE")
        with self.assertRaises(IntegrityError), transaction.atomic():
            AliasProduit.objects.create(membre=a1, libelle_brut="CITADINE life", produit=p01)
        AliasProduit.objects.create(membre=None, libelle_brut="Citadine Life", produit=p01)  # alias global
        with self.assertRaises(IntegrityError), transaction.atomic():
            AliasProduit.objects.create(membre=None, libelle_brut="citadine  LIFE", produit=p01)

    # --- grilles de segments versionnées
    def test_le_classement_reste_dans_sa_segmentation_et_les_grilles_coexistent(self):
        v1 = Segmentation.objects.get(code="GIPAME-V1")
        v2 = Segmentation.objects.create(code="GIPAME-V2", libelle="Grille de test")
        seg2 = Segment.objects.create(categorie=Categorie.objects.create(segmentation=v2, code="X", libelle="X"),
                                      code="Y", libelle="Y")
        neuf = Produit.objects.create(code="P99", modele=self.d.produits["P01"].modele, finition="TEST",
                                      libelle_affiche="test", statut="ACTIF")
        with self.assertRaises(IntegrityError), transaction.atomic():  # segment d'une autre grille
            ClassementProduit.objects.create(produit=neuf, segmentation=v1, segment=seg2)
        p01 = self.d.produits["P01"]
        ClassementProduit.objects.create(produit=p01, segmentation=v2, segment=seg2)  # nouvelle grille, ancienne intacte
        self.assertEqual(p01.classements.count(), 2)
        with self.assertRaises(IntegrityError), transaction.atomic():  # un seul segment par grille
            ClassementProduit.objects.create(produit=p01, segmentation=v2, segment=seg2)
