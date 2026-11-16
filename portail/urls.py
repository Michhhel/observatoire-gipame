"""Routes du portail. Aucun identifiant de membre dans les URL : le membre vient de la session."""
from django.urls import path

from .vues import administration, bureau, commun, compte, gestion, membre, referentiel

app_name = "portail"

urlpatterns = [
    path("", compte.racine, name="racine"),
    path("sante/", compte.sante, name="sante"),
    # --- compte
    path("connexion/", compte.Connexion.as_view(), name="connexion"),
    path("deconnexion/", compte.Deconnexion.as_view(), name="deconnexion"),
    path("mot-de-passe-oublie/", compte.MotDePasseOublie.as_view(), name="mot_de_passe_oublie"),
    path("mot-de-passe-oublie/envoye/", compte.MotDePasseEnvoye.as_view(), name="mot_de_passe_envoye"),
    path("nouveau-mot-de-passe/<uidb64>/<token>/", compte.NouveauMotDePasse.as_view(), name="nouveau_mot_de_passe"),
    path("activation/<uidb64>/<token>/", compte.Activation.as_view(), name="activation"),
    path("mot-de-passe-change/", compte.MotDePasseChange.as_view(), name="mot_de_passe_change"),
    # --- membre
    path("accueil/", membre.accueil, name="accueil"),
    path("declarer/", membre.assistant, name="assistant"),
    path("declarer/gabarit/", membre.gabarit, name="gabarit"),
    path("declarer/rapport/<int:depot_id>/", membre.rapport, name="rapport"),
    path("declarer/soumettre/<int:declaration_id>/", membre.soumettre, name="soumettre"),
    path("declarer/confirmation/<int:declaration_id>/", membre.confirmation, name="confirmation"),
    path("historique/", membre.historique, name="historique"),
    path("mon-annee/", membre.mon_annee, name="mon_annee"),
    path("mon-annee/export/", membre.export_annee, name="export_annee"),
    path("le-marche/", membre.marche, name="marche"),
    path("mes-produits/", membre.mes_produits, name="mes_produits"),
    path("mes-produits/<int:produit_id>/affichage/", membre.changer_affichage, name="changer_affichage"),
    # --- gestion
    path("gestion/", gestion.tableau, name="gestion_tableau"),
    path("gestion/rappels/", gestion.envoyer_rappels, name="gestion_rappels"),
    path("gestion/publications/", gestion.publications, name="gestion_publications"),
    path("gestion/propositions/", gestion.propositions, name="gestion_propositions"),
    path("gestion/propositions/<int:produit_id>/", gestion.proposition, name="gestion_proposition"),
    path("gestion/membres/", referentiel.membres, name="gestion_membres"),
    path("gestion/membres/nouveau/", referentiel.membre_nouveau, name="gestion_membre_nouveau"),
    path("gestion/membres/<int:membre_id>/", referentiel.membre, name="gestion_membre"),
    path("gestion/membres/<int:membre_id>/action/", referentiel.membre_action, name="gestion_membre_action"),
    path("gestion/catalogue/", gestion.catalogue, name="gestion_catalogue"),
    path("gestion/demandes-acces/", gestion.demandes_acces, name="gestion_demandes"),
    path("gestion/demandes-acces/<int:demande_id>/lecture/", gestion.lecture_acces, name="gestion_lecture_acces"),
    # --- bureau
    path("bureau/", bureau.tableau, name="bureau_tableau"),
    path("bureau/journal/", bureau.journal, name="bureau_journal"),
    path("bureau/approbations/", bureau.approbations, name="bureau_approbations"),
    path("bureau/approbations/<int:demande_id>/", bureau.approbation, name="bureau_approbation"),
    # --- administration (rôle TECHNIQUE)
    path("administration/comptes/", administration.comptes_liste, name="admin_comptes"),
    path("administration/comptes/<int:compte_id>/", administration.compte, name="admin_compte"),
    path("administration/comptes/<int:compte_id>/action/", administration.compte_action, name="admin_compte_action"),
    # --- pages publiques
    path("aide/", commun.aide, name="aide"),
    path("confidentialite/", commun.confidentialite, name="confidentialite"),
    # --- développement
    path("_galerie/", commun.galerie, name="galerie"),
]
