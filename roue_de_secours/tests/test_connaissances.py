"""Base de connaissances : format, liens, variables, cohérence avec le code et avec les paramètres réels."""
import importlib
from datetime import date

from django.test import SimpleTestCase

from portail.rapport import CONSEILS
from roue_de_secours import connaissances as k


class Fiches(SimpleTestCase):
    def test_toutes_les_fiches_sont_valides(self):
        self.assertEqual(k.verifier(), [])

    def test_aucun_avertissement_a_la_livraison(self):
        self.assertEqual(k.avertissements(), [])

    def test_ids_uniques_et_roles_connus(self):
        fiches = k.charger()
        self.assertEqual(len({f.id for f in fiches}), len(fiches))
        for f in fiches:
            self.assertTrue(f.roles <= k.ROLES | {"TOUS"}, f.id)

    def test_chaque_role_a_son_plan_du_site(self):
        for role in k.ROLES:
            self.assertTrue(any(s.toujours and s.visible_par(role) and s.fiche_id.startswith("plan-")
                                for s in k.sections()), role)

    def test_fiche_generee_couvre_tous_les_messages_du_rapport(self):
        titres = {s.titre for s in k.sections() if s.fiche_id == "messages-rapport"}
        self.assertEqual(titres, {quoi for quoi, _ in CONSEILS.values()})

    def test_seuils_par_defaut_identiques_aux_parametres_initiaux(self):
        initiaux = importlib.import_module("collecte.migrations.0003_donnees_initiales")
        valeurs = {cle: valeur for cle, valeur, *_ in initiaux.PARAMETRES}
        for var, (cle, defaut) in k.PARAMETRES_SECURITE.items():
            self.assertEqual(valeurs[cle], defaut, f"{var} : la valeur par défaut de la Roue diffère du paramètre {cle}")

    def test_toutes_les_variables_sont_remplies(self):
        vals = k.valeurs({"jours_grace_depot": "10", "definition_vente": "x", "contact_gipame": "", "import_quantite_max": "1",
                          "import_max_ajouts": "1", "import_taille_max_ko": "1", "import_variation_alerte_pct": "1",
                          "import_variation_min_unites": "1"})
        for s in k.sections():
            self.assertNotIn("{{", k.remplir(s.texte, vals), s.cle)

    def test_contact_par_defaut_et_contact_renseigne(self):
        self.assertEqual(k.valeurs({"contact_gipame": "À renseigner"})["contact"], "le secrétariat du GIPAME")
        self.assertIn("secretariat@exemple.ci", k.valeurs({"contact_gipame": "secretariat@exemple.ci"})["contact"])


class Obsolescence(SimpleTestCase):
    FICHE = "---\nid: essai\ntitre: Essai\nroles: TOUS\nmise_a_jour: {maj}\n---\n## Section\n{texte}\n"

    def test_fiche_non_relue_depuis_un_an_est_signalee(self):
        f = k.lire_texte(self.FICHE.format(maj="2026-01-01", texte="Texte."))
        self.assertEqual(k.avertissements([f], aujourd_hui=date(2026, 6, 1)), [])
        self.assertIn("non relue", k.avertissements([f], aujourd_hui=date(2027, 6, 1))[0])

    def test_annee_ecrite_en_dur_est_signalee(self):
        f = k.lire_texte(self.FICHE.format(maj="2026-11-20", texte="À partir de 2027, la règle change."))
        self.assertIn("année écrite en dur", k.avertissements([f], aujourd_hui=date(2026, 11, 20))[0])

    def test_lien_mort_et_variable_inconnue_sont_des_problemes(self):
        f = k.lire_texte(self.FICHE.format(maj="2026-11-20", texte="Voir [ici](/page-inexistante/) et {{inconnue}}."))
        problemes = " ".join(k.verifier([f]))
        self.assertIn("page inexistante", problemes)
        self.assertIn("variable inconnue", problemes)

    def test_entete_incomplet_refuse(self):
        with self.assertRaises(k.FicheInvalide):
            k.lire_texte("---\nid: x\ntitre: X\n---\ntexte\n")
