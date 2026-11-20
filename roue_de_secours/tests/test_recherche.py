"""Qualité de la recherche (jeu d'évaluation) et cloisonnement des fiches par rôle."""
import io

from django.core.management import call_command
from django.test import SimpleTestCase

from roue_de_secours import connaissances as k
from roue_de_secours.evaluation import CAS
from roue_de_secours.management.commands.roue_verifier import evaluer
from roue_de_secours.recherche import Index, raciner, termes


class Recherche(SimpleTestCase):
    def test_jeu_d_evaluation(self):
        echecs, faux_positifs = evaluer()
        self.assertLessEqual(len(echecs), len(CAS) * 0.1, "\n".join(f"{q} → {t}" for _, q, _, t in echecs))
        self.assertEqual(faux_positifs, [])

    def test_commande_roue_verifier(self):
        sortie = io.StringIO()  # portable (Windows comme Linux)
        call_command("roue_verifier", stdout=sortie)
        self.assertIn("Base de connaissances en ordre", sortie.getvalue())

    def test_un_membre_ne_recoit_jamais_une_fiche_reservee_a_un_autre_role(self):
        index = Index(k.sections())
        for question in ("créer un compte", "approuver une demande", "publier en définitif", "relancer les membres",
                         "journal des accès", "lire les chiffres d'un membre"):
            for r in index.chercher(question, "MEMBRE", k=10):
                self.assertTrue(r.section.visible_par("MEMBRE"), f"{question} → {r.section.fiche_id}")

    def test_accents_majuscules_et_pluriels(self):
        self.assertEqual(termes("Déclarations"), termes("declaration"))
        self.assertEqual(raciner("fichiers"), raciner("fichier"))

    def test_la_case_c_n_est_pas_un_mot_vide(self):
        self.assertIn("confidentiel", " ".join(termes("Que signifie « c » ?")))

    def test_question_precedente_aide_les_relances(self):
        index = Index(k.sections())
        self.assertEqual(index.chercher("et où ça ?", "MEMBRE"), [])
        avec = [r.section.fiche_id for r in index.chercher("et où ça ?", "MEMBRE", contexte="exporter mes ventes en excel")]
        self.assertEqual(avec[0], "consulter-membre")
        relance = [r.section.fiche_id for r in index.chercher("et ensuite ?", "MEMBRE", contexte="comment proposer un nouveau produit")]
        self.assertEqual(relance[0], "nouveau-produit")
