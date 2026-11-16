"""Captures d'écran du portail (vérification visuelle, bureau 1280 px et mobile 390 px).

Prérequis : serveur lancé sur http://127.0.0.1:8000 avec le jeu de démonstration et `comptes_demo`,
`pip install playwright && playwright install chromium`.
Usage : python docs/captures/capturer.py   → PNG dans docs/captures/ (écrasés).
Le scénario parcourt les écrans membre, gestion et bureau ; il ne dépose aucun fichier (voir les
tests pour le parcours de dépôt complet).
"""
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
MOT_DE_PASSE = "demo-2026"
ICI = Path(__file__).resolve().parent
PARCOURS = {
    "user_a1@demo.gipame.ci": [("membre_accueil", "/accueil/"), ("membre_assistant", "/declarer/"), ("membre_historique", "/historique/"),
                               ("membre_mon_annee", "/mon-annee/"), ("membre_marche", "/le-marche/"), ("membre_mes_produits", "/mes-produits/"),
                               ("galerie", "/_galerie/")],
    "gestionnaire@demo.gipame.ci": [("gestion_suivi", "/gestion/"), ("gestion_propositions", "/gestion/propositions/"),
                                    ("gestion_catalogue", "/gestion/catalogue/"), ("gestion_demandes", "/gestion/demandes-acces/"),
                                    ("gestion_publications", "/gestion/publications/"), ("gestion_membres", "/gestion/membres/"),
                                    ("gestion_membre", "/gestion/membres/1/"), ("gestion_membre_nouveau", "/gestion/membres/nouveau/")],
    "technicien@demo.gipame.ci": [("admin_comptes", "/administration/comptes/")],
    "president@demo.gipame.ci": [("bureau_marche", "/bureau/"), ("bureau_approbations", "/bureau/approbations/"),
                                 ("bureau_journal", "/bureau/journal/")],
}


async def main():
    async with async_playwright() as p:
        navigateur = await p.chromium.launch()
        for nom, largeur in (("bureau", 1280), ("mobile", 390)):
            contexte = await navigateur.new_context(viewport={"width": largeur, "height": 900}, device_scale_factor=2)
            page = await contexte.new_page()
            erreurs = []
            page.on("console", lambda m: erreurs.append(m.text) if m.type == "error" else None)
            await page.goto(f"{BASE}/connexion/")
            await page.screenshot(path=ICI / f"compte_connexion_{nom}.png", full_page=True)
            for slug, url in (("public_aide", "/aide/"), ("public_confidentialite", "/confidentialite/")):
                await page.goto(BASE + url)
                await page.screenshot(path=ICI / f"{slug}_{nom}.png", full_page=True)
            for utilisateur, ecrans in PARCOURS.items():
                await page.goto(f"{BASE}/connexion/")
                await page.fill("input[name=username]", utilisateur)
                await page.fill("input[name=password]", MOT_DE_PASSE)
                await page.click("button[type=submit]")
                await page.wait_for_load_state("networkidle")
                for slug, url in ecrans:
                    reponse = await page.goto(BASE + url)
                    await page.wait_for_timeout(500)
                    await page.screenshot(path=ICI / f"{slug}_{nom}.png", full_page=True)
                    print(nom, reponse.status, url)
                await page.goto(f"{BASE}/connexion/")  # la déconnexion se fait en POST ; on repart d'une session neuve
                await contexte.clear_cookies()
            if erreurs:
                print("ERREURS CONSOLE :", erreurs)
            await contexte.close()
        await navigateur.close()


if __name__ == "__main__":
    asyncio.run(main())
