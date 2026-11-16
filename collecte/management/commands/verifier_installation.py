from django.core.management.base import BaseCommand, CommandError
from django.db import connection

TABLES_RLS = ["collecte_declaration", "collecte_lignevente", "collecte_produit", "collecte_concession", "collecte_periodeadhesion",
              "collecte_produitmembre", "collecte_aliasproduit", "collecte_parametresysteme", "collecte_demandeaccesexceptionnel",
              "collecte_approbationacces", "collecte_journalmodification", "collecte_depotfichier"]
TABLES_METIER = ["collecte_lignevente", "collecte_declaration", "collecte_membre", "collecte_produit", "collecte_celluleagregat"]
ROLES = ["gipame_membre", "gipame_gestion", "gipame_bureau", "gipame_calcul", "gipame_app", "gipame_purge"]


class Command(BaseCommand):
    help = "Vérifie qu'une installation respecte le modèle de sécurité (à lancer après chaque migration, avec le compte propriétaire)."

    def handle(self, *args, **options):
        resultats = []

        def verifier(nom, ok, detail=""):
            resultats.append(ok)
            self.stdout.write(("  OK    " if ok else "  ECHEC ") + nom + (f" : {detail}" if detail else ""))

        with connection.cursor() as cur:
            cur.execute("SHOW server_version_num")
            version = int(cur.fetchone()[0])
            verifier("PostgreSQL >= 15", version >= 150000, f"version {version}")
            cur.execute("SELECT count(*) FROM pg_extension WHERE extname = 'btree_gist'")
            verifier("extension btree_gist", cur.fetchone()[0] == 1)
            cur.execute("SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)", [ROLES])
            presents = {r[0] for r in cur.fetchall()}
            verifier("les 6 rôles existent", presents == set(ROLES), f"manquants : {sorted(set(ROLES) - presents)}")
            cur.execute("SELECT rolinherit, rolsuper FROM pg_roles WHERE rolname = 'gipame_app'")
            ligne = cur.fetchone()
            verifier("gipame_app : NOINHERIT et non superutilisateur", bool(ligne) and not ligne[0] and not ligne[1])
            for table in TABLES_METIER:
                cur.execute("SELECT has_table_privilege('gipame_app', %s, 'SELECT')", [table])
                verifier(f"gipame_app sans droit direct sur {table}", not cur.fetchone()[0])
            cur.execute("SELECT relname FROM pg_class WHERE relrowsecurity AND relname = ANY(%s)", [TABLES_RLS])
            actives = {r[0] for r in cur.fetchall()}
            verifier("sécurité par ligne activée", actives == set(TABLES_RLS), f"manquantes : {sorted(set(TABLES_RLS) - actives)}")
            cur.execute("SELECT count(DISTINCT tgname) FROM pg_trigger WHERE tgname IN ('trg_declaration','trg_lignevente','trg_produit',"
                        "'trg_pas_de_suppression','trg_ajout_seulement','trg_audit','trg_immuable','trg_approbation','trg_classement')")
            verifier("triggers d'intégrité et d'audit", cur.fetchone()[0] == 9)
            # Portail (migration collecte 0006 + portail 0001 + appliquer_droits_techniques)
            cur.execute("SELECT count(*) FROM pg_trigger WHERE tgname = 'trg_pas_de_suppression' "
                        "AND tgrelid = 'collecte_utilisateur'::regclass")
            verifier("comptes non supprimables (trigger sur collecte_utilisateur)", cur.fetchone()[0] == 1)
            cur.execute("SELECT has_table_privilege('gipame_app', 'collecte_utilisateur', 'DELETE')")
            verifier("gipame_app sans DELETE sur les comptes", not cur.fetchone()[0], "lancer appliquer_droits_techniques")
            cur.execute("SELECT to_regclass('portail_tentativeconnexion') IS NOT NULL AND "
                        "has_table_privilege('gipame_app', 'portail_tentativeconnexion', 'INSERT')")
            verifier("journal des connexions du portail accessible à gipame_app", cur.fetchone()[0], "migrer puis appliquer_droits_techniques")
            cur.execute("SELECT has_table_privilege('gipame_bureau', 'collecte_v_profil_utilisateur', 'SELECT') AND "
                        "NOT has_table_privilege('gipame_bureau', 'collecte_utilisateur', 'SELECT')")
            verifier("annuaire des comptes en lecture seule pour le bureau et la gestion", cur.fetchone()[0])
            cur.execute("SELECT has_function_privilege('gipame_gestion', 'gipame_compte_creer(text,text,text,text,bigint,text)', 'EXECUTE') "
                        "AND NOT has_table_privilege('gipame_gestion', 'collecte_utilisateur', 'INSERT')")
            verifier("gestion des comptes par fonctions à privilège défini (migration 0007)", cur.fetchone()[0])
            cur.execute("SELECT has_function_privilege('gipame_gestion', 'gipame_destinataires_rappel(date)', 'EXECUTE') "
                        "AND NOT has_function_privilege('gipame_membre', 'gipame_destinataires_rappel(date)', 'EXECUTE') "
                        "AND NOT has_function_privilege('gipame_bureau', 'gipame_destinataires_rappel(date)', 'EXECUTE')")
            verifier("rappels : destinataires calculés par la base, réservés à la gestion (migration 0008)", cur.fetchone()[0])
            cur.execute("SELECT pg_has_role('gipame_app', 'gipame_calcul', 'MEMBER')")
            verifier("gipame_app peut basculer vers gipame_calcul (publication depuis le portail)", cur.fetchone()[0])
            cur.execute("SELECT valeur FROM collecte_parametresysteme WHERE cle = 'seuil_approbations_acces'")
            ligne = cur.fetchone()
            verifier("seuil d'accès exceptionnel défini", bool(ligne), f"{ligne[0]} poste(s) sur 3" if ligne else "")
            if ligne and int(ligne[0]) < 2:
                self.stdout.write(self.style.WARNING("  ATTENTION : un seul poste suffit à ouvrir les données individuelles."))
            cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            qualite = "superutilisateur : ne jamais l'utiliser en exploitation" if cur.fetchone()[0] else "non superutilisateur"
            self.stdout.write(f"  INFO  connecté en tant que {connection.settings_dict['USER']} ({qualite})")
        if not all(resultats):
            raise CommandError("Installation non conforme.")
        self.stdout.write(self.style.SUCCESS("Installation conforme."))
