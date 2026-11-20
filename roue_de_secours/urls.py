from django.urls import path

from . import vues

app_name = "roue_de_secours"

urlpatterns = [
    path("question/", vues.question, name="question"),
    path("avis/", vues.avis, name="avis"),
]
