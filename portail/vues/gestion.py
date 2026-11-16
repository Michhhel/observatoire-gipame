"""Écrans de la gestion (secrétariat) : suivi des dépôts, file de validation des produits proposés,
catalogue, demandes d'accès exceptionnel. La gestion ne voit jamais une quantité individuelle (§6.4) :
ces vues ne lisent que des statuts, des dates et le catalogue.
"""
from datetime import date

from django import forms
from django.contrib import messages
from django.db import DatabaseError, connection, transaction
from django.views.decorators.cache import never_cache
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from collecte import gestion as srv
from collecte import rappels
from collecte.models import (ApprobationAcces, DemandeAccesExceptionnel, JournalAcces, Membre, Produit, Publication,
                             Segment)

from .. import formats
from ..acces import gestion_requise


def _suivi():
    """Lignes de la vue collecte_v_suivi_depots (13 mois × membres attendus)."""
    with connection.cursor() as cur:
        cur.execute("SELECT membre_id, membre_code, mois, statut_depot, version, soumise_le, date_limite, en_retard "
                    "FROM collecte_v_suivi_depots ORDER BY membre_code, mois")
        colonnes = [c[0] for c in cur.description]
        return [dict(zip(colonnes, ligne)) for ligne in cur.fetchall()]


@gestion_requise
def tableau(request):
    lignes = _suivi()
    noms = {m.id: m.raison_sociale for m in Membre.objects.all()}
    mois = sorted({l["mois"] for l in lignes})[-7:]  # 6 derniers mois clos + mois courant
    par_membre = {}
    for l in lignes:
        if l["mois"] in mois:
            par_membre.setdefault((l["membre_code"], l["membre_id"]), {})[l["mois"]] = l
    mois_cle = formats.premier_du_mois(decalage=-1)
    attendus = [l for l in lignes if l["mois"] == mois_cle]
    recus = [l for l in attendus if l["statut_depot"] == "SOUMISE"]
    en_retard = [l for l in attendus if l["en_retard"]]
    propositions = Produit.objects.filter(statut="PROPOSE").count()
    dernier_rappel = (JournalAcces.objects.filter(action="RAPPELS_PREPARES", details__mois=mois_cle.isoformat())
                      .order_by("-cree_le").values_list("cree_le", flat=True).first())
    return render(request, "portail/gestion/tableau.html", {
        "dernier_rappel": dernier_rappel,
        "mois": mois, "mois_cle": mois_cle, "par_membre": sorted(par_membre.items()), "noms": noms,
        "nb_attendus": len(attendus), "nb_recus": len(recus), "nb_retard": len(en_retard), "nb_propositions": propositions,
        "date_limite": attendus[0]["date_limite"] if attendus else None, "page_active": "gestion_tableau",
    })


class FormulaireDecision(forms.Form):
    decision = forms.ChoiceField(choices=[("VALIDER", "Valider"), ("FUSIONNER", "Fusionner"), ("REJETER", "Rejeter")], widget=forms.RadioSelect, initial="VALIDER")
    segment = forms.ModelChoiceField(queryset=Segment.objects.none(), required=False, label="Segment de la grille")
    nom_modele = forms.CharField(required=False, max_length=120, label="Modèle (corrigé si besoin)")
    finition = forms.CharField(required=False, max_length=120, label="Version / finition (corrigée si besoin)")
    cible = forms.ModelChoiceField(queryset=Produit.objects.none(), required=False, label="Produit existant équivalent")
    motif = forms.CharField(required=False, max_length=500, label="Motif / note", widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["segment"].queryset = srv.segments_courants()
        self.fields["cible"].queryset = Produit.objects.filter(statut__in=["ACTIF", "ARCHIVE"]).order_by("code")

    def clean(self):
        d = super().clean()
        if d.get("decision") == "VALIDER" and not d.get("segment"):
            self.add_error("segment", "Choisissez le segment dans lequel classer ce produit.")
        if d.get("decision") == "FUSIONNER" and not d.get("cible"):
            self.add_error("cible", "Indiquez le produit existant vers lequel fusionner.")
        if d.get("decision") == "REJETER" and not (d.get("motif") or "").strip():
            self.add_error("motif", "Un motif est obligatoire pour rejeter.")
        return d


@gestion_requise
def propositions(request):
    en_attente = Produit.objects.filter(statut="PROPOSE").select_related(
        "propose_par", "marque_proposee", "modele__marque", "energie", "boite").order_by("cree_le")  # propose_par : un Membre
    traitees = Produit.objects.filter(statut__in=["FUSIONNE", "REJETE"]).order_by("-decide_le")[:20]
    recentes = Produit.objects.filter(statut="ACTIF", propose_par__isnull=False).order_by("-decide_le")[:20]
    return render(request, "portail/gestion/propositions.html", {
        "en_attente": en_attente, "traitees": traitees, "recentes": recentes, "page_active": "gestion_propositions"})


@gestion_requise
def proposition(request, produit_id):
    produit = get_object_or_404(Produit, pk=produit_id)
    marque = produit.modele.marque if produit.modele_id else produit.marque_proposee
    nom_modele = produit.modele.nom if produit.modele_id else produit.modele_propose
    proches = Produit.objects.filter(statut__in=["ACTIF", "ARCHIVE"], modele__marque=marque).select_related("modele").order_by("code")[:200]
    formulaire = FormulaireDecision(request.POST or None, initial={"nom_modele": nom_modele, "finition": produit.finition})
    if request.method == "POST" and produit.statut == "PROPOSE" and formulaire.is_valid():
        d = formulaire.cleaned_data
        try:
            if d["decision"] == "VALIDER":
                p = srv.valider_proposition(produit.id, request.user, d["segment"], d.get("nom_modele"), d.get("finition"), d.get("motif"))
                messages.success(request, f"Produit validé : {p.code} {p.libelle_affiche}. Il apparaîtra dans les prochains gabarits.")
            elif d["decision"] == "FUSIONNER":
                srv.fusionner_proposition(produit.id, d["cible"].id, request.user, d.get("motif"))
                messages.success(request, f"Proposition fusionnée vers {d['cible'].code} {d['cible'].libelle_affiche}.")
            else:
                srv.rejeter_proposition(produit.id, request.user, d.get("motif"))
                messages.success(request, "Proposition rejetée ; le motif est conservé.")
        except srv.DecisionImpossible as e:
            formulaire.add_error(None, str(e))
        else:
            return redirect("portail:gestion_propositions")
    return render(request, "portail/gestion/proposition.html", {
        "produit": produit, "marque": marque, "nom_modele": nom_modele, "proches": proches, "formulaire": formulaire,
        "page_active": "gestion_propositions"})


@gestion_requise
def catalogue(request):
    recherche = (request.GET.get("q") or "").strip()
    produits = Produit.objects.filter(statut__in=["ACTIF", "ARCHIVE"]).select_related("modele__marque", "energie").order_by("modele__marque__nom", "code")
    if recherche:
        from django.db.models import Q
        produits = produits.filter(Q(code__icontains=recherche) | Q(libelle_affiche__icontains=recherche) | Q(modele__marque__nom__icontains=recherche))
    return render(request, "portail/gestion/catalogue.html", {
        "produits": produits[:500], "nb": produits.count(), "recherche": recherche, "page_active": "gestion_catalogue"})


class FormulaireDemandeAcces(forms.Form):
    membre_cible = forms.ModelChoiceField(queryset=Membre.objects.order_by("code"), label="Membre concerné", required=False,
                                          empty_label="Tous les membres (à éviter)")
    mois_debut = forms.DateField(label="Premier mois", input_formats=["%Y-%m-%d", "%Y-%m"], widget=forms.DateInput(attrs={"type": "month"}))
    mois_fin = forms.DateField(label="Dernier mois", input_formats=["%Y-%m-%d", "%Y-%m"], widget=forms.DateInput(attrs={"type": "month"}))
    duree_minutes = forms.IntegerField(label="Durée de la fenêtre (minutes)", min_value=15, max_value=240, initial=60)
    motif = forms.CharField(label="Motif précis (il sera lu par le bureau)", max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))

    def clean(self):
        d = super().clean()
        for champ in ("mois_debut", "mois_fin"):
            if d.get(champ):
                d[champ] = d[champ].replace(day=1)
        if d.get("mois_debut") and d.get("mois_fin") and d["mois_fin"] < d["mois_debut"]:
            self.add_error("mois_fin", "Le dernier mois doit être postérieur ou égal au premier.")
        return d


@gestion_requise
def demandes_acces(request):
    formulaire = FormulaireDemandeAcces(request.POST or None)
    if request.method == "POST" and formulaire.is_valid():
        d = formulaire.cleaned_data
        srv.creer_demande_acces(request.user, d["motif"], d.get("membre_cible"), d["mois_debut"], d["mois_fin"], d["duree_minutes"])
        messages.success(request, "Demande enregistrée. Elle sera visible par le bureau pour approbation.")
        return redirect("portail:gestion_demandes")
    demandes = DemandeAccesExceptionnel.objects.filter(demandeur_id=request.user.id).order_by("-cree_le")[:30]
    return render(request, "portail/gestion/demandes_acces.html", {
        "formulaire": formulaire, "demandes": demandes, "page_active": "gestion_demandes"})


@gestion_requise
@never_cache
def lecture_acces(request, demande_id):
    """Lecture des données individuelles d'une demande approuvée (décision du 11/11/2026).

    Seul le demandeur peut lire ; c'est la fonction SQL gipame_lecture_exceptionnelle qui vérifie l'accord
    (seuil de postes), la fenêtre de temps et journalise CHAQUE lecture. La lecture est déclenchée par un POST
    (jamais par un simple affichage ou un rechargement) ; aucun export n'est proposé ; la page n'est pas mise
    en cache. Le refus éventuel de la base (accord insuffisant, accès expiré) est affiché tel quel.
    """
    demande = get_object_or_404(DemandeAccesExceptionnel.objects.select_related("membre_cible"), pk=demande_id,
                                demandeur_id=request.user.id)
    approbations = ApprobationAcces.objects.filter(demande=demande).select_related("poste").order_by("decide_le")
    lignes, refus = None, None
    if request.method == "POST":
        try:
            with transaction.atomic():  # point de sauvegarde : un refus de la base n'interrompt pas la requête
                with connection.cursor() as cur:
                    cur.execute("SELECT r_membre_code, r_mois, r_produit_code, r_quantite "
                                "FROM gipame_lecture_exceptionnelle(%s)", [demande.id])
                    brutes = cur.fetchall()
        except DatabaseError as e:
            refus = str(getattr(e, "__cause__", None) or e).split("\n")[0].replace("CONTEXT:", "").strip()
        else:
            libelles = dict(Produit.objects.filter(code__in={b[2] for b in brutes}).values_list("code", "libelle_affiche"))
            lignes = [{"membre": b[0], "mois": b[1], "code": b[2], "libelle": libelles.get(b[2], ""), "quantite": b[3]}
                      for b in brutes]
    return render(request, "portail/gestion/lecture_acces.html", {
        "demande": demande, "approbations": approbations, "lignes": lignes, "refus": refus,
        "page_active": "gestion_demandes"})


def _mois_depuis_formulaire(request, mois_valides):
    try:
        a, m = (int(x) for x in request.POST.get("mois", "").split("-"))
        mois = date(a, m, 1)
    except (ValueError, TypeError):
        return None
    return mois if mois in mois_valides else None


@gestion_requise
@require_POST
def envoyer_rappels(request):
    """Un rappel par destinataire, pour les membres attendus qui n'ont pas soumis le mois choisi."""
    mois_valides = {formats.premier_du_mois(decalage=d) for d in range(-12, 1)}
    mois = _mois_depuis_formulaire(request, mois_valides)
    if mois is None:
        messages.error(request, "Mois invalide.")
        return redirect("portail:gestion_tableau")
    bilan = rappels.envoyer_rappels(mois)
    if not bilan["membres"]:
        messages.success(request, f"Tous les membres attendus ont déclaré le mois {formats.de_mois(mois)} : aucun rappel à envoyer.")
    else:
        messages.success(request, f"{bilan['envoyes']} rappel(s) envoyé(s) pour {bilan['membres']} membre(s) "
                                  f"qui n'ont pas encore déclaré le mois {formats.de_mois(mois)}.")
    if bilan["sans_compte"]:
        messages.warning(request, "Sans compte actif, à relancer par téléphone : " + ", ".join(bilan["sans_compte"]) + ".")
    if bilan["echecs"]:
        messages.error(request, "Envoi impossible vers : " + ", ".join(bilan["echecs"]) + ". Vérifiez l'adresse ou la messagerie.")
    return redirect("portail:gestion_tableau")


@gestion_requise
def publications(request):
    """Calcul et publication des totaux de marché d'un mois clos. La gestion déclenche le calcul mais n'en voit
    que le résumé (couverture, version) : les totaux se consultent dans « Le marché » (membres) et chez le bureau."""
    mois_clos = [formats.premier_du_mois(decalage=d) for d in range(-1, -13, -1)]
    if request.method == "POST":
        mois = _mois_depuis_formulaire(request, set(mois_clos))
        definitive = request.POST.get("action") == "definitive"
        if mois is None:
            messages.error(request, "Mois invalide.")
        elif definitive and request.POST.get("confirmation") != "oui":
            messages.error(request, "Cochez la case de confirmation pour publier en définitif.")
        else:
            try:
                with transaction.atomic():
                    r = rappels.publier(mois, definitive=definitive)
            except ValueError as e:
                messages.error(request, f"Publication {formats.de_mois(mois)} impossible : {e}.")
            else:
                messages.success(request, f"Publication {formats.de_mois(mois)} calculée : {r['statut'].lower()}, version {r['version']}, "
                                          f"couverture {formats.pourcentage(r['couverture'])} ({r['declarants']}/{r['attendus']} membres).")
        return redirect("portail:gestion_publications")
    suivi = _suivi()
    derniere = {}
    for p in Publication.objects.filter(mois__in=mois_clos).only("mois", "statut", "version", "calculee_le",
                                                                 "couverture_pct").order_by("mois", "version"):
        derniere[p.mois] = p
    lignes = []
    for m in mois_clos:
        du_mois = [l for l in suivi if l["mois"] == m]
        lignes.append({"mois": m, "attendus": len(du_mois), "recus": sum(l["statut_depot"] == "SOUMISE" for l in du_mois),
                       "publication": derniere.get(m)})
    seuil = dict(srv.parametres_publication())
    return render(request, "portail/gestion/publications.html", {
        "lignes": lignes, "seuil_couverture": seuil.get("couverture_min_publication_pct", "80"),
        "page_active": "gestion_publications"})
