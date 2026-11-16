"""Comptes du portail en ligne de commande (connexion PROPRIÉTAIRE). Sert surtout à créer le tout premier
compte administrateur (rôle TECHNIQUE) ; ensuite, l'écran « Comptes » du portail fait la même chose.

  python manage.py gerer_compte creer --email admin@gipame.ci --prenom … --nom … --role TECHNIQUE [--envoyer]
  python manage.py gerer_compte creer --email a.kone@societe.ci --role MEMBRE --membre A1
  python manage.py gerer_compte renvoyer   --email …
  python manage.py gerer_compte desactiver --email … --motif "…"
  python manage.py gerer_compte reactiver  --email …
  python manage.py gerer_compte lister [--membre A1]
"""
from django.core.management.base import BaseCommand, CommandError

from collecte import comptes
from collecte.models import Membre, ProfilUtilisateur


class Command(BaseCommand):
    help = "Créer, réactiver, désactiver ou lister les comptes du portail (connexion propriétaire)."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["creer", "renvoyer", "desactiver", "reactiver", "lister"])
        parser.add_argument("--email")
        parser.add_argument("--prenom", default="")
        parser.add_argument("--nom", default="")
        parser.add_argument("--role", choices=["MEMBRE", "GESTION", "BUREAU", "TECHNIQUE"])
        parser.add_argument("--membre", help="code du membre (rôle MEMBRE)")
        parser.add_argument("--poste", help="code du poste du bureau (PRESIDENT, VICE_PRESIDENT, DELEGUE_GENERAL)")
        parser.add_argument("--motif", default="")
        parser.add_argument("--envoyer", action="store_true", help="envoyer le lien d'activation par e-mail")

    def handle(self, *args, **o):
        try:
            getattr(self, o["action"])(o)
        except comptes.OperationRefusee as e:
            raise CommandError(str(e))

    def _profil(self, o):
        email = (o.get("email") or "").strip().lower()
        if not email:
            raise CommandError("--email est obligatoire.")
        p = ProfilUtilisateur.objects.filter(username=email).first()
        if p is None:
            raise CommandError(f"Aucun compte pour {email}.")
        return p

    def _transmettre(self, email, lien, envoyer, prenom=""):
        if envoyer:
            comptes.envoyer_activation(email, lien, prenom)
            self.stdout.write(self.style.SUCCESS(f"Lien d'activation envoyé à {email} (valable 24 h)."))
        else:
            self.stdout.write(f"Lien d'activation (valable 24 h, à transmettre par un canal sûr) :\n{lien}")

    def creer(self, o):
        if not o.get("email") or not o.get("role"):
            raise CommandError("--email et --role sont obligatoires.")
        membre_id = None
        if o.get("membre"):
            membre = Membre.objects.filter(code=o["membre"]).first()
            if membre is None:
                raise CommandError(f"Membre inconnu : {o['membre']}")
            membre_id = membre.id
        identifiant, lien = comptes.creer(o["email"], o["prenom"], o["nom"], o["role"], membre_id, o.get("poste"))
        self.stdout.write(self.style.SUCCESS(f"Compte créé : {o['email'].strip().lower()} ({o['role']})."))
        self._transmettre(o["email"].strip().lower(), lien, o["envoyer"], o["prenom"])

    def renvoyer(self, o):
        p = self._profil(o)
        email, lien = comptes.nouveau_lien(p.id)
        self._transmettre(email, lien, o["envoyer"], p.first_name)

    def desactiver(self, o):
        p = self._profil(o)
        comptes.changer_etat(p.id, False, o.get("motif", ""))
        self.stdout.write(self.style.SUCCESS(f"Compte désactivé : {p.username} — {o['motif']}"))

    def reactiver(self, o):
        p = self._profil(o)
        comptes.changer_etat(p.id, True, o.get("motif", ""))
        self.stdout.write(self.style.SUCCESS(f"Compte réactivé : {p.username}"))

    def lister(self, o):
        for p in comptes.profils(o.get("membre")):
            etat = "actif" if p.is_active else "désactivé"
            self.stdout.write(f"{p.role_metier:9} {(p.membre.code if p.membre_id else '—'):6} {p.username:40} {etat}, "
                              f"{'activé' if p.compte_active else 'non activé'}")
