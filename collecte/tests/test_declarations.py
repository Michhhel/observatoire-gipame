"""Cycle de vie d'une déclaration : brouillon, soumission, correction, figement."""
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase

from collecte.demo import charger_demo, premier_du_mois
from collecte.models import Declaration, LigneVente

from .outils import en_tant_que, requete


class CycleDeVieDesDeclarations(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()
        cls.mois = premier_du_mois(0)  # mois courant : aucune déclaration pré-chargée

    def _brouillon(self, code="A1", quantites=None, mois=None, version=1):
        decl = Declaration.objects.create(membre=self.d.membres[code], mois=mois or self.mois, version=version)
        for produit, q in (quantites or {"P01": 12, "P14": 3}).items():
            LigneVente.objects.create(declaration=decl, produit=self.d.produits[produit], quantite=q)
        return decl

    def _soumettre(self, decl, attestation=True, **champs):
        decl.attestation_complete = attestation
        decl.statut = "SOUMISE"
        for cle, valeur in champs.items():
            setattr(decl, cle, valeur)
        decl.save()

    def test_soumission_normale_horodate_la_declaration(self):
        decl = self._brouillon()
        self._soumettre(decl)
        decl.refresh_from_db()
        self.assertEqual(decl.statut, "SOUMISE")
        self.assertIsNotNone(decl.soumise_le)

    def test_l_attestation_de_completude_est_obligatoire(self):
        decl = self._brouillon()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._soumettre(decl, attestation=False)

    def test_une_declaration_a_zero_exige_la_confirmation_aucune_vente(self):
        decl = self._brouillon(quantites={"P01": 0, "P14": 0})
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._soumettre(decl)
        self._soumettre(decl, aucune_vente_confirmee=True)
        decl.refresh_from_db()
        self.assertEqual(decl.statut, "SOUMISE")

    def test_une_declaration_sans_ligne_est_refusee(self):
        decl = Declaration.objects.create(membre=self.d.membres["A1"], mois=self.mois, version=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._soumettre(decl)

    def test_un_mois_futur_est_interdit(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Declaration.objects.create(membre=self.d.membres["A1"], mois=premier_du_mois(1), version=1)

    def test_la_version_doit_etre_la_suivante(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Declaration.objects.create(membre=self.d.membres["A1"], mois=self.d.mois_plein, version=3)

    def test_un_seul_brouillon_par_membre_et_par_mois(self):
        self._brouillon()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Declaration.objects.create(membre=self.d.membres["A1"], mois=self.mois, version=2)

    def test_une_correction_remplace_la_version_precedente(self):
        a1 = self.d.membres["A1"]
        v1 = Declaration.objects.get(membre=a1, mois=self.d.mois_plein, version=1)
        v2 = self._brouillon(quantites={"P01": 110, "P14": 10}, mois=self.d.mois_plein, version=2)
        with self.assertRaises(IntegrityError), transaction.atomic():  # motif de correction manquant
            self._soumettre(v2)
        self._soumettre(v2, motif_correction="Facture tardive du 30")
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual((v1.statut, v2.statut), ("REMPLACEE", "SOUMISE"))
        self.assertEqual(v2.precedente_id, v1.id)
        self.assertEqual(Declaration.objects.filter(membre=a1, mois=self.d.mois_plein, statut="SOUMISE").count(), 1)
        self.assertEqual(v1.lignes.count(), 2)  # l'ancienne version reste intacte (audit)

    def test_une_declaration_soumise_est_immuable(self):
        decl = Declaration.objects.get(membre=self.d.membres["A1"], mois=self.d.mois_plein, version=1)
        ligne = decl.lignes.first()
        actions = {
            "modifier une ligne": lambda: LigneVente.objects.filter(pk=ligne.pk).update(quantite=999),
            "supprimer une ligne": lambda: requete("DELETE FROM collecte_lignevente WHERE id = %s", [ligne.pk]),
            "ajouter une ligne": lambda: LigneVente.objects.create(declaration=decl, produit=self.d.produits["P03"], quantite=1),
            "changer le mois": lambda: Declaration.objects.filter(pk=decl.pk).update(mois=premier_du_mois(-3)),
            "supprimer la déclaration": lambda: requete("DELETE FROM collecte_declaration WHERE id = %s", [decl.pk]),
        }
        for nom, action in actions.items():
            with self.subTest(nom), self.assertRaises(DatabaseError), transaction.atomic():
                action()

    def test_un_brouillon_se_modifie_librement_puis_s_annule_sans_retour(self):
        decl = self._brouillon()
        LigneVente.objects.filter(declaration=decl, produit=self.d.produits["P01"]).update(quantite=20)
        decl.statut = "ANNULEE"
        decl.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Declaration.objects.filter(pk=decl.pk).update(statut="BROUILLON")

    def test_le_membre_depose_lui_meme_avec_le_role_membre(self):
        a1, u = self.d.membres["A1"], self.d.users["A1"]
        with en_tant_que("gipame_membre", membre_id=a1.id, utilisateur_id=u.id):
            decl = Declaration.objects.create(membre=a1, mois=self.mois, version=1)
            LigneVente.objects.create(declaration=decl, produit=self.d.produits["P01"], quantite=4)
            decl.attestation_complete = True
            decl.statut = "SOUMISE"
            decl.save(update_fields=["statut", "attestation_complete", "modifie_le"])
        decl.refresh_from_db()
        self.assertEqual((decl.statut, decl.soumise_par_id), ("SOUMISE", u.id))
