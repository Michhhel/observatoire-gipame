"""Connexion, déconnexion, activation de compte et mot de passe oublié.

Mécanisme : vues d'authentification de Django avec nos formulaires et gabarits. L'activation d'un
nouveau compte utilise le même jeton à usage unique que « mot de passe oublié » (validité :
settings.PASSWORD_RESET_TIMEOUT, 24 h), envoyé par e-mail par la gestion lors de la création du compte.
"""
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from ..acces import accueil_selon_role
from ..formulaires import FormulaireConnexion, FormulaireMotDePasseOublie, FormulaireNouveauMotDePasse


class Connexion(auth_views.LoginView):
    template_name = "portail/compte/connexion.html"
    authentication_form = FormulaireConnexion
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        return reverse_lazy(accueil_selon_role(self.request.user))


class Deconnexion(auth_views.LogoutView):
    next_page = "portail:connexion"


class MotDePasseOublie(auth_views.PasswordResetView):
    template_name = "portail/compte/mot_de_passe_oublie.html"
    form_class = FormulaireMotDePasseOublie
    email_template_name = "portail/courriels/reinitialisation.txt"
    subject_template_name = "portail/courriels/reinitialisation_objet.txt"
    success_url = reverse_lazy("portail:mot_de_passe_envoye")


class MotDePasseEnvoye(auth_views.PasswordResetDoneView):
    template_name = "portail/compte/mot_de_passe_envoye.html"


class NouveauMotDePasse(auth_views.PasswordResetConfirmView):
    """Sert à la fois à la réinitialisation et à l'activation (le gabarit adapte le titre)."""
    template_name = "portail/compte/nouveau_mot_de_passe.html"
    form_class = FormulaireNouveauMotDePasse
    success_url = reverse_lazy("portail:mot_de_passe_change")
    activation = False

    def get_context_data(self, **kwargs):
        contexte = super().get_context_data(**kwargs)
        contexte["activation"] = self.activation
        return contexte


class Activation(NouveauMotDePasse):
    activation = True


class MotDePasseChange(auth_views.PasswordResetCompleteView):
    template_name = "portail/compte/mot_de_passe_change.html"


def racine(request):
    """/ → accueil du rôle pour une personne connectée, sinon la page de présentation publique."""
    if request.user.is_authenticated:
        return redirect(accueil_selon_role(request.user))
    from .vitrine import vitrine
    return vitrine(request)


def sante(request):
    """Sonde de disponibilité pour l'hébergeur : ne lit ni session ni base."""
    from django.http import HttpResponse
    return HttpResponse("ok", content_type="text/plain")


def acces_refuse(request, exception=None):
    return render(request, "portail/commun/403.html", status=403)


def introuvable(request, exception=None):
    return render(request, "portail/commun/404.html", status=404)


def erreur_serveur(request):
    return render(request, "portail/commun/500.html", status=500)
