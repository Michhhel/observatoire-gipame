"""Contexte de base de données d'une opération : rôle PostgreSQL + identité (membre, utilisateur).

Même mécanisme pour le middleware web, les commandes et les tests : une transaction, SET LOCAL ROLE
vers un rôle métier, puis les réglages de session lus par la sécurité par ligne. Tout disparaît à la
fin de la transaction.

ATTENTION (frontière de confiance) : la sécurité par ligne se fonde sur `app.membre_id`, posé par le
code applicatif. Ne jamais le prendre dans une requête HTTP : toujours `request.user.membre_id`.
"""
from contextlib import contextmanager

from django.db import connection, transaction

ROLES_METIER = {"gipame_membre", "gipame_gestion", "gipame_bureau", "gipame_calcul"}

PARAMETRES_PAR_DEFAUT = {
    "jours_grace_depot": "10", "definition_vente": "Véhicules neufs facturés dans le mois.",
    "contact_gipame": "", "import_variation_alerte_pct": "50", "import_variation_min_unites": "10",
    "import_quantite_max": "20000", "import_max_ajouts": "20", "import_taille_max_ko": "2048",
}


@contextmanager
def en_role(role, membre_id=None, utilisateur_id=None):
    """Exécute le bloc sous `role`. Imbricable : à la sortie d'un bloc imbriqué (ex. calcul d'une
    publication lancé depuis une page de la gestion), le rôle et le contexte précédents sont rétablis."""
    if role not in ROLES_METIER:
        raise ValueError(f"Rôle inconnu : {role}")
    precedent = None
    if connection.in_atomic_block:
        with connection.cursor() as cur:
            cur.execute("SELECT current_user, current_setting('app.membre_id', true), current_setting('app.utilisateur_id', true)")
            precedent = cur.fetchone()
    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(f"SET LOCAL ROLE {role}")  # valeur issue d'une liste blanche
                cur.execute(
                    "SELECT set_config('app.membre_id', %s, true), set_config('app.utilisateur_id', %s, true)",
                    [str(membre_id or ""), str(utilisateur_id or "")],
                )
            yield
    finally:
        if connection.in_atomic_block:  # transaction englobante : SET LOCAL survit au point de sauvegarde
            role_prec, membre_prec, util_prec = precedent or (None, "", "")
            with connection.cursor() as cur:
                if role_prec in ROLES_METIER:
                    cur.execute(f"SET LOCAL ROLE {role_prec}")  # liste blanche
                else:
                    cur.execute("RESET ROLE")
                cur.execute("SELECT set_config('app.membre_id', %s, true), set_config('app.utilisateur_id', %s, true)",
                            [membre_prec or "", util_prec or ""])


def garantir_contexte_membre(membre_id):
    """À appeler dans une transaction. Pose le contexte s'il est absent (développement sans bascule de
    rôle) ; refuse s'il désigne un autre membre."""
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting('app.membre_id', true)")
        actuel = cur.fetchone()[0] or ""
        if actuel == "":
            cur.execute("SELECT set_config('app.membre_id', %s, true)", [str(membre_id)])
        elif actuel != str(membre_id):
            raise PermissionError("Le contexte de session désigne un autre membre.")


def parametres_publics():
    with connection.cursor() as cur:
        cur.execute("SELECT p_cle, p_valeur FROM gipame_parametres_publics()")
        valeurs = dict(cur.fetchall())
    return {**PARAMETRES_PAR_DEFAUT, **valeurs}
