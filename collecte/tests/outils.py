"""Outils de test : simuler exactement ce que fait le middleware (SET LOCAL ROLE + contexte)."""
from contextlib import contextmanager

from django.db import DatabaseError, connection, transaction


@contextmanager
def en_tant_que(role, membre_id=None, utilisateur_id=None):
    with connection.cursor() as cur:
        cur.execute(f"SET LOCAL ROLE {role}")
        cur.execute("SELECT set_config('app.membre_id', %s, true), set_config('app.utilisateur_id', %s, true)",
                    [str(membre_id or ""), str(utilisateur_id or "")])
    try:
        yield
    finally:
        with connection.cursor() as cur:
            cur.execute("RESET ROLE")
            cur.execute("SELECT set_config('app.membre_id', '', true), set_config('app.utilisateur_id', '', true)")


def requete(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else cur.rowcount


def doit_echouer(test, fonction, exc=DatabaseError):
    """Exécute `fonction` dans un point de sauvegarde et exige une erreur de base de données.
    À appeler À L'INTÉRIEUR de `en_tant_que` pour que RESET ROLE passe après le rollback."""
    with test.assertRaises(exc):
        with transaction.atomic():
            fonction()


# ----------------------------------------------------------------------- fichiers Excel de test
import io  # noqa: E402

from openpyxl import load_workbook  # noqa: E402

from collecte.contexte import en_role  # noqa: E402
from collecte.excel.depot import deposer_declaration  # noqa: E402
from collecte.excel.gabarit import generer_gabarit  # noqa: E402


def generer(d, code, mois):
    """Gabarit du membre `code`, généré avec le rôle membre (comme le ferait le portail)."""
    m, u = d.membres[code], d.users[code]
    with en_role("gipame_membre", membre_id=m.id, utilisateur_id=u.id):
        return generer_gabarit(m, mois)[0]


def deposer(d, code, contenu, soumettre=True, nom="declaration.xlsx"):
    m, u = d.membres[code], d.users[code]
    with en_role("gipame_membre", membre_id=m.id, utilisateur_id=u.id):
        return deposer_declaration(contenu, nom, m, u, soumettre=soumettre)


from collecte.cycle import remplir_gabarit as remplir  # noqa: E402,F401
