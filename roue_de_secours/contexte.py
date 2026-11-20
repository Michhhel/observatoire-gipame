"""Processeur de contexte : ce qu'il faut au gabarit pour afficher la Roue de Secours sur chaque page connectée."""
import hashlib
import hmac

from django.conf import settings
from django.urls import Resolver404, resolve

from portail.acces import ROLES

from . import reglages

SUGGESTIONS_PAGE = {
    "accueil": ["Que dois-je faire ce mois-ci ?", "Quelle est ma date limite ?", "Qui voit mes chiffres ?"],
    "assistant": ["Comment remplir le fichier Excel ?", "Je n'ai rien vendu ce mois-ci", "Excel n'ouvre pas le fichier"],
    "rapport": ["Différence entre erreur et alerte ?", "Puis-je soumettre avec une alerte ?", "Comment corriger mon fichier ?"],
    "confirmation": ["Comment corriger après avoir soumis ?", "Quand le marché sera-t-il publié ?"],
    "historique": ["Comment corriger un mois déjà soumis ?", "Mon ancienne version est-elle effacée ?"],
    "mon_annee": ["Comment exporter mes ventes en Excel ?", "Pourquoi un mois est vide ?"],
    "marche": ["Que signifie « c » ?", "Provisoire ou définitive ?", "Quand sortent les chiffres ?"],
    "mes_produits": ["Comment proposer un nouveau produit ?", "Que se passe-t-il si je masque un produit ?"],
    "gestion_tableau": ["Comment relancer les retardataires ?", "Que contient le courriel de rappel ?"],
    "gestion_publications": ["Quand publier en définitif ?", "Un membre a corrigé après publication"],
    "gestion_propositions": ["Valider, fusionner ou rejeter ?", "Où apparaît le produit validé ?"],
    "gestion_proposition": ["Valider, fusionner ou rejeter ?"],
    "gestion_membres": ["Comment ajouter un membre ?", "À quoi sert le groupe économique ?"],
    "gestion_demandes": ["Comment fonctionne l'accès exceptionnel ?", "Combien de temps dure l'accès ?"],
    "bureau_tableau": ["Que signifie « c » ?", "Pourquoi ne vois-je pas le nombre de contributeurs ?"],
    "bureau_approbations": ["Comment approuver une demande ?", "Combien d'accords faut-il ?"],
    "bureau_journal": ["Que contient le journal des accès ?", "Comment imprimer le journal ?"],
    "admin_comptes": ["Comment créer un compte ?", "Renvoyer un lien d'activation"],
    "admin_compte": ["Désactiver ou supprimer un compte ?", "Renvoyer un lien d'activation"],
}
SUGGESTIONS_ROLE = {
    "MEMBRE": ["Comment déclarer mes ventes ?", "Quelle est ma date limite ?", "Qui voit mes chiffres ?"],
    "GESTION": ["Qui n'a pas encore déclaré ?", "Comment publier le marché ?", "Traiter un produit proposé"],
    "TECHNIQUE": ["Comment créer un compte ?", "Qui n'a pas encore déclaré ?", "Comment publier le marché ?"],
    "BUREAU": ["Comment approuver une demande ?", "Que contient le journal des accès ?", "Que signifie « c » ?"],
}


def contexte(request):
    user = getattr(request, "user", None)
    if not reglages.active() or not user or not user.is_authenticated or getattr(user, "role_metier", None) not in ROLES:
        return {"roue": {"active": False}}
    try:
        page = resolve(request.path_info).url_name
    except Resolver404:
        page = None
    # Clé de stockage de la conversation dans l'onglet : propre à chaque compte (un poste partagé ne mélange rien).
    cle = hmac.new(settings.SECRET_KEY.encode(), f"roue:{user.pk}".encode(), hashlib.sha256).hexdigest()[:16]
    return {"roue": {
        "active": True, "cle": f"roue-{cle}", "role": user.role_metier,
        "suggestions": SUGGESTIONS_PAGE.get(page) or SUGGESTIONS_ROLE[user.role_metier],
        "ia": reglages.fournisseur() != "hors_ligne",
    }}
