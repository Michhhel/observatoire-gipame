"""Service « comptes » : création, activation, désactivation, modification — par les fonctions SQL de
collecte/sql/0007_comptes.sql. Utilisé par l'écran Comptes du portail (rôle TECHNIQUE, via gipame_app)
et par la commande gerer_compte (connexion propriétaire). Aucun accès direct à la table des comptes ici.
"""
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import DatabaseError, connection, transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import ProfilUtilisateur, Utilisateur


class OperationRefusee(ValueError):
    """Message destiné à l'administrateur, tel que formulé par la base."""


def _appeler(sql, params):
    try:
        with transaction.atomic(), connection.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else None
    except DatabaseError as e:
        message = str(getattr(e, "__cause__", None) or e).split("\n")[0]
        raise OperationRefusee(message.replace("ERREUR:", "").replace("ERROR:", "").strip()) from None


def creer(email, prenom, nom, role, membre_id=None, poste_code=None):
    """Crée le compte ; renvoie (id, lien d'activation)."""
    (identifiant, mot_de_passe), = _appeler("SELECT r_id, r_mot_de_passe FROM gipame_compte_creer(%s, %s, %s, %s, %s, %s)",
                                            [email, prenom, nom, role, membre_id, poste_code])
    return identifiant, lien_activation(identifiant, email.strip().lower(), mot_de_passe, None)


def lien_activation(identifiant, email, mot_de_passe, derniere_connexion):
    """Jeton Django standard (usage unique, PASSWORD_RESET_TIMEOUT) calculé sans lire la table des comptes."""
    fantome = Utilisateur(pk=identifiant, email=email, password=mot_de_passe, last_login=derniere_connexion)
    uid = urlsafe_base64_encode(force_bytes(identifiant))
    return settings.URL_PUBLIQUE.rstrip("/") + reverse("portail:activation", kwargs={"uidb64": uid, "token": default_token_generator.make_token(fantome)})


def nouveau_lien(identifiant):
    """Nouveau lien d'activation pour un compte qui n'a jamais choisi de mot de passe. Renvoie (email, lien)."""
    (email, mot_de_passe, derniere), = _appeler("SELECT * FROM gipame_compte_pour_activation(%s)", [identifiant])
    return email, lien_activation(identifiant, email, mot_de_passe, derniere)


def envoyer_activation(email, lien, prenom="", societe=""):
    send_mail("Observatoire GIPAME : activez votre compte",
              render_to_string("portail/courriels/activation.txt", {"prenom": prenom, "email": email, "url_activation": lien, "societe": societe}),
              settings.DEFAULT_FROM_EMAIL, [email])


def changer_etat(identifiant, actif, motif=""):
    _appeler("SELECT gipame_compte_etat(%s, %s, %s)", [identifiant, actif, motif])


def modifier(identifiant, email, prenom, nom):
    _appeler("SELECT gipame_compte_modifier(%s, %s, %s, %s)", [identifiant, email, prenom, nom])


def profils(membre_code=None):
    qs = ProfilUtilisateur.objects.select_related("membre").order_by("role_metier", "membre__code", "username")
    if membre_code:
        qs = qs.filter(membre__code=membre_code)
    return qs
