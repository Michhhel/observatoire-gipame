"""Une seule table, isolée du reste de la base : les avis donnés sur les réponses (boutons « Utile » / « À revoir »,
« Signaler une question sans réponse »).

Anonyme par construction : aucun lien vers le compte ni vers la société, seulement le rôle (membre, gestion…).
Les rôles du portail peuvent seulement AJOUTER une ligne (ni lire, ni modifier, ni effacer : migration 0001) ;
la relecture se fait avec la commande `roue_avis`, connexion propriétaire, par l'administrateur technique.
"""
from django.db import models


class Avis(models.Model):
    class Note(models.IntegerChoices):
        UTILE = 1, "Utile"
        A_REVOIR = -1, "À revoir"
        SANS_REPONSE = 0, "Question sans réponse"

    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)
    role = models.CharField(max_length=12)
    page = models.CharField(max_length=80, blank=True)
    question = models.TextField()
    reponse = models.TextField(blank=True)
    sources = models.CharField(max_length=400, blank=True)
    mode = models.CharField(max_length=12, blank=True)  # ia / hors_ligne
    note = models.SmallIntegerField(choices=Note.choices)
    commentaire = models.TextField(blank=True)

    class Meta:
        verbose_name = "avis sur une réponse"
        verbose_name_plural = "avis sur les réponses"
        constraints = [models.CheckConstraint(condition=models.Q(note__in=[-1, 0, 1]), name="roue_avis_note_ok")]
