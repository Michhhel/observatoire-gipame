"""Fournisseurs d'IA : lecture des flux (sans réseau), erreurs, bascule automatique sur le mode hors ligne."""
import io
import json
import urllib.error
from unittest import mock

from django.test import SimpleTestCase

from roue_de_secours import fournisseurs as f
from roue_de_secours.conversation import Preparation, flux
from roue_de_secours.connaissances import Section


def flux_sse(*evenements):
    lignes = []
    for e in evenements:
        lignes.append(b"data: " + (e if isinstance(e, bytes) else json.dumps(e).encode()) + b"\n")
        lignes.append(b"\n")
    reponse = io.BytesIO(b"".join(lignes))
    reponse.__enter__ = lambda *a: reponse
    reponse.__exit__ = lambda *a: None
    return reponse


REQUETE = f.Requete("fixe", "variable", [{"role": "user", "texte": "Bonjour ?"}])
PASSAGE = Section("essai", "Fiche d'essai", "Section", "Texte de la fiche.", frozenset({"TOUS"}), "/aide/", (), False)


class Lecture(SimpleTestCase):
    def test_anthropic(self):
        sse = flux_sse({"type": "message_start", "message": {"usage": {"input_tokens": 12}}},
                       {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Bon"}},
                       {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "jour."}},
                       {"type": "message_delta", "usage": {"output_tokens": 3}}, {"type": "message_stop"})
        with mock.patch("urllib.request.urlopen", return_value=sse) as appel:
            p = f.Anthropic("modele-essai", "cle")
            self.assertEqual("".join(p.diffuser(REQUETE)), "Bonjour.")
        corps = json.loads(appel.call_args[0][0].data)
        self.assertEqual(corps["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(corps["messages"], [{"role": "user", "content": "Bonjour ?"}])
        self.assertEqual(p.usage, {"input_tokens": 12, "output_tokens": 3})

    def test_compatible_openai(self):
        sse = flux_sse({"choices": [{"delta": {"content": "Sa"}}]}, {"choices": [{"delta": {"content": "lut"}}]}, b"[DONE]")
        with mock.patch("urllib.request.urlopen", return_value=sse) as appel:
            texte = "".join(f.CompatibleOpenAI("m", "cle", "https://api.exemple.ci/v1").diffuser(REQUETE))
        self.assertEqual(texte, "Salut")
        self.assertTrue(appel.call_args[0][0].full_url.endswith("/v1/chat/completions"))
        self.assertIn("RoueDeSecours", appel.call_args[0][0].get_header("User-agent"))

    def test_gemini_temperature_par_defaut_reflexion_basse(self):
        from django.test import override_settings
        url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        sse = flux_sse({"choices": [{"delta": {"content": "Bonjour"}}]}, b"[DONE]")
        with override_settings(ROUE_DE_SECOURS={"URL_API": url, "CLE_API": "cle", "MODELE": "gemini-flash"}), \
                mock.patch("urllib.request.urlopen", return_value=sse) as appel:
            from roue_de_secours.fournisseurs import construire
            p = construire()
            self.assertIsInstance(p, f.CompatibleOpenAI)
            self.assertEqual("".join(p.diffuser(REQUETE)), "Bonjour")
        requete_http = appel.call_args[0][0]
        corps = json.loads(requete_http.data)
        self.assertEqual(requete_http.full_url, "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions")
        self.assertNotIn("temperature", corps)
        self.assertEqual(corps["reasoning_effort"], "low")
        self.assertGreaterEqual(corps["max_tokens"], 4096)
        self.assertEqual(requete_http.get_header("Authorization"), "Bearer cle")

    def test_modele_retire_donne_une_erreur_lisible(self):
        erreur = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b'{"error":"model not found"}'))
        with mock.patch("urllib.request.urlopen", side_effect=erreur), self.assertLogs("roue_de_secours", "ERROR"):
            with self.assertRaises(f.ErreurFournisseur) as ctx:
                list(f.Anthropic("ancien-modele", "cle").diffuser(REQUETE))
        self.assertIn("modèle", ctx.exception.raison)

    def test_sans_cle_pas_d_appel(self):
        with mock.patch("urllib.request.urlopen") as appel, self.assertRaises(f.ErreurFournisseur):
            list(f.Anthropic("m", "").diffuser(REQUETE))
        appel.assert_not_called()

    def test_messages_alternes(self):
        m = f._messages_alternes([{"role": "assistant", "texte": "a"}, {"role": "user", "texte": "b"},
                                  {"role": "user", "texte": "c"}, {"role": "assistant", "texte": ""}])
        self.assertEqual(m, [{"role": "user", "content": "b\n\nc"}])


class Bascule(SimpleTestCase):
    def evenements(self, fournisseur):
        prep = Preparation(f.Requete("fixe", "var", [], [PASSAGE], {}), [{"titre": "Fiche d'essai", "lien": "/aide/"}], False)
        return [json.loads(l) for l in flux(prep, fournisseur)]

    def test_service_indisponible_bascule_sur_les_fiches(self):
        class Panne(f.Fournisseur):
            nom = "panne"

            def diffuser(self, requete):
                raise f.ErreurFournisseur("service d'IA injoignable")
                yield  # noqa

        ev = self.evenements(Panne())
        self.assertEqual(ev[0]["t"], "sources")
        self.assertIn({"t": "mode", "mode": "hors_ligne", "raison": "service d'IA injoignable"}, ev)
        self.assertIn("Texte de la fiche.", "".join(e.get("d", "") for e in ev))
        self.assertEqual(ev[-1], {"t": "fin", "mode": "hors_ligne", "sans_fiche": False})

    def test_coupure_en_cours_de_reponse(self):
        class Coupure(f.Fournisseur):
            nom = "coupure"

            def diffuser(self, requete):
                yield "Début"
                raise f.ErreurFournisseur("le service d'IA a interrompu la réponse")

        ev = self.evenements(Coupure())
        self.assertEqual([e["t"] for e in ev], ["sources", "texte", "erreur", "fin"])

    def test_hors_ligne_un_seul_passage_et_renvois(self):
        autre = Section("essai", "Fiche d'essai", "Autre section", "Autre texte.", frozenset({"TOUS"}), "", (), False)
        prep = Preparation(f.Requete("fixe", "var", [], [PASSAGE, autre], {}), [], False)
        texte = "".join(json.loads(l).get("d", "") for l in flux(prep, f.HorsLigne()))
        self.assertIn("Texte de la fiche.", texte)
        self.assertNotIn("Autre texte.", texte)
        self.assertIn("« Autre section »", texte)

    def test_hors_ligne_sans_passage(self):
        prep = Preparation(f.Requete("fixe", "var", [], [], {"contact": "le secrétariat du GIPAME"}), [], True)
        texte = "".join(json.loads(l).get("d", "") for l in flux(prep, f.HorsLigne()))
        self.assertIn("pas trouvé", texte)
