"""Écran « Comptes » de l'administrateur du GIPAME (rôle TECHNIQUE) : créer un compte, envoyer ou afficher
le lien d'activation, modifier, désactiver / réactiver. Tout passe par collecte.comptes (fonctions SQL à
privilège défini) : le portail ne touche jamais la table des comptes.
"""
from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from collecte import comptes
from collecte.models import Membre, Poste, ProfilUtilisateur

from .. import demo
from ..acces import technique_requis

ROLES = [("MEMBRE", "Membre — déclare et consulte pour sa société"), ("GESTION", "Gestion — secrétariat du GIPAME"),
         ("BUREAU", "Bureau — approuve les accès exceptionnels"), ("TECHNIQUE", "Administrateur de l'Observatoire")]


class FormulaireCompte(forms.Form):
    email = forms.EmailField(label="Adresse e-mail (identifiant)", widget=forms.EmailInput(attrs={"placeholder": "prenom.nom@societe.ci", "autocomplete": "off"}))
    prenom = forms.CharField(label="Prénom", max_length=150, required=False)
    nom = forms.CharField(label="Nom", max_length=150, required=False)
    role = forms.ChoiceField(label="Rôle", choices=ROLES, widget=forms.RadioSelect, initial="MEMBRE")
    membre = forms.ModelChoiceField(label="Société (pour un compte Membre)", queryset=Membre.objects.order_by("code"), required=False, empty_label="—")
    poste = forms.ModelChoiceField(label="Poste tenu (pour un compte Bureau)", queryset=Poste.objects.order_by("code"), required=False, empty_label="Autre / aucun")
    envoyer = forms.BooleanField(label="Envoyer le lien d'activation par e-mail", required=False, initial=True)

    def clean(self):
        d = super().clean()
        if d.get("role") == "MEMBRE" and not d.get("membre"):
            self.add_error("membre", "Choisissez la société de ce membre.")
        if d.get("role") != "MEMBRE" and d.get("membre"):
            self.add_error("membre", "Seul un compte Membre est rattaché à une société.")
        if d.get("poste") and d.get("role") != "BUREAU":
            self.add_error("poste", "Seul un compte Bureau tient un poste.")
        return d


class FormulaireModification(forms.Form):
    email = forms.EmailField(label="Adresse e-mail (identifiant)")
    prenom = forms.CharField(label="Prénom", max_length=150, required=False)
    nom = forms.CharField(label="Nom", max_length=150, required=False)


@technique_requis
def comptes_liste(request):
    formulaire = FormulaireCompte(request.POST or None)
    if request.method == "POST" and formulaire.is_valid():
        d = formulaire.cleaned_data
        try:
            identifiant, lien = comptes.creer(d["email"], d["prenom"], d["nom"], d["role"],
                                              d["membre"].id if d.get("membre") else None, d["poste"].code if d.get("poste") else None)
        except comptes.OperationRefusee as e:
            formulaire.add_error(None, str(e))
        else:
            if d["envoyer"]:
                comptes.envoyer_activation(d["email"].lower(), lien, d["prenom"], d["membre"].raison_sociale if d.get("membre") else "")
                messages.success(request, f"Compte créé et lien d'activation envoyé à {d['email'].lower()} (valable 24 h).")
                return redirect("portail:admin_comptes")
            request.session["lien_activation"] = {"id": identifiant, "email": d["email"].lower(), "lien": lien}
            return redirect("portail:admin_compte", compte_id=identifiant)
    profils = comptes.profils()
    filtre = request.GET.get("filtre", "")
    if filtre == "inactifs":
        profils = profils.filter(is_active=False)
    elif filtre == "non_actives":
        profils = profils.filter(is_active=True, compte_active=False)
    elif filtre in {"MEMBRE", "GESTION", "BUREAU", "TECHNIQUE"}:
        profils = profils.filter(role_metier=filtre)
    return render(request, "portail/administration/comptes.html", {
        "profils": profils, "formulaire": formulaire, "filtre": filtre, "nb_total": ProfilUtilisateur.objects.count(),
        "nb_non_actives": ProfilUtilisateur.objects.filter(is_active=True, compte_active=False).count(), "page_active": "admin_comptes"})


@technique_requis
def compte(request, compte_id):
    profil = get_object_or_404(ProfilUtilisateur.objects.select_related("membre"), pk=compte_id)
    lien = request.session.pop("lien_activation", None)
    if lien and lien.get("id") != profil.id:
        lien = None
    formulaire = FormulaireModification(request.POST or None, initial={"email": profil.email, "prenom": profil.first_name, "nom": profil.last_name})
    if request.method == "POST" and demo.compte_protege(profil.email or profil.username):
        formulaire.add_error(None, "Démonstration : les comptes de démonstration ne peuvent pas être modifiés. "
                                   "Créez un nouveau compte pour essayer la modification.")
    elif request.method == "POST" and formulaire.is_valid():
        d = formulaire.cleaned_data
        try:
            comptes.modifier(profil.id, d["email"], d["prenom"], d["nom"])
        except comptes.OperationRefusee as e:
            formulaire.add_error(None, str(e))
        else:
            messages.success(request, "Compte mis à jour.")
            return redirect("portail:admin_compte", compte_id=profil.id)
    return render(request, "portail/administration/compte.html", {
        "profil": profil, "formulaire": formulaire, "lien": lien, "moi": profil.id == request.user.id, "page_active": "admin_comptes"})


@technique_requis
@require_POST
def compte_action(request, compte_id):
    profil = get_object_or_404(ProfilUtilisateur, pk=compte_id)
    action = request.POST.get("action")
    if demo.compte_protege(profil.email or profil.username):
        messages.error(request, "Démonstration : les comptes de démonstration ne peuvent être ni désactivés ni réinitialisés, "
                                "pour que chaque visiteur puisse les utiliser. Créez un nouveau compte pour essayer ces actions.")
        return redirect("portail:admin_compte", compte_id=profil.id)
    try:
        if action == "desactiver":
            comptes.changer_etat(profil.id, False, request.POST.get("motif", ""))
            messages.success(request, f"Compte {profil.username} désactivé.")
        elif action == "reactiver":
            comptes.changer_etat(profil.id, True, request.POST.get("motif", ""))
            messages.success(request, f"Compte {profil.username} réactivé.")
        elif action in ("lien", "envoyer"):
            email, lien = comptes.nouveau_lien(profil.id)
            if action == "envoyer":
                comptes.envoyer_activation(email, lien, profil.first_name, profil.membre.raison_sociale if profil.membre_id else "")
                messages.success(request, f"Nouveau lien d'activation envoyé à {email}.")
            else:
                request.session["lien_activation"] = {"id": profil.id, "email": email, "lien": lien}
        else:
            messages.error(request, "Action inconnue.")
    except comptes.OperationRefusee as e:
        messages.error(request, str(e))
    return redirect("portail:admin_compte", compte_id=profil.id)
