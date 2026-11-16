"""Publication des agrégats : seuils, dominance, groupes, suppression complémentaire, figement."""
from decimal import Decimal

from django.db import IntegrityError, ProgrammingError, transaction
from django.test import TestCase

from collecte.confidentialite import Cellule, appliquer_controle, relations_valides
from collecte.demo import charger_demo
from collecte.models import (Categorie, CelluleAgregat, ClassementProduit, Declaration, LigneVente,
                             ParametreSysteme, Publication, Segment, Segmentation)
from collecte.services import calculer_publication

from .outils import doit_echouer, en_tant_que, requete


def cellules_par_cle(pub):
    return {(c.dimension, c.cle): c for c in pub.cellules.all()}


class Publications(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()

    def test_les_cellules_suivent_les_regles_de_confidentialite(self):
        c = cellules_par_cle(calculer_publication(self.d.mois_plein))
        self.assertEqual(c[("TOTAL", "ALL")].total, 551)
        self.assertEqual(c[("SEGMENT", "AB")].total, 270)
        self.assertEqual(c[("ENERGIE", "ESSENCE")].total, 395)
        for cle in ("M2", "H", "PU_4X4"):  # moins de 3 contributeurs
            self.assertEqual((c[("SEGMENT", cle)].supprime, c[("SEGMENT", cle)].motif_suppression), (True, "SEUIL"), cle)
        m1 = c[("SEGMENT", "M1")]  # 4 membres mais 3 appartiennent au même groupe : 2 contributeurs indépendants
        self.assertEqual((m1.supprime, m1.motif_suppression, m1.n_contributeurs), (True, "SEUIL", 2))
        for cle in ("SUV", "VAN"):  # un contributeur pèse plus de 80 %
            self.assertEqual((c[("SEGMENT", cle)].supprime, c[("SEGMENT", cle)].motif_suppression), (True, "DOMINANCE"), cle)
        # PU_4X4 est masqué et PU_4X2 publiable : on le retrouverait par différence avec la catégorie
        self.assertEqual(c[("SEGMENT", "PU_4X2")].motif_suppression, "COMPLEMENTAIRE")
        for cle in ("JAPONAISE", "EUROPEENNE", "COREENNE", "CHINOISE", "AUTRES"):
            self.assertTrue(c[("ORIGINE", cle)].supprime, cle)  # marques exclusives : l'origine = un seul distributeur

    def test_une_valeur_supprimee_n_est_jamais_stockee(self):
        pub = calculer_publication(self.d.mois_plein)
        self.assertTrue(pub.cellules.filter(supprime=True).exists())
        self.assertFalse(pub.cellules.filter(supprime=True, total__isnull=False).exists())
        self.assertFalse(pub.cellules.filter(supprime=False, total__isnull=True).exists())

    def test_aucune_relation_parent_enfants_n_a_une_seule_cellule_masquee(self):
        pub = calculer_publication(self.d.mois_plein)
        seg_vers_cat = {s.code: s.categorie.code for s in Segment.objects.all()}
        cellules = [Cellule(c.dimension, c.cle, par_entite={"x": c.total or 0},
                            parent=f"CATEGORIE:{seg_vers_cat[c.cle]}" if c.dimension == "SEGMENT" else None,
                            supprime=c.supprime) for c in pub.cellules.all()]
        self.assertTrue(relations_valides(cellules))

    def test_le_controle_est_independant_de_la_base(self):
        # 3 contributeurs, mais l'un fait 90 % : dominance
        c = Cellule("SEGMENT", "S", {"a": 90, "b": 5, "c": 5}, parent="CATEGORIE:C")
        parent = Cellule("CATEGORIE", "C", {"a": 90, "b": 5, "c": 5})
        appliquer_controle([parent, c])
        self.assertEqual((c.motif, parent.motif), ("DOMINANCE", "DOMINANCE"))
        # seuil paramétrable : à 5 contributeurs minimum, 4 contributeurs équilibrés sont masqués
        d = Cellule("TOTAL", "ALL", {"a": 10, "b": 10, "c": 10, "d": 10})
        appliquer_controle([d], k_min=5)
        self.assertEqual(d.motif, "SEUIL")

    def test_couverture_publication_provisoire_puis_definitive(self):
        pub = calculer_publication(self.d.mois_partiel)  # B3 n'a pas déposé : 5 membres sur 6
        self.assertEqual((pub.nb_membres_attendus, pub.nb_membres_declarants), (6, 5))
        self.assertEqual(pub.couverture_pct, Decimal("83.33"))
        calculer_publication(self.d.mois_partiel, statut="DEFINITIVE")  # 83,33 % >= 80 %
        ParametreSysteme.objects.filter(cle="couverture_min_publication_pct").update(valeur="90")
        with self.assertRaises(ValueError):
            calculer_publication(self.d.mois_partiel, statut="DEFINITIVE")

    def test_une_publication_est_figee_une_correction_donne_une_nouvelle_version(self):
        pub = calculer_publication(self.d.mois_plein)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Publication.objects.filter(pk=pub.pk).update(couverture_pct=Decimal("1"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            CelluleAgregat.objects.filter(publication=pub).update(n_contributeurs=9)
        a1 = self.d.membres["A1"]
        v2 = Declaration.objects.create(membre=a1, mois=self.d.mois_plein, version=2)
        for code, q in {"P01": 110, "P14": 10}.items():
            LigneVente.objects.create(declaration=v2, produit=self.d.produits[code], quantite=q)
        v2.attestation_complete, v2.statut, v2.motif_correction = True, "SOUMISE", "Facture tardive"
        v2.save()
        pub2 = calculer_publication(self.d.mois_plein)
        self.assertEqual(pub2.version, 2)
        self.assertEqual(cellules_par_cle(pub2)[("TOTAL", "ALL")].total, 561)       # la correction est prise en compte
        self.assertEqual(cellules_par_cle(pub)[("TOTAL", "ALL")].total, 551)        # l'ancienne publication ne bouge pas

    def test_les_membres_lisent_les_totaux_mais_pas_les_details_de_suppression(self):
        calculer_publication(self.d.mois_plein)
        b1 = self.d.membres["B1"]
        with en_tant_que("gipame_membre", membre_id=b1.id):
            n = requete("SELECT count(*) FROM collecte_celluleagregat WHERE total IS NOT NULL")[0][0]
            doit_echouer(self, lambda: requete("SELECT motif_suppression FROM collecte_celluleagregat"), ProgrammingError)
            doit_echouer(self, lambda: requete("SELECT n_contributeurs FROM collecte_celluleagregat"), ProgrammingError)
        self.assertGreater(n, 0)

    def test_l_ancienne_grille_de_segments_reste_consultable(self):
        v1 = Segmentation.objects.get(code="GIPAME-V1")
        v2 = Segmentation.objects.create(code="GIPAME-V2", libelle="Grille de test")
        seg = Segment.objects.create(categorie=Categorie.objects.create(segmentation=v2, code="CITADINES", libelle="Citadines"),
                                     code="CITADINES", libelle="Citadines")
        for code in ("P01", "P02", "P04", "P05", "P06"):
            ClassementProduit.objects.create(produit=self.d.produits[code], segmentation=v2, segment=seg)
        c1 = cellules_par_cle(calculer_publication(self.d.mois_plein, segmentation=v1))
        c2 = cellules_par_cle(calculer_publication(self.d.mois_plein, segmentation=v2))
        self.assertEqual(c1[("SEGMENT", "AB")].total, 270)             # lecture selon l'ancienne grille : inchangée
        self.assertNotIn(("SEGMENT", "AB"), c2)
        self.assertEqual(c2[("SEGMENT", "CITADINES")].total, 270)      # lecture selon la nouvelle grille
