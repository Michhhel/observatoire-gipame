"""Jeu d'évaluation de la recherche : (rôle, question telle qu'un utilisateur l'écrirait, fiches acceptables).

Règle : la bonne fiche doit figurer parmi les 3 premiers passages retrouvés. Les tests exigent au moins 90 % de
réussite (et la commande roue_verifier affiche les échecs). Quand une réponse fausse est signalée, ajouter ici la
question qui l'a provoquée, corriger la fiche, relancer : le problème ne peut plus revenir sans qu'on le voie.
"""
CAS = [
    # --- membre : déclarer
    ("MEMBRE", "Comment je fais pour déclarer mes ventes du mois ?", {"declarer-etapes"}),
    ("MEMBRE", "comment envoyer mon fichier excel", {"declarer-etapes"}),
    ("MEMBRE", "c'est quand la date limite pour déclarer", {"declarer-etapes", "calendrier"}),
    ("MEMBRE", "j'ai déposé mon fichier, c'est bon ou il faut faire autre chose ?", {"declarer-etapes", "rapport-controle"}),
    ("MEMBRE", "quelle différence entre déposer et soumettre", {"declarer-etapes", "glossaire"}),
    ("MEMBRE", "on a rien vendu ce mois, on fait quoi", {"aucune-vente"}),
    ("MEMBRE", "toutes mes quantités sont à zéro et le fichier est refusé", {"aucune-vente", "messages-rapport"}),
    ("MEMBRE", "où est-ce que je mets les quantités dans le fichier", {"gabarit-excel"}),
    ("MEMBRE", "les cases grises ne se modifient pas", {"gabarit-excel"}),
    ("MEMBRE", "excel affiche un bandeau jaune mode protégé", {"gabarit-excel", "excel-problemes"}),
    ("MEMBRE", "le fichier ne s'ouvre pas", {"excel-problemes", "gabarit-excel"}),
    ("MEMBRE", "je travaille sur mac avec numbers", {"excel-problemes"}),
    ("MEMBRE", "est-ce que je peux envoyer un csv", {"excel-problemes", "gabarit-excel"}),
    ("MEMBRE", "fichier modifié ou non reconnu", {"excel-problemes", "messages-rapport"}),
    ("MEMBRE", "Gabarit déjà utilisé, ça veut dire quoi ?", {"messages-rapport", "corriger-declaration"}),
    ("MEMBRE", "Produit en double", {"messages-rapport"}),
    ("MEMBRE", "Motif de correction manquant", {"messages-rapport", "corriger-declaration"}),
    ("MEMBRE", "le rapport est orange, je peux quand même valider ?", {"rapport-controle"}),
    ("MEMBRE", "pourquoi on me demande une explication sur une variation", {"rapport-controle", "messages-rapport"}),
    ("MEMBRE", "je me suis trompé dans les chiffres après avoir soumis", {"corriger-declaration"}),
    ("MEMBRE", "comment modifier la déclaration du mois de mars", {"corriger-declaration"}),
    ("MEMBRE", "un modèle qu'on vend n'est pas dans la liste", {"nouveau-produit"}),
    ("MEMBRE", "notre marque n'apparait pas dans l'onglet ajouts", {"nouveau-produit"}),
    ("MEMBRE", "on ne vend plus ce véhicule, je l'enlève comment", {"nouveau-produit"}),
    ("MEMBRE", "où voir mes déclarations des mois passés", {"consulter-membre"}),
    ("MEMBRE", "exporter mes ventes de l'année en excel", {"consulter-membre"}),
    ("MEMBRE", "que veut dire provisoire sur le marché", {"consulter-membre"}),
    ("MEMBRE", "dans quel segment se trouve un pick-up", {"grille-segments", "glossaire"}),
    # --- tous : confidentialité, compte, assistant
    ("MEMBRE", "est-ce que le GIPAME voit mes chiffres ?", {"confidentialite"}),
    ("MEMBRE", "combien a vendu notre concurrent le mois dernier", {"confidentialite", "roue-de-secours"}),
    ("MEMBRE", "Que signifie « c » dans le tableau ?", {"confidentialite"}),
    ("BUREAU", "pourquoi des cases sont masquées", {"confidentialite", "bureau-marche-journal"}),
    ("MEMBRE", "j'ai oublié mon mot de passe", {"compte-connexion"}),
    ("GESTION", "mon compte est bloqué", {"compte-connexion"}),
    ("MEMBRE", "le lien d'activation ne marche plus", {"compte-connexion", "admin-comptes"}),
    ("MEMBRE", "pourquoi j'ai été déconnecté", {"compte-connexion"}),
    ("MEMBRE", "qui dois-je contacter au GIPAME", {"contact"}),
    ("MEMBRE", "c'est quoi l'observatoire, ça sert à quoi", {"observatoire"}),
    ("MEMBRE", "est-ce que tu peux soumettre à ma place", {"roue-de-secours"}),
    ("MEMBRE", "A quoi tu sers, comme chatbot ?", {"roue-de-secours"}),
    ("MEMBRE", "Quelles sont les ventes de alpha1", {"confidentialite"}),
    ("MEMBRE", "Combien Toyota a vendu ce mois ?", {"confidentialite"}),
    ("MEMBRE", "Comment ajouter un produit qui n'est pas dans mon fichier ?", {"nouveau-produit"}),
    ("BUREAU", "où partent mes questions, tu es une IA ?", {"roue-de-secours"}),
    # --- gestion
    ("GESTION", "qui n'a pas encore déclaré ce mois", {"gestion-depots-rappels"}),
    ("GESTION", "comment relancer les retardataires", {"gestion-depots-rappels"}),
    ("GESTION", "quand est-ce qu'on peut publier en définitif", {"gestion-publications"}),
    ("GESTION", "un membre a corrigé après la publication", {"gestion-publications"}),
    ("GESTION", "un membre a proposé un produit qui existe déjà", {"gestion-propositions"}),
    ("GESTION", "ajouter une nouvelle société membre", {"gestion-membres-catalogue"}),
    ("GESTION", "à quoi sert le groupe économique", {"gestion-membres-catalogue", "confidentialite"}),
    ("GESTION", "je dois vérifier les chiffres d'un membre", {"acces-exceptionnel"}),
    # --- bureau
    ("BUREAU", "combien d'accords faut-il pour un accès exceptionnel", {"acces-exceptionnel", "confidentialite"}),
    ("BUREAU", "comment approuver la demande de la gestion", {"acces-exceptionnel"}),
    ("BUREAU", "que contient le journal des accès", {"bureau-marche-journal"}),
    # --- administration
    ("TECHNIQUE", "créer un compte pour un nouvel utilisateur", {"admin-comptes"}),
    ("TECHNIQUE", "comment supprimer un compte", {"admin-comptes"}),
]

# Questions qui ne doivent RIEN trouver (hors sujet) : la Roue répond alors qu'elle ne sait pas.
HORS_SUJET = [
    ("MEMBRE", "quelle est la capitale du Japon"),
    ("MEMBRE", "donne-moi une recette de poulet braisé"),
    ("GESTION", "qui a gagné la coupe d'Afrique"),
]
