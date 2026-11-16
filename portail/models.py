"""Tables propres au portail (techniques, jamais de donnée de vente).

TentativeConnexion : journal en ajout seulement des connexions réussies ou échouées, base du blocage
temporaire (5 échecs en 15 minutes → compte bloqué 15 minutes) et du rapport d'accès. On n'enregistre
que l'identifiant saisi (normalisé) et l'adresse IP : jamais le mot de passe.
"""
from django.db import models


class TentativeConnexion(models.Model):
    identifiant = models.CharField(max_length=254, db_index=True)  # e-mail saisi, en minuscules
    reussie = models.BooleanField()
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    cree_le = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "tentative de connexion"
        verbose_name_plural = "tentatives de connexion"
