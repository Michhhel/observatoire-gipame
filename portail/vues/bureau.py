"""Écrans du bureau : tableau de bord du marché publié et approbation des accès exceptionnels.
Le bureau voit les totaux publiés (jamais une donnée individuelle, ni le nombre de contributeurs,
ni le motif d'un masquage) ; il approuve ou refuse les demandes d'accès au nom de son poste.
"""
import json
from datetime import date

from django import forms
from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from collecte.excel.exports import _cellules, _libelles, _meilleures_publications, _ordre_cles
from collecte.models import (ApprobationAcces, DemandeAccesExceptionnel, JournalAcces, Membre, ProfilUtilisateur,
                             Segmentation, TitulairePoste)

from .. import formats
from ..acces import bureau_requis


def _annee(request):
    try:
        return int(request.GET.get("annee") or date.today().year)
    except ValueError:
        return date.today().year


def _tableau_marche(annee):
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
        valeurs = [None if cellules.get(m, {}).get(cle) is None else ("c" if cellules[m][cle][1] else cellules[m][cle][0])
                   for m in range(1, 13)]
        lignes.append({"libelle": libelles.get(cle, cle[1]), "dimension": cle[0], "valeurs": valeurs})
    total = [None if cellules.get(m, {}).get(("TOTAL", "ALL")) is None or cellules[m][("TOTAL", "ALL")][1]
             else cellules[m][("TOTAL", "ALL")][0] for m in range(1, 13)]
    return publications, lignes, total


@bureau_requis
def tableau(request):
    annee = _annee(request)
    publications, lignes, total = _tableau_marche(annee)
    dernier = max(publications) if publications else None
    derniere = publications.get(dernier) if dernier else None
    total_dernier = total[dernier - 1] if dernier else None
    total_prec = total[dernier - 2] if dernier and dernier > 1 else None
    cumul = sum(t for t in total if t is not None)
    en_attente = DemandeAccesExceptionnel.objects.filter(approbations__isnull=True).count()
    return render(request, "portail/bureau/tableau.html", {
        "annee": annee, "annees": list(range(date.today().year - 3, date.today().year + 1)), "lignes": lignes,
        "mois_courts": formats.MOIS_COURTS, "dernier_mois": date(annee, dernier, 1) if dernier else None, "derniere": derniere,
        "total_dernier": total_dernier, "total_prec": total_prec,
        "tendance": round((total_dernier - total_prec) / total_prec * 100, 1) if total_dernier is not None and total_prec else None,
        "cumul": cumul, "nb_mois_publies": len(publications), "total_json": json.dumps(total),
        "nb_membres": Membre.objects.filter(famille="VEHICULES").count(), "en_attente": en_attente, "page_active": "bureau_tableau",
    })


class FormulaireApprobation(forms.Form):
    decision = forms.ChoiceField(choices=[("APPROUVEE", "J'approuve cet accès"), ("REFUSEE", "Je refuse")], widget=forms.RadioSelect)
    commentaire = forms.CharField(required=False, max_length=500, label="Commentaire (facultatif)", widget=forms.Textarea(attrs={"rows": 2}))


def _poste_du(utilisateur):
    aujourd_hui = date.today()
    t = TitulairePoste.objects.filter(utilisateur=utilisateur, date_debut__lte=aujourd_hui).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=aujourd_hui)).select_related("poste").first()
    return t.poste if t else None


@bureau_requis
def approbations(request):
    poste = _poste_du(request.user)
    demandes = list(DemandeAccesExceptionnel.objects.select_related("membre_cible").prefetch_related("approbations__poste").order_by("-cree_le")[:50])
    profils = {p.id: p for p in ProfilUtilisateur.objects.filter(id__in={d.demandeur_id for d in demandes})}
    liste = []
    for d in demandes:
        d.profil_demandeur = profils.get(d.demandeur_id)
        mes = [a for a in d.approbations.all() if poste and a.poste_id == poste.id]
        accords = [a for a in d.approbations.all() if a.decision == "APPROUVEE"]
        liste.append({"demande": d, "deja": mes[0] if mes else None, "nb_accords": len(accords),
                      "refus": any(a.decision == "REFUSEE" for a in d.approbations.all())})
    return render(request, "portail/bureau/approbations.html", {"poste": poste, "liste": liste, "page_active": "bureau_approbations"})


@bureau_requis
def approbation(request, demande_id):
    demande = get_object_or_404(DemandeAccesExceptionnel.objects.select_related("membre_cible"), pk=demande_id)
    demande.profil_demandeur = ProfilUtilisateur.objects.filter(pk=demande.demandeur_id).first()
    poste = _poste_du(request.user)
    deja = ApprobationAcces.objects.filter(demande=demande, poste=poste).first() if poste else None
    formulaire = FormulaireApprobation(request.POST or None)
    if request.method == "POST" and poste and not deja and formulaire.is_valid():
        try:
            ApprobationAcces.objects.create(demande=demande, poste=poste, approbateur=request.user,
                                            decision=formulaire.cleaned_data["decision"], commentaire=formulaire.cleaned_data["commentaire"])
        except IntegrityError:
            messages.error(request, "La décision n'a pas pu être enregistrée (poste déjà prononcé ou règle de la base).")
        else:
            messages.success(request, "Décision enregistrée au nom du poste " + poste.libelle + ".")
        return redirect("portail:bureau_approbations")
    return render(request, "portail/bureau/approbation.html", {
        "demande": demande, "poste": poste, "deja": deja, "formulaire": formulaire,
        "approbations": demande.approbations.select_related("poste").order_by("decide_le"), "page_active": "bureau_approbations"})


LIBELLES_JOURNAL = {
    "LECTURE_EXCEPTIONNELLE": "Lecture de données individuelles",
    "COMPTE_CREE": "Compte créé", "COMPTE_MODIFIE": "Compte modifié", "COMPTE_DESACTIVE": "Compte désactivé",
    "COMPTE_REACTIVE": "Compte réactivé", "LIEN_ACTIVATION": "Lien d'activation régénéré",
    "RAPPELS_PREPARES": "Rappels de dépôt envoyés",
}


def _date_iso(texte):
    try:
        return date.fromisoformat(texte)
    except (TypeError, ValueError):
        return None


@bureau_requis
def journal(request):
    """Rapport mensuel des accès (§15, P0.4) : qui a lu des données individuelles, quels comptes ont été créés ou
    désactivés, quand les rappels sont partis. Aucune quantité : seulement des faits et des volumes de lignes."""
    mois_possibles = [formats.premier_du_mois(decalage=d) for d in range(0, -12, -1)]
    try:
        a, m = (int(x) for x in request.GET.get("mois", "").split("-"))
        mois = date(a, m, 1) if date(a, m, 1) in mois_possibles else mois_possibles[0]
    except ValueError:
        mois = mois_possibles[0]
    fin = formats.premier_du_mois(mois, decalage=1)
    entrees = list(JournalAcces.objects.filter(cree_le__date__gte=mois, cree_le__date__lt=fin).order_by("-cree_le"))
    ids = {e.utilisateur_id for e in entrees} | {e.details.get("par") for e in entrees}
    noms = {p.id: (f"{p.first_name} {p.last_name}".strip() or p.email)
            for p in ProfilUtilisateur.objects.filter(id__in=[i for i in ids if i])}
    societes = dict(Membre.objects.values_list("id", "raison_sociale"))
    lignes = []
    for e in entrees:
        d = e.details or {}
        if e.action == "LECTURE_EXCEPTIONNELLE":
            par = noms.get(e.utilisateur_id, "—")
            debut, fin_p = _date_iso(d.get("mois_debut")), _date_iso(d.get("mois_fin"))
            periode = formats.mois_court(debut) + ("" if debut == fin_p else f" → {formats.mois_court(fin_p)}")
            objet = f"{societes.get(d.get('membre_cible_id'), 'Tous les membres')} · {periode} · {e.nb_lignes} ligne(s) lue(s)"
        elif e.action == "RAPPELS_PREPARES":
            par = noms.get(e.utilisateur_id, "Envoi automatique")
            objet = f"Mois {formats.de_mois(_date_iso(d.get('mois')))} · {e.nb_lignes} membre(s) relancé(s)"
        else:
            par = noms.get(d.get("par"), "Administrateur (installation)")
            objet = d.get("email", "") + (f" · motif : {d['motif']}" if d.get("motif") else "")
        lignes.append({"quand": e.cree_le, "action": e.action, "libelle": LIBELLES_JOURNAL.get(e.action, e.action),
                       "par": par, "objet": objet, "demande": e.demande_id})
    return render(request, "portail/bureau/journal.html", {
        "mois": mois, "mois_possibles": mois_possibles, "lignes": lignes,
        "nb_lectures": sum(l["action"] == "LECTURE_EXCEPTIONNELLE" for l in lignes),
        "nb_comptes": sum(l["action"].startswith("COMPTE") for l in lignes),
        "page_active": "bureau_journal"})
