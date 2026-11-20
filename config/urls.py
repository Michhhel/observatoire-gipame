"""Routes du projet : l'administration Django (réservée au rôle TECHNIQUE, voir middleware) et le portail."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("roue-de-secours/", include("roue_de_secours.urls")),  # assistant d'aide (module autonome)
    path("", include("portail.urls")),
]

handler403 = "portail.vues.compte.acces_refuse"
handler404 = "portail.vues.compte.introuvable"
handler500 = "portail.vues.compte.erreur_serveur"
