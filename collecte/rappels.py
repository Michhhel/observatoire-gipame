"""Rappels de dépôt et calcul des publications lancés depuis le portail de la gestion.

Rappels : les destinataires viennent de la fonction SQL gipame_destinataires_rappel (la gestion ne lit pas la
table des comptes). Un courriel PAR destinataire (jamais de liste de destinataires visible), qui ne parle que
de la société du destinataire : ni quantité, ni nom d'un autre membre, ni nombre de retardataires.
"""
import logging
from datetime import date

from django.conf import settings
from django.core.mail import send_mail
from django.db import connection
from django.template.loader import render_to_string
from django.urls import reverse

journal = logging.getLogger(__name__)


def destinataires(mois):
    """[(membre_id, raison_sociale, email|None, prenom, date_limite)] — à appeler sous gipame_gestion."""
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM gipame_destinataires_rappel(%s)", [mois])
        return cur.fetchall()


def envoyer_rappels(mois):
    """Envoie les rappels du mois. Renvoie {'envoyes', 'membres', 'sans_compte': [raisons sociales], 'echecs': [emails]}."""
    from portail.formats import de_mois, date_longue  # formats français partagés avec le portail

    lignes = destinataires(mois)
    membres, sans_compte, envoyes, echecs = set(), [], 0, []
    for membre_id, societe, email, prenom, date_limite in lignes:
        membres.add(membre_id)
        if not email:
            sans_compte.append(societe)
            continue
        contexte = {"prenom": prenom, "societe": societe, "mois": de_mois(mois),
                    "date_limite": date_longue(date_limite), "en_retard": date.today() > date_limite,
                    "url": settings.URL_PUBLIQUE + reverse("portail:assistant")}
        try:
            send_mail(render_to_string("portail/courriels/rappel_objet.txt", contexte).strip(),
                      render_to_string("portail/courriels/rappel.txt", contexte),
                      None, [email])
            envoyes += 1
        except Exception:  # un serveur de messagerie capricieux ne doit pas bloquer les autres envois
            journal.exception("Échec d'envoi d'un rappel")
            echecs.append(email)
    return {"envoyes": envoyes, "membres": len(membres), "sans_compte": sans_compte, "echecs": echecs}


def jours_de_rappel(mois, aujourd_hui=None):
    """Rappels automatiques : 3 jours avant la date limite, le lendemain, puis une semaine après."""
    from datetime import timedelta
    with connection.cursor() as cur:
        cur.execute("SELECT COALESCE((SELECT valeur::integer FROM collecte_parametresysteme WHERE cle = 'jours_grace_depot'), 10)")
        grace = cur.fetchone()[0]
    suivant = date(mois.year + mois.month // 12, mois.month % 12 + 1, 1)
    limite = suivant + timedelta(days=grace)
    aujourd_hui = aujourd_hui or date.today()
    return aujourd_hui in {limite - timedelta(days=3), limite + timedelta(days=1), limite + timedelta(days=7)}


def publier(mois, definitive=False):
    """Calcule et fige la publication d'un mois depuis une page de la gestion. Le calcul tourne sous le rôle
    gipame_calcul (seul autorisé à lire les lignes individuelles) ; la gestion ne reçoit que le résumé
    (version, statut, couverture). Lève ValueError si la couverture est insuffisante pour un définitif."""
    from .contexte import en_role
    from .services import calculer_publication
    with en_role("gipame_calcul"):
        pub = calculer_publication(mois, statut="DEFINITIVE" if definitive else "PROVISOIRE")
        return {"version": pub.version, "statut": pub.get_statut_display(), "couverture": pub.couverture_pct,
                "declarants": pub.nb_membres_declarants, "attendus": pub.nb_membres_attendus}
