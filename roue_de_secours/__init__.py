"""Roue de Secours : assistant d'aide du portail (« pour vous dépanner si vous êtes perdu sur le site »).

Module autonome, branché sur le portail en quatre points seulement (voir ROUE_DE_SECOURS.md) :
INSTALLED_APPS + processeur de contexte, une ligne dans config/urls.py, une inclusion dans base.html.

Principe de sécurité : la Roue de Secours ne sait jamais plus que la personne qui lui parle.
- Elle répond à partir de fiches d'aide écrites à la main (dossier connaissances/), pas à partir des données.
- La seule information personnelle qu'elle reçoit est la « situation » de l'utilisateur : des statuts et des dates,
  lus avec ses propres droits (même rôle PostgreSQL que la page affichée), JAMAIS une quantité.
- Le prestataire d'IA ne reçoit ni nom, ni adresse e-mail, ni nom de société.
"""
