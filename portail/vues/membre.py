"""Écrans du membre : accueil, assistant de dépôt, rapport, soumission, confirmation, historique,
Mon année, Le marché, Mes produits.

Invariants (§6.4) : le membre est toujours `membre_courant(request)` ; chaque lecture/écriture de
données passe par les services de `collecte` ; aucune quantité ne figure dans une URL, un titre de
page, un message flash ou un journal.
"""
import json
from datetime import date, timedelta

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from collecte import produits as srv_produits
from collecte.contexte import parametres_publics
from collecte.excel.depot import deposer_declaration, soumettre_declaration
from collecte.excel.exports import _cellules, _libelles, _meilleures_publications, _ordre_cles, exporter_annee_membre
from collecte.excel.gabarit import generer_gabarit
from collecte.models import Declaration, DepotFichier, LigneVente, PeriodeAdhesion, Produit, ProduitMembre, Segmentation

from .. import formats, rapport as rapport_lisible
from ..acces import membre_courant, membre_requis
from ..formulaires import FormulaireDepot, FormulaireProposition, FormulaireSoumission

TYPE_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PROFONDEUR_MOIS = 36  # on peut déclarer / consulter jusqu'à 3 ans en arrière


# ----------------------------------------------------------------------------------------------- outils
def _mois_demande(request, nom="mois"):
    """Paramètre d'URL « AAAA-MM » → premier jour du mois. Par défaut : le mois écoulé.
    Un mois est une période, pas une donnée confidentielle : il peut venir de l'URL."""
    brut = request.GET.get(nom) or request.POST.get(nom)
    if not brut:
        return formats.premier_du_mois(decalage=-1)
    try:
        annee, mois = brut.split("-")
        d = date(int(annee), int(mois), 1)
    except (ValueError, AttributeError):
        raise Http404("Mois inconnu.")
    if d >= formats.premier_du_mois() or d < formats.premier_du_mois(decalage=-PROFONDEUR_MOIS):
        raise Http404("Ce mois n'est pas ouvert à la déclaration.")
    return d


def _annee_demandee(request):
    brut = request.GET.get("annee")
    annee = date.today().year
    if brut:
        try:
            annee = int(brut)
        except ValueError:
            raise Http404("Année inconnue.")
    if not (annee - 5 <= date.today().year <= annee + 1):
        raise Http404("Année hors de la période consultable.")
    return annee


def _attendue(membre, mois):
    """Vrai si le membre doit déclarer ce mois (période d'adhésion avec déclaration obligatoire)."""
    return PeriodeAdhesion.objects.filter(membre=membre, declaration_obligatoire=True, date_debut__lte=formats.fin_du_mois(mois)).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=mois)).exists()


def _situation(membre, mois, params):
    """État de la déclaration du membre pour un mois : à faire, brouillon, soumise ; date limite."""
    attendue = _attendue(membre, mois)
    declarations = list(Declaration.objects.filter(membre=membre, mois=mois).order_by("-version"))
    soumise = next((d for d in declarations if d.statut == "SOUMISE"), None)
    brouillon = next((d for d in declarations if d.statut == "BROUILLON"), None)
    date_limite = formats.fin_du_mois(mois) + timedelta(days=int(params.get("jours_grace_depot", 10)))
    depot_brouillon = DepotFichier.objects.filter(declaration=brouillon).order_by("-cree_le").first() if brouillon else None
    return {
        "mois": mois, "soumise": soumise, "brouillon": brouillon, "depot_brouillon": depot_brouillon, "versions": len(declarations),
        "etat": "SOUMISE" if soumise and not brouillon else ("BROUILLON" if brouillon else "A_FAIRE"),
        "date_limite": date_limite, "delai": formats.phrase_delai(date_limite),
        "en_retard": attendue and not soumise and formats.jours_restants(date_limite) < 0,
        "attendue": attendue, "correction": soumise is not None,
    }


def _total_declaration(declaration):
    if declaration is None:
        return None
    return sum(LigneVente.objects.filter(declaration=declaration).values_list("quantite", flat=True))


def _tendance(actuel, precedent):
    if actuel is None or precedent in (None, 0):
        return None
    return round((actuel - precedent) / precedent * 100, 1)


# ----------------------------------------------------------------------------------------------- accueil
@membre_requis
def accueil(request):
    membre = membre_courant(request)
    params = parametres_publics()
    mois = formats.premier_du_mois(decalage=-1)
    situation = _situation(membre, mois, params)
    precedent = formats.premier_du_mois(decalage=-2)
    soumise_prec = Declaration.objects.filter(membre=membre, mois=precedent, statut="SOUMISE").first()
    total_mois, total_prec = _total_declaration(situation["soumise"]), _total_declaration(soumise_prec)
    douze_mois = []
    for i in range(1, 13):
        m = formats.premier_du_mois(decalage=-i)
        s = _situation(membre, m, params)
        douze_mois.append({"mois": m, "etat": s["etat"], "en_retard": s["en_retard"], "attendue": s["attendue"]})
    derniers_depots = DepotFichier.objects.filter(membre=membre).order_by("-cree_le")[:5]
    return render(request, "portail/membre/accueil.html", {
        "membre": membre, "situation": situation, "total_mois": total_mois, "total_prec": total_prec,
        "tendance": _tendance(total_mois, total_prec), "mois_precedent": precedent, "douze_mois": douze_mois,
        "derniers_depots": derniers_depots, "annee": mois.year, "params": params, "page_active": "accueil",
    })


# ----------------------------------------------------------------------------------------------- assistant
@membre_requis
def assistant(request):
    """Les 3 étapes : Télécharger → Remplir → Déposer. Le dépôt (POST) crée un brouillon et redirige vers le rapport."""
    membre = membre_courant(request)
    params = parametres_publics()
    mois = _mois_demande(request)
    situation = _situation(membre, mois, params)
    formulaire = FormulaireDepot(request.POST or None, request.FILES or None, correction=situation["correction"])
    if request.method == "POST" and formulaire.is_valid():
        fichier = formulaire.cleaned_data["fichier"]
        rapport = deposer_declaration(fichier.read(), fichier.name, membre, request.user, soumettre=False,
                                      motif_portail=formulaire.cleaned_data.get("motif"))
        if rapport.depot_id:
            return redirect("portail:rapport", depot_id=rapport.depot_id)
        # trace impossible (cas limite) : on affiche le rapport sans le persister
        erreurs, alertes = rapport_lisible.traduire_tout(rapport.problemes)
        return render(request, "portail/membre/rapport.html", {
            "membre": membre, "mois": mois, "situation": situation, "depot": None, "resultat": rapport.resultat,
            "erreurs": erreurs, "alertes": alertes, "declaration": None, "page_active": "declarer"})
    mois_ouverts = [formats.premier_du_mois(decalage=-i) for i in range(1, 13)]
    return render(request, "portail/membre/assistant.html", {
        "membre": membre, "mois": mois, "situation": situation, "formulaire": formulaire, "params": params,
        "mois_ouverts": mois_ouverts, "page_active": "declarer",
    })


@membre_requis
def gabarit(request):
    """Téléchargement du gabarit Excel du mois (étape 1)."""
    membre = membre_courant(request)
    mois = _mois_demande(request)
    octets = generer_gabarit(membre, mois)
    version = Declaration.objects.filter(membre=membre, mois=mois).count() + 1
    nom = f"declaration_{membre.code}_{mois:%Y-%m}_v{version}.xlsx"
    reponse = HttpResponse(octets, content_type=TYPE_XLSX)
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    return reponse


@membre_requis
def rapport(request, depot_id):
    """Rapport de contrôle d'un dépôt : quoi / où / comment corriger, puis attestation et soumission."""
    membre = membre_courant(request)
    depot = get_object_or_404(DepotFichier, pk=depot_id, membre=membre)
    params = parametres_publics()
    situation = _situation(membre, depot.mois, params)
    erreurs, alertes = rapport_lisible.traduire_tout((depot.rapport or []))
    declaration = depot.declaration
    if declaration is not None and declaration.statut == "SOUMISE":
        return redirect("portail:confirmation", declaration_id=declaration.id)
    formulaire = None
    if declaration is not None and declaration.statut == "BROUILLON":
        formulaire = FormulaireSoumission(correction=situation["correction"] and not declaration.motif_correction,
                                          initial={"commentaire": declaration.commentaire_portail})
    return render(request, "portail/membre/rapport.html", {
        "membre": membre, "mois": depot.mois, "situation": situation, "depot": depot, "resultat": depot.resultat,
        "erreurs": erreurs, "alertes": alertes, "a_commenter": rapport_lisible.alertes_a_commenter(alertes),
        "declaration": declaration, "formulaire": formulaire, "total": _total_declaration(declaration),
        "nb_lignes": LigneVente.objects.filter(declaration=declaration).count() if declaration else 0,
        "page_active": "declarer",
    })


@membre_requis
@require_POST
def soumettre(request, declaration_id):
    membre = membre_courant(request)
    declaration = get_object_or_404(Declaration, pk=declaration_id, membre=membre)
    if declaration.statut != "BROUILLON":
        messages.info(request, "Cette déclaration a déjà été soumise.")
        return redirect("portail:confirmation", declaration_id=declaration.id)
    situation = _situation(membre, declaration.mois, parametres_publics())
    formulaire = FormulaireSoumission(request.POST, correction=situation["correction"] and not declaration.motif_correction)
    if not formulaire.is_valid():
        depot = DepotFichier.objects.filter(declaration=declaration).order_by("-cree_le").first()
        erreurs, alertes = rapport_lisible.traduire_tout((depot.rapport or []) if depot else [])
        return render(request, "portail/membre/rapport.html", {
            "membre": membre, "mois": declaration.mois, "situation": situation, "depot": depot, "resultat": depot.resultat if depot else None,
            "erreurs": erreurs, "alertes": alertes, "a_commenter": rapport_lisible.alertes_a_commenter(alertes),
            "declaration": declaration, "formulaire": formulaire, "total": _total_declaration(declaration),
            "nb_lignes": LigneVente.objects.filter(declaration=declaration).count(), "page_active": "declarer"}, status=400)
    try:
        soumettre_declaration(declaration.id, membre, attestation=True,
                              motif=formulaire.cleaned_data.get("motif"), commentaire=formulaire.cleaned_data.get("commentaire"))
    except IntegrityError:
        messages.error(request, "La soumission a été refusée par un contrôle de cohérence. Déposez un nouveau fichier.")
        return redirect("portail:assistant")
    return redirect("portail:confirmation", declaration_id=declaration.id)


@membre_requis
def confirmation(request, declaration_id):
    membre = membre_courant(request)
    declaration = get_object_or_404(Declaration, pk=declaration_id, membre=membre)
    return render(request, "portail/membre/confirmation.html", {
        "membre": membre, "declaration": declaration, "total": _total_declaration(declaration),
        "nb_lignes": LigneVente.objects.filter(declaration=declaration).count(),
        "nb_lignes_non_nulles": LigneVente.objects.filter(declaration=declaration, quantite__gt=0).count(),
        "annee": declaration.mois.year, "page_active": "declarer",
    })


# ----------------------------------------------------------------------------------------------- historique
@membre_requis
def historique(request):
    membre = membre_courant(request)
    declarations = Declaration.objects.filter(membre=membre).order_by("-mois", "-version")
    depots = DepotFichier.objects.filter(membre=membre).order_by("-cree_le")[:50]
    return render(request, "portail/membre/historique.html", {
        "membre": membre, "declarations": declarations, "depots": depots, "page_active": "historique"})


# ----------------------------------------------------------------------------------------------- Mon année
def _tableau_annee(membre, annee):
    """Lignes (produit × 12 mois) des déclarations SOUMISES de l'année, totaux mensuels, sous-totaux par marque."""
    declarations = {d.mois.month: d for d in Declaration.objects.filter(membre=membre, mois__year=annee, statut="SOUMISE")}
    ventes = {}
    for produit_id, mois, q in LigneVente.objects.filter(declaration__in=list(declarations.values())).values_list(
            "produit_id", "declaration__mois", "quantite"):
        ventes.setdefault(produit_id, {})[mois.month] = q
    produits = Produit.objects.filter(id__in=list(ventes)).select_related("modele__marque", "energie").order_by(
        "modele__marque__nom", "code")
    lignes, totaux = [], {m: 0 for m in range(1, 13)}
    for p in produits:
        par_mois = ventes.get(p.id, {})
        total = sum(par_mois.values())
        for m, q in par_mois.items():
            totaux[m] += q
        lignes.append({"produit": p, "mois": [par_mois.get(m) for m in range(1, 13)], "total": total,
                       "marque": p.modele.marque.nom if p.modele_id else "—"})
    return declarations, lignes, totaux


@membre_requis
def mon_annee(request):
    membre = membre_courant(request)
    annee = _annee_demandee(request)
    declarations, lignes, totaux = _tableau_annee(membre, annee)
    mois_declares = sorted(declarations)
    total_annee = sum(totaux[m] for m in mois_declares)
    serie = [totaux[m] if m in declarations else None for m in range(1, 13)]
    par_energie = {}
    for l in lignes:
        par_energie[l["produit"].energie.libelle] = par_energie.get(l["produit"].energie.libelle, 0) + l["total"]
    return render(request, "portail/membre/mon_annee.html", {
        "membre": membre, "annee": annee, "annees": list(range(date.today().year - 3, date.today().year + 1)),
        "lignes": lignes, "totaux": totaux, "mois_declares": mois_declares, "total_annee": total_annee,
        "nb_mois": len(mois_declares), "moyenne": round(total_annee / len(mois_declares)) if mois_declares else None,
        "meilleur_mois": max(mois_declares, key=lambda m: totaux[m]) if mois_declares else None,
        "meilleur_mois_libelle": formats.MOIS[max(mois_declares, key=lambda m: totaux[m]) - 1] if mois_declares else "",
        "serie_json": json.dumps(serie), "energies_json": json.dumps(sorted(par_energie.items(), key=lambda x: -x[1])),
        "mois_courts": formats.MOIS_COURTS, "page_active": "mon_annee",
    })


@membre_requis
def export_annee(request):
    membre = membre_courant(request)
    annee = _annee_demandee(request)
    reponse = HttpResponse(exporter_annee_membre(membre, annee), content_type=TYPE_XLSX)
    reponse["Content-Disposition"] = f'attachment; filename="mon_annee_{membre.code}_{annee}.xlsx"'
    return reponse


# ----------------------------------------------------------------------------------------------- Le marché
@membre_requis
def marche(request):
    membre = membre_courant(request)
    annee = _annee_demandee(request)
    publications = _meilleures_publications(annee)
    segmentation = Segmentation.objects.filter(statut="COURANTE").first()
    libelles = _libelles(segmentation.id) if segmentation else {}
    ordre = _ordre_cles(segmentation.id) if segmentation else {}
    cellules = _cellules(publications)
    rang = {"TOTAL": 0, "CATEGORIE": 1, "SEGMENT": 1, "ORIGINE": 2, "ENERGIE": 3}
    cles = sorted({c for m in cellules.values() for c in m},
                  key=lambda k: (rang.get(k[0], 9), ordre.get(k, 9999), libelles.get(k, k[1])))
    lignes = []
    for cle in cles:
        valeurs = []
        for m in range(1, 13):
            cellule = cellules.get(m, {}).get(cle)
            valeurs.append(None if cellule is None else ("c" if cellule[1] else cellule[0]))
        lignes.append({"libelle": libelles.get(cle, cle[1]), "dimension": cle[0], "valeurs": valeurs})
    total_marche = [None if cellules.get(m, {}).get(("TOTAL", "ALL")) is None or cellules[m][("TOTAL", "ALL")][1]
                    else cellules[m][("TOTAL", "ALL")][0] for m in range(1, 13)]
    _, _, mes_totaux = _tableau_annee(membre, annee)
    mes_mois = set(Declaration.objects.filter(membre=membre, mois__year=annee, statut="SOUMISE").values_list("mois__month", flat=True))
    mes_ventes = [mes_totaux[m] if m in mes_mois else None for m in range(1, 13)]
    dernier = max(publications) if publications else None
    return render(request, "portail/membre/marche.html", {
        "membre": membre, "annee": annee, "annees": list(range(date.today().year - 3, date.today().year + 1)),
        "publications": publications, "lignes": lignes, "mois_courts": formats.MOIS_COURTS,
        "dernier_mois": date(annee, dernier, 1) if dernier else None, "derniere": publications.get(dernier) if dernier else None,
        "marche_json": json.dumps(total_marche), "mes_ventes_json": json.dumps(mes_ventes), "page_active": "marche",
    })


# ----------------------------------------------------------------------------------------------- Mes produits
@membre_requis
def mes_produits(request):
    membre = membre_courant(request)
    marques = srv_produits.marques_du_membre(membre)
    actifs = Produit.objects.filter(statut="ACTIF", modele__marque__in=marques).select_related("modele__marque", "energie").order_by(
        "modele__marque__nom", "code")
    masques = set(ProduitMembre.objects.filter(membre=membre, etat="MASQUE").values_list("produit_id", flat=True))
    proposes = Produit.objects.filter(statut="PROPOSE", propose_par=membre).select_related("modele__marque", "energie").order_by("-cree_le")
    formulaire = FormulaireProposition(request.POST or None, marques=marques)
    if request.method == "POST" and formulaire.is_valid():
        d = formulaire.cleaned_data
        try:
            produit, proche = srv_produits.proposer_produit(
                membre, d["marque"], d["modele"], d["finition"], d["energie"], boite=d.get("boite"), motricite=d.get("motricite") or "",
                segment=d.get("segment") or "", note=d.get("note") or "", cylindree=d.get("cylindree"), puissance=d.get("puissance"),
                charge=d.get("charge"), ptac=d.get("ptac"), places=d.get("places"))
        except srv_produits.PropositionRefusee as e:
            formulaire.add_error(None, str(e))
        else:
            messages.success(request, f"Proposition enregistrée : {produit.libelle_affiche}. Le GIPAME la validera avant de l'ajouter à votre gabarit.")
            if proche:
                messages.info(request, f"Un produit proche existe déjà ({proche.libelle_affiche}) : le GIPAME vérifiera qu'il ne s'agit pas d'un doublon.")
            return redirect("portail:mes_produits")
    return render(request, "portail/membre/mes_produits.html", {
        "membre": membre, "actifs": actifs, "masques": masques, "proposes": proposes, "formulaire": formulaire,
        "nb_affiches": sum(1 for p in actifs if p.id not in masques), "page_active": "mes_produits",
    })


@membre_requis
@require_POST
def changer_affichage(request, produit_id):
    membre = membre_courant(request)
    masquer = request.POST.get("action") == "masquer"
    produit = get_object_or_404(Produit, pk=produit_id, statut="ACTIF", modele__marque__in=srv_produits.marques_du_membre(membre))
    srv_produits.changer_affichage(membre, produit.id, masquer, motif=request.POST.get("motif", "")[:200])
    messages.success(request, f"{produit.libelle_affiche} : {'retiré de' if masquer else 'remis dans'} votre gabarit.")
    return redirect("portail:mes_produits")
