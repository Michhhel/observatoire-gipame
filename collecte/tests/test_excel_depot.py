"""Dépôt d'un fichier Excel : ce qui est accepté, ce qui est refusé, et ce qui n'est jamais écrit."""
import io
import zipfile

from django.db import ProgrammingError
from django.test import TestCase
from openpyxl import load_workbook

from collecte.contexte import en_role
from collecte.demo import VENTES, charger_demo, premier_du_mois
from collecte.excel.depot import soumettre_declaration
from collecte.models import (Concession, Declaration, DepotFichier, LigneVente, Marque, Modele, ParametreSysteme, Produit,
                             ProduitMembre)

from .outils import deposer, doit_echouer, en_tant_que, generer, remplir, requete


def codes(rapport):
    return [p.code for p in rapport.problemes]


class DepotExcel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()
        cls.mois = premier_du_mois(0)  # mois courant : pas encore de déclaration ; le mois précédent existe

    def _vide(self, code="A1"):
        return generer(self.d, code, self.mois)

    # --- cas nominal
    def test_depot_nominal_soumis_sans_alerte(self):
        r = deposer(self.d, "A1", remplir(self._vide(), {"P01": 95, "P14": 12}))
        self.assertTrue(r.ok, r.en_texte())
        self.assertEqual((r.resultat, r.statut_declaration, r.nb_lignes, r.total_unites), ("ACCEPTE", "SOUMISE", 2, 107))
        decl = Declaration.objects.get(membre=self.d.membres["A1"], mois=self.mois)
        self.assertEqual((decl.statut, decl.version, decl.attestation_complete), ("SOUMISE", 1, True))
        self.assertEqual(dict(decl.lignes.values_list("produit__code", "quantite")), {"P01": 95, "P14": 12})
        trace = DepotFichier.objects.get(pk=r.depot_id)
        self.assertEqual((trace.resultat, trace.empreinte_sha256, trace.declaration_id), ("ACCEPTE", r.empreinte, decl.id))

    # --- alertes (jamais bloquantes)
    def test_alerte_de_variation_tant_qu_il_n_y_a_pas_de_commentaire(self):
        r = deposer(self.d, "A1", remplir(self._vide(), {"P01": 300, "P14": 10}), soumettre=False)
        self.assertIn("VARIATION", codes(r))
        self.assertEqual(r.resultat, "ACCEPTE_AVEC_ALERTES")
        r2 = deposer(self.d, "A1", remplir(self._vide(), {"P01": 300, "P14": 10}, commentaires={"P01": "Commande de flotte"}),
                     soumettre=False)
        self.assertNotIn("VARIATION", codes(r2))

    def test_alerte_quand_tout_est_identique_au_mois_precedent(self):
        r = deposer(self.d, "A1", remplir(self._vide(), VENTES["A1"]), soumettre=False)
        self.assertIn("IDENTIQUE", codes(r))

    # --- zéros et attestation
    def test_toutes_les_quantites_a_zero_exigent_la_confirmation(self):
        r = deposer(self.d, "A1", remplir(self._vide(), {}, aucune_vente="NON"))
        self.assertEqual(codes(r), ["ZERO_NON_CONFIRME"])
        self.assertFalse(Declaration.objects.filter(membre=self.d.membres["A1"], mois=self.mois).exists())
        r2 = deposer(self.d, "A1", remplir(self._vide(), {}, aucune_vente="OUI"))
        self.assertTrue(r2.ok, r2.en_texte())
        self.assertEqual(r2.statut_declaration, "SOUMISE")

    def test_aucune_vente_et_quantites_positives_sont_incoherentes(self):
        r = deposer(self.d, "A1", remplir(self._vide(), {"P01": 5}, aucune_vente="OUI"))
        self.assertIn("INCOHERENCE", codes(r))

    def test_sans_attestation_la_declaration_reste_brouillon_et_se_remplace_librement(self):
        r = deposer(self.d, "A1", remplir(self._vide(), {"P01": 95, "P14": 12}, attestation=""))
        self.assertEqual((r.statut_declaration, r.resultat), ("BROUILLON", "ACCEPTE_AVEC_ALERTES"))
        self.assertIn("ATTESTATION_MANQUANTE", codes(r))
        r2 = deposer(self.d, "A1", remplir(self._vide(), {"P01": 90, "P14": 14}, attestation="NON"), soumettre=False)
        self.assertEqual(r2.declaration_id, r.declaration_id)  # même brouillon, lignes remplacées
        self.assertEqual(Declaration.objects.filter(membre=self.d.membres["A1"], mois=self.mois).count(), 1)
        self.assertEqual(dict(LigneVente.objects.filter(declaration_id=r.declaration_id).values_list("produit__code", "quantite")),
                         {"P01": 90, "P14": 14})
        with en_role("gipame_membre", membre_id=self.d.membres["A1"].id, utilisateur_id=self.d.users["A1"].id):
            decl = soumettre_declaration(r.declaration_id, self.d.membres["A1"], attestation=True)
        self.assertEqual(decl.statut, "SOUMISE")

    # --- identité du fichier
    def test_le_fichier_d_un_autre_membre_est_refuse(self):
        r = deposer(self.d, "A1", remplir(self._vide("B1"), {"P04": 40}))
        self.assertEqual(codes(r), ["COMPTE"])
        self.assertEqual(r.resultat, "REJETE")
        self.assertFalse(Declaration.objects.filter(mois=self.mois, membre__in=[self.d.membres["A1"], self.d.membres["B1"]]).exists())

    def test_un_fichier_modifie_ou_non_genere_par_le_portail_est_refuse(self):
        wb = load_workbook(io.BytesIO(self._vide("B1")))
        meta = wb["_META"]
        for r in range(1, 20):
            if meta.cell(r, 1).value == "membre_code":
                meta.cell(r, 2).value = "A1"  # B1 se fait passer pour A1
        sortie = io.BytesIO()
        wb.save(sortie)
        r = deposer(self.d, "A1", remplir(sortie.getvalue(), {"P04": 40}))
        self.assertEqual(codes(r), ["SIGNATURE"])

    def test_un_gabarit_perime_est_refuse(self):
        vide = self._vide()
        self.assertTrue(deposer(self.d, "A1", remplir(vide, {"P01": 95, "P14": 12})).ok)
        r = deposer(self.d, "A1", remplir(vide, {"P01": 50, "P14": 5}))
        self.assertEqual(codes(r), ["GABARIT_PERIME"])

    # --- structure du tableau
    def test_ligne_ajoutee_ou_supprimee_ou_code_modifie(self):
        wb = load_workbook(io.BytesIO(self._vide()))
        wb["DECLARATION"]["A8"] = "P03"  # code d'un produit d'un autre membre
        sortie = io.BytesIO()
        wb.save(sortie)
        r = deposer(self.d, "A1", sortie.getvalue())
        self.assertEqual(sorted(codes(r)), ["LIGNE_AJOUTEE", "LIGNE_MANQUANTE"])
        wb = load_workbook(io.BytesIO(self._vide()))
        wb["DECLARATION"].delete_rows(9)
        sortie = io.BytesIO()
        wb.save(sortie)
        self.assertIn("LIGNE_MANQUANTE", codes(deposer(self.d, "A1", sortie.getvalue())))

    def test_quantites_invalides(self):
        cas = {-3: "QUANTITE", 1.5: "QUANTITE", "abc": "QUANTITE", None: "QUANTITE", 999999: "QUANTITE", True: "QUANTITE"}
        for valeur, attendu in cas.items():
            with self.subTest(valeur=valeur):
                r = deposer(self.d, "A1", remplir(self._vide(), {"P01": valeur, "P14": 5}), soumettre=False)
                self.assertEqual(codes(r), [attendu])
                self.assertEqual(r.erreurs[0].ligne, 8 if r.erreurs[0].ligne == 8 else 9)
        # un nombre saisi comme du texte est accepté avec une alerte
        r = deposer(self.d, "A1", remplir(self._vide(), {"P01": "95", "P14": 12}), soumettre=False)
        self.assertTrue(r.ok)
        self.assertIn("NOMBRE_EN_TEXTE", codes(r))

    def test_une_formule_sans_valeur_calculee_est_refusee_pas_devinee(self):
        r = deposer(self.d, "A1", remplir(self._vide(), {"P01": "=10+5", "P14": 12}), soumettre=False)
        self.assertEqual(codes(r), ["QUANTITE"])

    def test_deux_lignes_avec_le_meme_code(self):
        wb = load_workbook(io.BytesIO(self._vide()))
        wb["DECLARATION"]["A9"] = wb["DECLARATION"]["A8"].value
        sortie = io.BytesIO()
        wb.save(sortie)
        r = deposer(self.d, "A1", sortie.getvalue())
        self.assertIn("DOUBLON", codes(r))

    # --- fichiers dangereux
    def test_fichiers_dangereux_ou_invalides(self):
        self.assertEqual(codes(deposer(self.d, "A1", b"code,quantite\nP01,3\n")), ["FICHIER"])
        valide = self._vide()
        piege = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(valide)) as z_in, zipfile.ZipFile(piege, "w") as z_out:
            for info in z_in.infolist():
                z_out.writestr(info, z_in.read(info.filename))
            z_out.writestr("xl/vbaProject.bin", b"macro")
        self.assertEqual(codes(deposer(self.d, "A1", piege.getvalue())), ["FICHIER"])
        ParametreSysteme.objects.filter(cle="import_taille_max_ko").update(valeur="1")
        self.assertEqual(codes(deposer(self.d, "A1", valide)), ["FICHIER"])

    # --- corrections
    def test_correction_motivee_remplace_la_version_precedente(self):
        a1 = self.d.membres["A1"]
        self.assertTrue(deposer(self.d, "A1", remplir(self._vide(), {"P01": 95, "P14": 12})).ok)
        v2 = self._vide()
        ws = load_workbook(io.BytesIO(v2))["DECLARATION"]
        self.assertEqual((ws["B4"].value[:1], ws.cell(8, 7).value, ws.cell(9, 7).value), ("2", 12, 95))  # pré-rempli
        r = deposer(self.d, "A1", remplir(v2, {}, motif="x"))  # rien ne change
        self.assertEqual(codes(r), ["AUCUNE_MODIFICATION"])
        r = deposer(self.d, "A1", remplir(v2, {"P01": 110}, motif=""))
        self.assertIn("MOTIF_REQUIS", codes(r))
        r = deposer(self.d, "A1", remplir(v2, {"P01": 110}, motif="Facture tardive du 30"))
        self.assertTrue(r.ok, r.en_texte())
        decl = {x.version: x for x in Declaration.objects.filter(membre=a1, mois=self.mois)}
        self.assertEqual((decl[1].statut, decl[2].statut, decl[2].precedente_id), ("REMPLACEE", "SOUMISE", decl[1].id))
        self.assertEqual(dict(decl[1].lignes.values_list("produit__code", "quantite")), {"P01": 95, "P14": 12})  # historique intact

    # --- nouveaux produits
    def _ajout(self, **champs):
        base = ["ALPHA-M", "Nouveaute", "gt line", "ESSENCE", "BVA", 1600, 8, None, None, 5, "4x2", "Citadine", 4, "lancement"]
        for i, v in champs.items():
            base[int(i[1:])] = v
        return base

    def test_un_nouveau_produit_est_propose_une_seule_fois_et_reste_prive(self):
        fichier = remplir(self._vide(), {"P01": 95, "P14": 12}, ajouts=[self._ajout()])
        r = deposer(self.d, "A1", fichier, soumettre=False)
        self.assertTrue(r.ok, r.en_texte())
        self.assertEqual((r.nb_ajouts, r.nb_lignes, r.total_unites), (1, 3, 111))
        deposer(self.d, "A1", fichier, soumettre=False)  # redépôt du brouillon : pas de doublon
        p = Produit.objects.get(statut="PROPOSE")
        self.assertEqual((p.finition, p.propose_par_id, p.modele.nom if p.modele else p.modele_propose), ("GT LINE", self.d.membres["A1"].id, "Nouveaute"))
        self.assertTrue(LigneVente.objects.filter(declaration_id=r.declaration_id, produit=p, quantite=4).exists())
        with en_tant_que("gipame_membre", membre_id=self.d.membres["B1"].id):
            self.assertEqual(requete("SELECT count(*) FROM collecte_produit WHERE id = %s", [p.id])[0][0], 0)
        gab = generer(self.d, "A1", self.mois)
        ws = load_workbook(io.BytesIO(gab))["DECLARATION"]
        self.assertIn(p.code, {ws.cell(r_, 1).value for r_ in range(8, 14)})  # la proposition figure dans son gabarit

    def test_ajouts_invalides(self):
        cas = {
            "marque non détenue": (self._ajout(c0="BETA"), "AJOUT_MARQUE"),
            "énergie manquante": (self._ajout(c3=None), "AJOUT_ENERGIE"),
            "modèle manquant": (self._ajout(c1=None), "AJOUT_INCOMPLET"),
            "quantité invalide": (self._ajout(c12="beaucoup"), "AJOUT_QUANTITE"),
            "produit déjà au catalogue": (["ALPHA-M", "Citadine", "life", "ESSENCE", "BVM", None, None, None, None, None, "", "", 2, ""],
                                          "AJOUT_EXISTE_DEJA"),
        }
        for nom, (ligne, attendu) in cas.items():
            with self.subTest(nom):
                r = deposer(self.d, "A1", remplir(self._vide(), {"P01": 95, "P14": 12}, ajouts=[ligne]), soumettre=False)
                self.assertEqual(codes(r), [attendu])
        self.assertFalse(Produit.objects.filter(statut="PROPOSE").exists())  # rien n'a été écrit

    # --- cohérence avec le catalogue
    def test_produit_retire_depuis_le_telechargement(self):
        vide = self._vide()
        ProduitMembre.objects.create(membre=self.d.membres["A1"], produit=self.d.produits["P14"], etat="MASQUE")
        r = deposer(self.d, "A1", remplir(vide, {"P01": 95, "P14": 12}), soumettre=False)
        self.assertEqual(codes(r), ["PRODUIT_RETIRE"])

    def test_produit_ajoute_au_catalogue_depuis_le_telechargement(self):
        vide = self._vide()
        Produit.objects.create(code="P97", modele=Modele.objects.get(code="ALPHA-M-CITADINE"), finition="NEUVE",
                               libelle_affiche="nouveau", statut="ACTIF")
        r = deposer(self.d, "A1", remplir(vide, {"P01": 95, "P14": 12}), soumettre=False)
        self.assertTrue(r.ok)
        self.assertIn("CATALOGUE_PLUS_RECENT", codes(r))

    # --- traces et droits
    def test_un_rejet_n_ecrit_que_sa_trace_et_chaque_membre_ne_voit_que_les_siennes(self):
        r = deposer(self.d, "A1", remplir(self._vide(), {"P01": -1, "P14": 12}))
        self.assertEqual(r.resultat, "REJETE")
        self.assertEqual(LigneVente.objects.filter(declaration__membre=self.d.membres["A1"], declaration__mois=self.mois).count(), 0)
        trace = DepotFichier.objects.get(pk=r.depot_id)
        self.assertEqual((trace.resultat, trace.nb_erreurs, trace.declaration_id), ("REJETE", 1, None))
        with en_tant_que("gipame_membre", membre_id=self.d.membres["B1"].id):
            self.assertEqual(requete("SELECT count(*) FROM collecte_depotfichier")[0][0], 0)
        with en_tant_que("gipame_gestion", utilisateur_id=self.d.users["gestionnaire"].id):
            self.assertEqual(requete("SELECT count(*) FROM collecte_depotfichier")[0][0], 1)
            doit_echouer(self, lambda: requete("SELECT rapport FROM collecte_depotfichier"), ProgrammingError)  # peut citer des quantités
