"""Pages communes : aide, charte de confidentialité (publiques, sans base de données pour un visiteur anonyme),
galerie des composants (aide au développement, visible seulement en DEBUG)."""
from django.conf import settings
from django.http import Http404
from django.shortcuts import render

from .. import formats


def galerie(request):
    """Guide de style vivant : tous les composants de base.css, avec des données fictives."""
    if not settings.DEBUG:
        raise Http404
    return render(request, "portail/commun/galerie.html", {"mois": formats.premier_du_mois(decalage=-1)})


def _parametres(request):
    """Paramètres publics (délai, contact…) pour un utilisateur connecté ; valeurs par défaut sinon."""
    from collecte.contexte import PARAMETRES_PAR_DEFAUT, parametres_publics
    return parametres_publics() if request.user.is_authenticated else dict(PARAMETRES_PAR_DEFAUT)


def aide(request):
    return render(request, "portail/commun/aide.html", {"p": _parametres(request), "page_active": "aide"})


def confidentialite(request):
    return render(request, "portail/commun/confidentialite.html", {
        "p": _parametres(request), "hebergement": settings.HEBERGEMENT_DONNEES, "page_active": "confidentialite"})
