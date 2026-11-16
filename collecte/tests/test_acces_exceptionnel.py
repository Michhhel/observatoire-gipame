"""Accès exceptionnel aux données individuelles : accord de postes, fenêtre limitée, journal."""
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase

from collecte.demo import charger_demo
from collecte.models import (ApprobationAcces, DemandeAccesExceptionnel, JournalAcces, ParametreSysteme,
                             Poste, TitulairePoste, Utilisateur)

from .outils import doit_echouer, en_tant_que, requete


class AccesExceptionnel(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.d = charger_demo()

    def _demande(self, utilisateur="technicien"):
        u = self.d.users[utilisateur]
        return DemandeAccesExceptionnel.objects.create(
            demandeur=u, motif="Écart de totaux à expliquer", membre_cible=self.d.membres["B1"],
            mois_debut=self.d.mois_plein, mois_fin=self.d.mois_plein)

    def _approuver(self, demande, poste, utilisateur, decision="APPROUVEE"):
        u, p = self.d.users[utilisateur], Poste.objects.get(code=poste)
        with en_tant_que("gipame_bureau", utilisateur_id=u.id):
            return ApprobationAcces.objects.create(demande=demande, poste=p, approbateur=u, decision=decision)

    def _approbation_refusee(self, demande, poste, utilisateur, qui=None):
        u, p = self.d.users[utilisateur], Poste.objects.get(code=poste)
        with en_tant_que("gipame_bureau", utilisateur_id=self.d.users[qui or utilisateur].id):
            doit_echouer(self, lambda: ApprobationAcces.objects.create(
                demande=demande, poste=p, approbateur=u, decision="APPROUVEE"), IntegrityError)

    def _lire(self, demande, utilisateur="technicien"):
        with en_tant_que("gipame_gestion", utilisateur_id=self.d.users[utilisateur].id):
            return requete("SELECT * FROM gipame_lecture_exceptionnelle(%s)", [demande.id])

    def _lecture_refusee(self, demande, utilisateur="technicien"):
        with en_tant_que("gipame_gestion", utilisateur_id=self.d.users[utilisateur].id):
            doit_echouer(self, lambda: requete("SELECT * FROM gipame_lecture_exceptionnelle(%s)", [demande.id]))

    def test_sans_accord_aucune_lecture(self):
        self._lecture_refusee(self._demande())

    def test_un_seul_accord_ne_suffit_pas_au_seuil_de_deux(self):
        dem = self._demande()
        self._approuver(dem, "PRESIDENT", "president")
        self._lecture_refusee(dem)

    def test_un_refus_ne_compte_pas_comme_un_accord(self):
        dem = self._demande()
        self._approuver(dem, "PRESIDENT", "president")
        self._approuver(dem, "VICE_PRESIDENT", "vice_president", decision="REFUSEE")
        self._lecture_refusee(dem)

    def test_deux_postes_differents_ouvrent_l_acces_et_chaque_lecture_est_journalisee(self):
        dem = self._demande()
        self._approuver(dem, "PRESIDENT", "president")
        self._approuver(dem, "DELEGUE_GENERAL", "delegue_general")
        lignes = self._lire(dem)
        self.assertEqual(len(lignes), 6)  # les 6 lignes de B1 pour le mois demandé, et rien d'autre
        self.assertIn(("B1", self.d.mois_plein, "P18", 90), lignes)
        self.assertEqual({l[0] for l in lignes}, {"B1"})
        trace = JournalAcces.objects.get(demande_id=dem.id)
        self.assertEqual((trace.nb_lignes, trace.utilisateur_id), (6, self.d.users["technicien"].id))

    def test_le_seuil_est_un_parametre_que_seul_le_proprietaire_change(self):
        ParametreSysteme.objects.filter(cle="seuil_approbations_acces").update(valeur="3")
        dem = self._demande()
        self._approuver(dem, "PRESIDENT", "president")
        self._approuver(dem, "VICE_PRESIDENT", "vice_president")
        self._lecture_refusee(dem)  # 2 sur 3 ne suffit plus
        self._approuver(dem, "DELEGUE_GENERAL", "delegue_general")
        self.assertEqual(len(self._lire(dem)), 6)
        ParametreSysteme.objects.filter(cle="seuil_approbations_acces").update(valeur="1")
        dem2 = self._demande()
        self._approuver(dem2, "PRESIDENT", "president")
        self.assertEqual(len(self._lire(dem2)), 6)  # « 1 sur 3 » est possible, mais c'est un choix de sécurité

    def test_le_demandeur_ne_peut_pas_approuver_sa_propre_demande(self):
        dem = self._demande("president")
        self._approbation_refusee(dem, "PRESIDENT", "president")

    def test_il_faut_detenir_le_poste_pour_l_approuver(self):
        dem = self._demande()
        self._approbation_refusee(dem, "PRESIDENT", "delegue_general")

    def test_pas_d_usurpation_d_identite(self):
        dem = self._demande()
        self._approbation_refusee(dem, "VICE_PRESIDENT", "vice_president", qui="president")

    def test_un_autre_utilisateur_ne_peut_pas_se_servir_de_la_demande(self):
        dem = self._demande()
        self._approuver(dem, "PRESIDENT", "president")
        self._approuver(dem, "VICE_PRESIDENT", "vice_president")
        self._lecture_refusee(dem, utilisateur="autre_technicien")

    def test_l_acces_expire(self):
        dem = self._demande()
        self._approuver(dem, "PRESIDENT", "president")
        self._approuver(dem, "VICE_PRESIDENT", "vice_president")
        requete("SET LOCAL gipame.purge = 'on'")  # seul le propriétaire peut réécrire l'historique
        requete("UPDATE collecte_approbationacces SET decide_le = now() - interval '3 hours' WHERE demande_id = %s", [dem.id])
        requete("SET LOCAL gipame.purge = 'off'")
        self._lecture_refusee(dem)

    def test_les_demandes_sont_visibles_du_bureau_et_de_leur_auteur_seulement(self):
        dem = self._demande()
        with en_tant_que("gipame_gestion", utilisateur_id=self.d.users["autre_technicien"].id):
            self.assertEqual(requete("SELECT count(*) FROM collecte_demandeaccesexceptionnel")[0][0], 0)
        with en_tant_que("gipame_gestion", utilisateur_id=self.d.users["technicien"].id):
            self.assertEqual(requete("SELECT count(*) FROM collecte_demandeaccesexceptionnel")[0][0], 1)
        with en_tant_que("gipame_bureau", utilisateur_id=self.d.users["president"].id):
            self.assertEqual(requete("SELECT count(*) FROM collecte_demandeaccesexceptionnel")[0][0], 1)

    def test_les_approbations_sont_figees(self):
        dem = self._demande()
        appr = self._approuver(dem, "PRESIDENT", "president")
        for sql in ("UPDATE collecte_approbationacces SET decision = 'REFUSEE' WHERE id = %s",
                    "DELETE FROM collecte_approbationacces WHERE id = %s"):
            with self.assertRaises(IntegrityError), transaction.atomic():
                requete(sql, [appr.id])

    def test_l_autorite_suit_le_poste_pas_la_personne(self):
        aujourdhui = date.today()
        TitulairePoste.objects.filter(poste__code="PRESIDENT").update(date_fin=aujourdhui - timedelta(days=1))
        nouveau = Utilisateur(username="nouveau_president", role_metier="BUREAU")
        nouveau.set_unusable_password()
        nouveau.save()
        TitulairePoste.objects.create(poste=Poste.objects.get(code="PRESIDENT"), utilisateur=nouveau, date_debut=aujourdhui)
        self.d.users["nouveau_president"] = nouveau
        dem = self._demande()
        self._approbation_refusee(dem, "PRESIDENT", "president")  # l'ancien titulaire n'a plus l'autorité
        self._approuver(dem, "PRESIDENT", "nouveau_president")
