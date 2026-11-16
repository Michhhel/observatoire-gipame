"""Formulaires du portail. Les libellés sont ceux affichés au membre : français simple, sans jargon."""
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm

from collecte.models import Boite, Energie, Marque

from . import securite

EXTENSIONS_ACCEPTEES = (".xlsx",)


class FormulaireConnexion(AuthenticationForm):
    """Connexion par adresse e-mail (le nom d'utilisateur interne EST l'adresse, en minuscules)."""

    username = forms.EmailField(label="Adresse e-mail", widget=forms.EmailInput(
        attrs={"autocomplete": "email", "autofocus": True, "placeholder": "prenom.nom@societe.ci", "inputmode": "email"}))
    password = forms.CharField(label="Mot de passe", strip=False,
                               widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    error_messages = {
        "invalid_login": "Adresse e-mail ou mot de passe incorrect.",
        "inactive": "Ce compte est désactivé. Contactez le GIPAME.",
        "bloque": "Trop de tentatives. Patientez 15 minutes avant de réessayer, ou utilisez « Mot de passe oublié ».",
    }

    def clean(self):
        identifiant = securite.normaliser_identifiant(self.cleaned_data.get("username"))
        mot_de_passe = self.cleaned_data.get("password")
        if not identifiant or not mot_de_passe:
            return self.cleaned_data
        if securite.est_bloque(identifiant):
            securite.enregistrer(identifiant, False, self.request)
            raise forms.ValidationError(self.error_messages["bloque"], code="bloque")
        self.user_cache = authenticate(self.request, username=identifiant, password=mot_de_passe)
        securite.enregistrer(identifiant, self.user_cache is not None, self.request)
        if self.user_cache is None:
            raise self.get_invalid_login_error()
        self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class FormulaireMotDePasseOublie(PasswordResetForm):
    email = forms.EmailField(label="Adresse e-mail", max_length=254,
                             widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}))


class FormulaireNouveauMotDePasse(SetPasswordForm):
    new_password1 = forms.CharField(label="Nouveau mot de passe", strip=False,
                                    widget=forms.PasswordInput(attrs={"autocomplete": "new-password", "autofocus": True}),
                                    help_text="Au moins 8 caractères, pas uniquement des chiffres.")
    new_password2 = forms.CharField(label="Confirmez le mot de passe", strip=False,
                                    widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))


class FormulaireDepot(forms.Form):
    fichier = forms.FileField(label="Votre fichier Excel rempli", allow_empty_file=False)
    motif = forms.CharField(label="Pourquoi corrigez-vous cette déclaration ?", required=False, max_length=300,
                            widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Ex. : 3 livraisons facturées après la clôture."}))

    def __init__(self, *args, correction=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.correction = correction
        if not correction:
            self.fields.pop("motif")

    def clean_motif(self):
        motif = (self.cleaned_data.get("motif") or "").strip()
        if self.correction and not motif:
            raise forms.ValidationError("Indiquez en une phrase le motif de la correction : il sera conservé avec la nouvelle version.")
        return motif

    def clean_fichier(self):
        f = self.cleaned_data["fichier"]
        if not f.name.lower().endswith(EXTENSIONS_ACCEPTEES):
            raise forms.ValidationError("Seul le format Excel (.xlsx) est accepté : enregistrez le fichier au format "
                                        "« Classeur Excel (*.xlsx) » puis déposez-le à nouveau.")
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Le fichier dépasse 5 Mo : vérifiez qu'il s'agit bien du gabarit rempli.")
        return f


class FormulaireSoumission(forms.Form):
    attestation = forms.BooleanField(
        label="Je certifie que cette déclaration est complète et exacte pour le mois indiqué.", required=True,
        error_messages={"required": "L'attestation est nécessaire pour soumettre la déclaration."})
    motif = forms.CharField(label="Motif de la correction", required=False, max_length=500,
                            widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Ex. : 3 livraisons de novembre facturées en décembre."}))
    commentaire = forms.CharField(label="Vos explications sur les points signalés", required=False, max_length=2000,
                                  widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Facultatif : une phrase suffit."}))

    def __init__(self, *args, correction=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.correction = correction
        if not correction:
            self.fields.pop("motif")

    def clean_motif(self):
        motif = (self.cleaned_data.get("motif") or "").strip()
        if self.correction and not motif:
            raise forms.ValidationError("Indiquez en une phrase pourquoi vous corrigez cette déclaration.")
        return motif


class FormulaireProposition(forms.Form):
    """Proposer un nouveau produit depuis le portail (même validation que l'onglet AJOUTS)."""

    marque = forms.ModelChoiceField(label="Marque", queryset=Marque.objects.none(), empty_label="Choisissez…")
    modele = forms.CharField(label="Modèle", max_length=120, help_text="Ex. : Hilux, Sportage, Tunland.")
    finition = forms.CharField(label="Version / finition", max_length=120, help_text="Ex. : 2.4 D 4x4 BVM, GL, PRESTIGE.")
    energie = forms.ModelChoiceField(label="Énergie", queryset=Energie.objects.filter(actif=True), empty_label="Choisissez…")
    boite = forms.ModelChoiceField(label="Boîte", queryset=Boite.objects.filter(actif=True), required=False, empty_label="—")
    cylindree = forms.IntegerField(label="Cylindrée (cm³)", required=False, min_value=0)
    puissance = forms.IntegerField(label="Puissance fiscale (CV)", required=False, min_value=0)
    places = forms.IntegerField(label="Nombre de places", required=False, min_value=0)
    ptac = forms.IntegerField(label="PTAC (kg)", required=False, min_value=0)
    charge = forms.IntegerField(label="Charge utile (kg)", required=False, min_value=0)
    motricite = forms.ChoiceField(label="Motricité", required=False, choices=[("", "—"), ("4X2", "4x2"), ("4X4", "4x4")])
    segment = forms.CharField(label="Type de véhicule (votre suggestion)", required=False, max_length=150,
                              help_text="Ex. : pick-up 4x4, SUV, bus 23-34 places. Le GIPAME classera le produit.")
    note = forms.CharField(label="Remarque pour le GIPAME", required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, marques=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["marque"].queryset = marques if marques is not None else Marque.objects.none()

    def clean_finition(self):
        return self.cleaned_data["finition"].strip().upper()
