"""Reprise de l'historique : lecture d'un ancien fichier (structure réelle, données fictives), rapprochement, chargement."""
import io

from django.test import TestCase
from openpyxl import load_workbook

from collecte.demo_historique import fabriquer_historique
from collecte.excel import commun as c
from collecte.excel.historique import charger_historique, ecrire_rapprochement, lire_historique
from collecte.models import (AliasProduit, ClassementProduit, Declaration, DepotFichier, LigneVente, Marque, Membre, Produit)


def modifier(contenu, fonction):
    wb = load_workbook(io.BytesIO(contenu))
    fonction(wb)
    sortie = io.BytesIO()
    wb.save(sortie)
    return sortie.getvalue()


class Historique(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ancien = fabriquer_historique()
        cls.lecture = lire_historique(cls.ancien)
        cls.rapprochement, cls.a_completer = ecrire_rapprochement(cls.lecture)

    def test_lecture_ignore_les_totaux_et_reconstruit_segment_et_origine(self):
        lecture = self.lecture
        self.assertEqual((lecture.annee, lecture.feuille, len(lecture.lignes)), (2024, "MTM 2024", 6))
        self.assertGreaterEqual(lecture.nb_ignorees, 1)  # le sous-total « NISSAN / SOUS-TOTAL A/B »
        par_libelle = {l["libelle"]: l for l in lecture.lignes}
        starlet = par_libelle["STARLET 1.5 ESS STYLE 4-AT"]
        self.assertEqual([starlet["mois"][m] for m in (1, 2, 3, 4)], [11, 12, 17, None])  # doublon additionné
        self.assertEqual((starlet["segment"], starlet["origine"], starlet["nb_source"]), ("AB", "JAPONAISE", 2))
        self.assertEqual((par_libelle["POLO 1.0 TSI"]["origine"], par_libelle["TUCSON 2.0 DIESEL"]["segment"],
                          par_libelle["TUCSON 2.0 DIESEL"]["origine"]), ("EUROPEENNE", "SUV", "COREENNE"))
        self.assertEqual((par_libelle["KANGOO VAN"]["segment"], par_libelle["KANGOO VAN"]["origine"]), ("VAN", "EUROPEENNE"))
        genres = {a["type"] for a in lecture.anomalies}
        self.assertEqual(genres, {"NEGATIF", "TEXTE", "DOUBLON_FUSIONNE"})
        self.assertEqual([par_libelle["ALTO 800 MC1"]["mois"][m] for m in (1, 2, 3)], [5, 0, None])  # négatif -> 0, texte -> vide

    def test_le_rapprochement_propose_tout_et_ne_contient_aucune_quantite(self):
        wb = load_workbook(io.BytesIO(self.rapprochement))
        self.assertEqual(wb.sheetnames, ["LISEZ-MOI", "MEMBRES", "MARQUES", "PRODUITS", "ANOMALIES"])
        self.assertEqual(self.a_completer, 0)
        membres = [r for r in wb["MEMBRES"].iter_rows(min_row=2, values_only=True) if r[0]]
        self.assertEqual({r[3] for r in membres}, {"CFAO-MOTORS", "SOCIDA", "SIFF", "SMT-CI"})
        produits = {r[3]: r for r in wb["PRODUITS"].iter_rows(min_row=2, values_only=True) if r[0]}
        starlet = produits["STARLET 1.5 ESS STYLE 4-AT"]
        self.assertEqual((starlet[7], starlet[9], starlet[10], starlet[11], starlet[15], starlet[16]),
                         ("STARLET", "ESSENCE", "BVA", 1500, "AB", "AUTO"))
        self.assertEqual(produits["STARLET 1.5 PETROL LIFE 5MT"][9], "ESSENCE")  # PETROL -> ESSENCE

    def test_chargement_a_blanc_n_ecrit_rien(self):
        avant = (Membre.objects.count(), Declaration.objects.count(), Produit.objects.count())
        rapport = charger_historique(self.ancien, self.rapprochement, a_blanc=True)
        self.assertFalse(rapport.erreurs, rapport.en_texte())
        self.assertEqual(rapport.declarations_creees, 12)
        self.assertEqual((Membre.objects.count(), Declaration.objects.count(), Produit.objects.count()), avant)

    def test_chargement_complet(self):
        rapport = charger_historique(self.ancien, self.rapprochement, nom_fichier="MTM_2024.xlsx")
        self.assertFalse(rapport.erreurs, rapport.en_texte())
        self.assertEqual((rapport.membres_crees, rapport.marques_creees, rapport.produits_crees, rapport.declarations_creees,
                          rapport.lignes_creees), (4, 5, 6, 12, 18))
        self.assertEqual(set(Membre.objects.values_list("code", flat=True)), {"CFAO-MOTORS", "SOCIDA", "SIFF", "SMT-CI"})
        self.assertFalse(Marque.objects.filter(code__startswith="NISSAN").exists())
        self.assertEqual(rapport.totaux[("CFAO-MOTORS", "2024-01")], 14)   # 11 + 3 : le doublon est additionné
        self.assertEqual(rapport.totaux[("CFAO-MOTORS", "2024-03")], 21)
        self.assertEqual(rapport.totaux[("SOCIDA", "2024-01")], 5)
        self.assertEqual((rapport.totaux[("SOCIDA", "2024-02")], rapport.totaux[("SOCIDA", "2024-03")]), (0, 0))
        self.assertFalse(any(mois > "2024-03" for (_c, mois) in rapport.totaux))     # mois sans chiffre : pas de déclaration
        decl = Declaration.objects.get(membre__code="SOCIDA", mois="2024-02-01")
        self.assertEqual((decl.source, decl.statut, decl.aucune_vente_confirmee, decl.attestation_complete),
                         ("IMPORT_HISTORIQUE", "SOUMISE", True, True))
        self.assertEqual(LigneVente.objects.count(), 18)
        self.assertEqual(ClassementProduit.objects.count(), 6)
        self.assertEqual(AliasProduit.objects.count(), 6)
        trace = DepotFichier.objects.get(type_depot="HISTORIQUE")
        self.assertEqual((trace.nom_fichier, trace.resultat), ("MTM_2024.xlsx", "ACCEPTE_AVEC_ALERTES"))
        self.assertTrue(any(p.code == "NEGATIF" for p in rapport.alertes))

    def test_un_second_chargement_ne_duplique_rien(self):
        charger_historique(self.ancien, self.rapprochement)
        compte = (Declaration.objects.count(), Produit.objects.count(), LigneVente.objects.count(), Membre.objects.count())
        rapport = charger_historique(self.ancien, self.rapprochement)
        self.assertEqual((rapport.declarations_creees, rapport.declarations_ignorees, rapport.produits_crees), (0, 12, 0))
        self.assertEqual((Declaration.objects.count(), Produit.objects.count(), LigneVente.objects.count(), Membre.objects.count()), compte)

    def test_l_annee_suivante_se_rapproche_toute_seule(self):
        charger_historique(self.ancien, self.rapprochement)
        suivant = fabriquer_historique(2025, decalage=2)
        lecture = lire_historique(suivant)
        rapprochement, a_completer = ecrire_rapprochement(lecture)
        produits = [r for r in load_workbook(io.BytesIO(rapprochement))["PRODUITS"].iter_rows(min_row=2, values_only=True) if r[0]]
        self.assertTrue(all(r[16] == "RAPPROCHE" and r[6] for r in produits))  # code produit déjà connu, statut RAPPROCHE
        rapport = charger_historique(suivant, rapprochement)
        self.assertFalse(rapport.erreurs, rapport.en_texte())
        self.assertEqual((rapport.produits_crees, rapport.produits_rapproches, rapport.declarations_creees), (0, 6, 12))
        self.assertEqual(Produit.objects.count(), 6)

    def test_un_rapprochement_incomplet_bloque_tout(self):
        def vider_origine(wb):
            wb["MARQUES"]["E2"] = None
        avant = Declaration.objects.count()
        rapport = charger_historique(self.ancien, modifier(self.rapprochement, vider_origine))
        self.assertEqual({p.code for p in rapport.erreurs}, {"RAPPROCHEMENT_INCOMPLET"})
        self.assertEqual(Declaration.objects.count(), avant)
        self.assertFalse(Membre.objects.exists())

    def test_une_ligne_absente_du_rapprochement_est_signalee(self):
        rapport = charger_historique(self.ancien, modifier(self.rapprochement, lambda wb: wb["PRODUITS"].delete_rows(2)))
        self.assertIn("SANS_RAPPROCHEMENT", {p.code for p in rapport.erreurs})
        self.assertFalse(Membre.objects.exists())

    def test_fichier_illisible_ou_dangereux(self):
        with self.assertRaises(c.FichierInvalide):
            lire_historique(b"pas un classeur")
