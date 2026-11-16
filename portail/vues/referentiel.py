"""Écrans « Membres » de la gestion : qui déclare, depuis quand, quelles marques. Aucune donnée de vente ici.
Les règles (pas de chevauchement, codes immuables, rien ne se supprime) sont dans la base ; ces vues ne font que
présenter les formulaires et traduire les refus en messages."""
from datetime import date

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from collecte import referentiel as srv
from collecte.models import Concession, GroupeEconomique, Marque, Membre, Origine, PeriodeAdhesion, ProfilUtilisateur

from .. import formats
from ..acces import gestion_requise


class ChampMois(forms.CharField):
    """Saisie « AAAA-MM » (sélecteur de mois du navigateur) → date du 1er du mois."""
    widget = forms.TextInput(attrs={"type": "month", "placeholder": "AAAA-MM"})

    def clean(self, valeur):
        valeur = super().clean(valeur)
        if not valeur:
            return None
        try:
            a, m = (int(x) for x in valeur.split("-")[:2])
            return date(a, m, 1)
        except ValueError:
            raise forms.ValidationError("Indiquez un mois au format AAAA-MM.")


class FormulaireMembre(forms.Form):
    code = forms.CharField(max_length=20, label="Code du membre",
                           help_text="Court et définitif (ex. CFAO, SAMAD) : il ne pourra plus être modifié.")
    raison_sociale = forms.CharField(max_length=200, label="Raison sociale")
    groupe = forms.CharField(max_length=150, required=False, label="Groupe économique (facultatif)",
                             help_text="Les sociétés d'un même groupe comptent pour un seul contributeur dans les règles de confidentialité.")
    debut = ChampMois(label="Premier mois à déclarer")
    marques = forms.ModelMultipleChoiceField(queryset=Marque.objects.none(), required=False, label="Marques distribuées",
                                             widget=forms.CheckboxSelectMultiple)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["marques"].queryset = Marque.objects.order_by("nom")
        self.fields["debut"].initial = f"{formats.premier_du_mois():%Y-%m}"


class FormulaireMarque(forms.Form):
    code = forms.CharField(max_length=30, label="Code de la marque", help_text="Ex. TOYOTA. Définitif.")
    nom = forms.CharField(max_length=100, label="Nom affiché")
    origine = forms.ModelChoiceField(queryset=Origine.objects.none(), label="Origine")

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["origine"].queryset = Origine.objects.order_by("ordre")


def _groupes_datalist():
    return GroupeEconomique.objects.order_by("nom").values_list("nom", flat=True)


@gestion_requise
def membres(request):
    aujourd_hui = date.today()
    liste = list(Membre.objects.select_related("groupe").order_by("code"))
    en_cours = {p.membre_id: p for p in PeriodeAdhesion.objects.filter(date_debut__lte=aujourd_hui).exclude(date_fin__lt=aujourd_hui)}
    marques = {}
    for c in Concession.objects.select_related("marque").exclude(date_fin__lt=aujourd_hui).order_by("marque__nom"):
        marques.setdefault(c.membre_id, []).append(c.marque.nom)
    comptes = {}
    for p in ProfilUtilisateur.objects.filter(role_metier="MEMBRE", is_active=True):
        comptes[p.membre_id] = comptes.get(p.membre_id, 0) + 1
    lignes = [{"m": m, "adhesion": en_cours.get(m.id), "marques": marques.get(m.id, []), "comptes": comptes.get(m.id, 0)}
              for m in liste]
    return render(request, "portail/gestion/membres.html", {"lignes": lignes, "page_active": "gestion_membres"})


@gestion_requise
def membre_nouveau(request):
    formulaire = FormulaireMembre(request.POST or None)
    if request.method == "POST" and formulaire.is_valid():
        d = formulaire.cleaned_data
        try:
            membre = srv.creer_membre(d["code"], d["raison_sociale"], d["groupe"], d["debut"], d["marques"])
        except srv.ReferentielInvalide as e:
            formulaire.add_error(None, str(e))
        else:
            messages.success(request, f"{membre.raison_sociale} est enregistré : il devra déclarer à partir {formats.de_mois(d['debut'])}. "
                                      "Créez maintenant le compte de son déclarant (menu Comptes).")
            return redirect("portail:gestion_membre", membre_id=membre.id)
    return render(request, "portail/gestion/membre_nouveau.html", {
        "formulaire": formulaire, "groupes": _groupes_datalist(), "page_active": "gestion_membres"})


@gestion_requise
def membre(request, membre_id):
    m = get_object_or_404(Membre.objects.select_related("groupe"), pk=membre_id)
    return render(request, "portail/gestion/membre.html", {
        "m": m, "periodes": m.periodes.order_by("-date_debut"),
        "concessions": m.concessions.select_related("marque__origine").order_by("date_fin", "marque__nom"),
        "marques": Marque.objects.order_by("nom"), "groupes": _groupes_datalist(),
        "formulaire_marque": FormulaireMarque(), "mois_courant": f"{formats.premier_du_mois():%Y-%m}",
        "comptes": ProfilUtilisateur.objects.filter(membre_id=m.id).order_by("-is_active", "email"),
        "page_active": "gestion_membres"})


@gestion_requise
@require_POST
def membre_action(request, membre_id):
    m = get_object_or_404(Membre, pk=membre_id)
    action = request.POST.get("action")
    try:
        mois = ChampMois(required=False).clean(request.POST.get("mois"))
        if action == "modifier":
            srv.modifier_membre(m, request.POST.get("raison_sociale"), request.POST.get("groupe"))
            messages.success(request, "Fiche mise à jour.")
        elif action in {"clore_adhesion", "ouvrir_adhesion", "ajouter_concession", "clore_concession"} and not mois:
            raise srv.ReferentielInvalide("Indiquez le mois.")
        elif action == "clore_adhesion":
            srv.clore_adhesion(get_object_or_404(PeriodeAdhesion, pk=request.POST.get("periode"), membre=m), mois)
            messages.success(request, f"Adhésion close : dernier mois à déclarer, {formats.mois_long(mois)}.")
        elif action == "ouvrir_adhesion":
            srv.ouvrir_adhesion(m, mois)
            messages.success(request, f"Nouvelle période d'adhésion à partir {formats.de_mois(mois)}.")
        elif action == "ajouter_concession":
            srv.ajouter_concession(m, get_object_or_404(Marque, pk=request.POST.get("marque")), mois)
            messages.success(request, "Marque ajoutée : elle apparaîtra dans les prochains gabarits du membre.")
        elif action == "clore_concession":
            srv.clore_concession(get_object_or_404(Concession, pk=request.POST.get("concession"), membre=m), mois)
            messages.success(request, f"Marque retirée après {formats.mois_long(mois)}.")
        elif action == "creer_marque":
            f = FormulaireMarque(request.POST)
            if not f.is_valid():
                raise srv.ReferentielInvalide("Marque : code, nom et origine sont obligatoires.")
            marque = srv.creer_marque(f.cleaned_data["code"], f.cleaned_data["nom"], f.cleaned_data["origine"])
            messages.success(request, f"Marque {marque.nom} créée : vous pouvez maintenant l'ajouter au membre.")
        else:
            raise srv.ReferentielInvalide("Action inconnue.")
    except (srv.ReferentielInvalide, forms.ValidationError) as e:
        messages.error(request, e.messages[0] if isinstance(e, forms.ValidationError) else str(e))
    return redirect("portail:gestion_membre", membre_id=m.id)
