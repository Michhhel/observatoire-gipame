"""Cycle complet de démonstration : gabarit -> remplissage -> dépôt -> publication -> exports.

Chaque étape s'exécute avec le rôle PostgreSQL qui lui correspond (membre, calcul, bureau, gestion) : si ce
cycle passe avec la connexion `gipame_app` (sans superutilisateur), la matrice de droits est bonne.
Réservé à la base de démonstration (codes de membres A1..B3, données fictives).
"""
import io
import os
from types import SimpleNamespace

from openpyxl import load_workbook

from .contexte import en_role
from .demo import VENTES, premier_du_mois
from .excel import exports
from .excel.depot import deposer_declaration
from .excel.gabarit import generer_gabarit
from .models import Membre, Publication, Utilisateur
from .services import calculer_publication


def remplir_gabarit(contenu, quantites=None, attestation="OUI", aucune_vente="NON", motif="", commentaires=None, ajouts=None,
                    cellules=None):
    """Simule un membre qui remplit le fichier dans Excel. `quantites` : {code produit: quantité}."""
    wb = load_workbook(io.BytesIO(contenu))
    ws = wb["DECLARATION"]
    for r in range(8, ws.max_row + 1):
        code = ws.cell(r, 1).value
        if code == "TOTAL":
            break
        if code and quantites and code in quantites:
            ws.cell(r, 7).value = quantites[code]
        if code and commentaires and code in commentaires:
            ws.cell(r, 8).value = commentaires[code]
    ws["G2"] = attestation or None
    ws["G3"] = aucune_vente or None
    ws["G4"] = motif or None
    for k, ligne in enumerate(ajouts or []):
        for col, valeur in enumerate(ligne, 1):
            wb["AJOUTS"].cell(7 + k, col).value = valeur
    for (feuille, adresse), valeur in (cellules or {}).items():
        wb[feuille][adresse] = valeur
    sortie = io.BytesIO()
    wb.save(sortie)
    return sortie.getvalue()


def executer_cycle_demo(mois=None, sortie=None, journal=None):
    journal = journal or (lambda *_: None)
    mois = mois or premier_du_mois(0)
    fichiers = []  # (sous-dossier, nom, octets)

    with en_role("gipame_gestion"):
        membres = {m.code: m for m in Membre.objects.filter(code__in=list(VENTES))}
    if set(membres) != set(VENTES):
        raise RuntimeError("Base de démonstration absente : lancez d'abord « python manage.py seed_demo ».")
    comptes = {u.membre_id: u for u in Utilisateur.objects.filter(role_metier="MEMBRE",
                                                                  membre_id__in=[m.id for m in membres.values()])}
    rapports = {}
    journal(f"== Mois {mois:%Y-%m} : chaque membre télécharge son gabarit, le remplit et le dépose ==")
    for code, quantites in VENTES.items():
        m, u = membres[code], comptes[membres[code].id]
        with en_role("gipame_membre", membre_id=m.id, utilisateur_id=u.id):
            gabarit, version, n = generer_gabarit(m, mois)
            rempli = remplir_gabarit(gabarit, quantites)
            if code == "A1":  # un fichier volontairement faux, pour voir les contrôles à l'œuvre
                faux = remplir_gabarit(gabarit, {"P01": -5, "P14": 1.5}, attestation="OUI")
                rapport_faux = deposer_declaration(faux, "A1_avec_erreurs.xlsx", m, u, soumettre=True)
                fichiers.append(("erreurs", "A1_avec_erreurs.xlsx", faux))
                journal("-- A1 dépose un fichier avec erreurs :")
                journal(rapport_faux.en_texte())
            rapport = deposer_declaration(rempli, f"{code}_{mois:%Y-%m}.xlsx", m, u, soumettre=True)
        rapports[code] = rapport
        fichiers.append(("gabarits", f"declaration_{code}_{mois:%Y-%m}_v{version}.xlsx", gabarit))
        fichiers.append(("remplis", f"{code}_{mois:%Y-%m}.xlsx", rempli))
        journal(f"-- {code} : {rapport.resultat}, déclaration {rapport.statut_declaration}, {rapport.total_unites} unités")
        for p in rapport.problemes:
            journal(f"     {p}")

    journal("== Calcul de la publication (rôle gipame_calcul) ==")
    with en_role("gipame_calcul"):
        pub = calculer_publication(mois)
        n_cellules, n_masquees = pub.cellules.count(), pub.cellules.filter(supprime=True).count()
    journal(f"-- publication v{pub.version} : couverture {pub.couverture_pct} %, {n_cellules} cellules dont {n_masquees} masquées")

    journal("== Exports Excel, chacun avec le rôle de son destinataire ==")
    for code, m in membres.items():
        with en_role("gipame_membre", membre_id=m.id, utilisateur_id=comptes[m.id].id):
            fichiers.append(("exports", f"annee_{code}_{mois.year}.xlsx", exports.exporter_annee_membre(m, mois.year)))
    with en_role("gipame_bureau"):
        fichiers.append(("exports", f"publication_{mois:%Y-%m}_bureau.xlsx",
                         exports.exporter_publication(Publication.objects.get(pk=pub.pk))))
    with en_role("gipame_gestion"):
        fichiers.append(("exports", f"publication_{mois:%Y-%m}_gestion_detail.xlsx",
                         exports.exporter_publication(Publication.objects.get(pk=pub.pk), detail=True)))
        fichiers.append(("exports", "suivi_depots.xlsx", exports.exporter_suivi_depots()))
    if sortie:
        for sous_dossier, nom, contenu in fichiers:
            os.makedirs(os.path.join(sortie, sous_dossier), exist_ok=True)
            with open(os.path.join(sortie, sous_dossier, nom), "wb") as f:
                f.write(contenu)
        journal(f"== {len(fichiers)} fichiers écrits dans {sortie}/ ==")
    return SimpleNamespace(mois=mois, rapports=rapports, rapport_faux=rapport_faux, publication_id=pub.pk, fichiers=fichiers)
