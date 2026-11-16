"""Contraintes d'intégrité : ce que la base refuse, quoi que fasse l'application."""
from datetime import date, timedelta

from django.db import IntegrityError, ProgrammingError, transaction
from django.test import TestCase

from collecte.demo import charger_demo, premier_du_mois
from collecte.models import (Boite, Concession, Declaration, JournalModification, LigneVente, Marque,
                             Membre, PeriodeAdhesion, Poste, Produit, TitulairePoste, Utilisateur)

from .outils import doit_echouer, en_tant_que, requete


class Contraintes(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()

    def test_pas_de_chevauchement_de_concessions_mais_une_marque_peut_avoir_deux_distributeurs(self):
        marque = Marque.objects.get(code="ALPHA-M")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Concession.objects.create(membre=self.d.membres["A1"], marque=marque, date_debut=date(2026, 1, 1))
        Concession.objects.create(membre=self.d.membres["B3"], marque=marque, date_debut=date(2026, 1, 1))

    def test_un_membre_peut_sortir_puis_revenir_sans_chevauchement(self):
        b3 = self.d.membres["B3"]
        with self.assertRaises(IntegrityError), transaction.atomic():
            PeriodeAdhesion.objects.create(membre=b3, date_debut=date(2026, 6, 1))
        PeriodeAdhesion.objects.filter(membre=b3).update(date_fin=date(2026, 5, 31))
        PeriodeAdhesion.objects.create(membre=b3, date_debut=date(2026, 9, 1))

    def test_le_mois_doit_etre_un_premier_du_mois(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Declaration.objects.create(membre=self.d.membres["A1"], mois=date(2026, 3, 15), version=1)

    def test_une_quantite_negative_est_refusee(self):
        decl = Declaration.objects.create(membre=self.d.membres["A1"], mois=premier_du_mois(0), version=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            LigneVente.objects.create(declaration=decl, produit=self.d.produits["P01"], quantite=-1)

    def test_un_compte_membre_exige_un_membre_et_les_autres_roles_n_en_ont_pas(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Utilisateur.objects.create(username="orphelin", role_metier="MEMBRE")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Utilisateur.objects.create(username="dirigeant_membre", role_metier="BUREAU", membre=self.d.membres["A1"])

    def test_un_seul_titulaire_par_poste_a_la_fois(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TitulairePoste.objects.create(poste=Poste.objects.get(code="PRESIDENT"),
                                          utilisateur=self.d.users["technicien"], date_debut=date(2026, 1, 1))

    def test_les_codes_publics_sont_immuables(self):
        for modele, code in ((Membre, "A1"), (Produit, "P01"), (Marque, "BETA")):
            with self.subTest(modele.__name__), self.assertRaises(IntegrityError), transaction.atomic():
                modele.objects.filter(code=code).update(code=code + "-X")

    def test_aucune_suppression_physique(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            requete("DELETE FROM collecte_origine WHERE code = 'AUTRES'")

    def test_la_purge_exige_le_role_de_purge_le_drapeau_seul_ne_suffit_pas(self):
        a1 = self.d.membres["A1"]
        ligne = LigneVente.objects.filter(declaration__membre=a1).first()
        with en_tant_que("gipame_membre", membre_id=a1.id):  # droit DELETE sur les lignes, mais pas le rôle de purge
            requete("SET LOCAL gipame.purge = 'on'")
            doit_echouer(self, lambda: requete("DELETE FROM collecte_lignevente WHERE id = %s", [ligne.pk]), IntegrityError)
        Boite.objects.create(code="TEST", libelle="à purger")
        requete("SET LOCAL gipame.purge = 'on'")  # le propriétaire (sous scellés) peut purger explicitement
        self.assertEqual(requete("DELETE FROM collecte_boite WHERE code = 'TEST'"), 1)

    def test_l_audit_garde_l_ancien_et_le_nouvel_etat(self):
        Produit.objects.filter(code="P01").update(libelle_affiche="Libellé modifié")
        trace = JournalModification.objects.filter(table_nom="collecte_produit", operation="UPDATE").latest("id")
        self.assertEqual(trace.ancien["libelle_affiche"], "ALPHA-M Citadine LIFE")
        self.assertEqual(trace.nouveau["libelle_affiche"], "Libellé modifié")

    def test_les_journaux_sont_en_ajout_seulement(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            requete("DELETE FROM collecte_journalmodification")

    def test_les_alertes_de_retard_suivent_le_delai_de_grace_modifiable(self):
        g = self.d.users["gestionnaire"]
        sql = ("SELECT membre_code, en_retard, statut_depot FROM collecte_v_suivi_depots WHERE mois = %s")
        with en_tant_que("gipame_gestion", utilisateur_id=g.id):
            requete("UPDATE collecte_parametresysteme SET valeur = '0' WHERE cle = 'jours_grace_depot'")
            lignes = {r[0]: r for r in requete(sql, [self.d.mois_partiel])}
        self.assertTrue(lignes["B3"][1])          # B3 n'a rien déposé : en retard
        self.assertIsNone(lignes["B3"][2])
        self.assertFalse(lignes["A1"][1])         # A1 a déposé
        self.assertEqual(lignes["A1"][2], "SOUMISE")
