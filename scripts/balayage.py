"""Balayage automatique de l'application dans toutes ses variations (navigateur réel, Playwright).

Pour chaque profil (membre, autre membre, gestion, bureau, administration), sur ordinateur et sur téléphone,
en mode clair et en mode sombre, le script ouvre toutes les pages accessibles depuis le menu, puis vérifie :
  - la page répond sans erreur (pas de 4xx/5xx) ;
  - aucune erreur JavaScript ;
  - rien ne déborde horizontalement (pas de défilement latéral sur téléphone) ;
  - un membre ne voit JAMAIS le nom d'un autre membre (non-fuite) ;
  - chaque page a un titre <h1> et pas d'image sans texte alternatif.
Il produit un rapport (balayage/RAPPORT.md) et une capture par page et par variation.

Usage (environnement activé, `pip install -r requirements-dev.txt` et `playwright install chromium`) :
    python scripts/balayage.py                                              # démonstration en ligne
    python scripts/balayage.py --adresse http://127.0.0.1:8000              # serveur local (jeu seed_demo + comptes_demo)
    python scripts/balayage.py --rapide                                     # ordinateur + mode clair seulement

Il ne modifie rien : il se contente de lire les pages (aucun dépôt, aucun envoi de formulaire hormis la connexion).
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

MOT_DE_PASSE = "demo-2026"
PROFILS = {
    "membre_A1": ("user_a1@demo.gipame.ci", "Alpha Motors"),
    "membre_B1": ("user_b1@demo.gipame.ci", "Beta Distribution"),
    "gestion": ("gestionnaire@demo.gipame.ci", None),
    "bureau": ("president@demo.gipame.ci", None),
    "administration": ("technicien@demo.gipame.ci", None),
}
MEMBRES = ["Alpha Motors", "Alpha Trucks", "Alpha Auto", "Beta Distribution", "Gamma Automobiles", "Delta Véhicules"]
ECRANS = {"ordinateur": {"width": 1366, "height": 768}, "telephone": {"width": 390, "height": 844}}
PAGES_PUBLIQUES = ["/", "/connexion/", "/aide/", "/confidentialite/", "/mot-de-passe-oublie/"]
A_EVITER = ("/deconnexion/", "/export", "/gabarit/", "/action/", "/rappels/", "/admin/")


async def verifier_page(page, url, profil, propre_nom):
    constats = []
    reponse = await page.goto(url, wait_until="networkidle")
    if reponse is None or reponse.status >= 400:
        constats.append(f"statut HTTP {reponse.status if reponse else 'aucun'}")
        return constats
    await page.wait_for_timeout(250)
    if await page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
        largeur = await page.evaluate("document.documentElement.scrollWidth")
        constats.append(f"débordement horizontal ({largeur}px pour {page.viewport_size['width']}px)")
    if not await page.query_selector("h1"):
        constats.append("aucun titre <h1>")
    sans_alt = await page.evaluate("[...document.images].filter(i => !i.hasAttribute('alt')).length")
    if sans_alt:
        constats.append(f"{sans_alt} image(s) sans attribut alt")
    if propre_nom:  # non-fuite : un membre ne voit que son propre nom
        texte = await page.inner_text("body")
        for autre in MEMBRES:
            if autre != propre_nom and autre in texte:
                constats.append(f"FUITE POSSIBLE : « {autre} » visible par {profil}")
    return constats


async def liens_du_menu(page, base):
    hrefs = await page.eval_on_selector_all("nav a[href], .nav a[href], header a[href]", "els => els.map(e => e.getAttribute('href'))")
    vus = []
    for h in hrefs:
        if not h or h.startswith(("#", "mailto:", "http")) or any(x in h for x in A_EVITER):
            continue
        u = urljoin(base, h)
        if urlparse(u).netloc == urlparse(base).netloc and u not in vus:
            vus.append(u)
    return vus


async def balayer(base, sortie, rapide):
    from playwright.async_api import async_playwright
    lignes, nb_pages, nb_problemes = [], 0, 0
    variations = [("ordinateur", "light")] if rapide else [(e, t) for e in ECRANS for t in ("light", "dark")]
    async with async_playwright() as p:
        navigateur = await p.chromium.launch()
        for ecran, theme in variations:
            for profil in ["public", *PROFILS]:
                contexte = await navigateur.new_context(viewport=ECRANS[ecran], color_scheme=theme)
                page = await contexte.new_page()
                erreurs_js = []
                page.on("pageerror", lambda e: erreurs_js.append(str(e)))
                propre_nom = None
                if profil == "public":
                    urls = [urljoin(base, u) for u in PAGES_PUBLIQUES]
                else:
                    email, propre_nom = PROFILS[profil]
                    await page.goto(urljoin(base, "/connexion/"), wait_until="networkidle")
                    await page.fill("#id_username", email)
                    await page.fill("#id_password", MOT_DE_PASSE)
                    await page.click("form button[type=submit]")
                    await page.wait_for_load_state("networkidle")
                    if "/connexion/" in page.url:
                        lignes.append(f"| {ecran} · {theme} | {profil} | connexion | ❌ connexion refusée |")
                        nb_problemes += 1
                        await contexte.close()
                        continue
                    urls = [page.url, *await liens_du_menu(page, base)]
                for url in dict.fromkeys(urls):
                    erreurs_js.clear()
                    constats = await verifier_page(page, url, profil, propre_nom)
                    constats += [f"erreur JavaScript : {e[:120]}" for e in erreurs_js]
                    chemin = urlparse(url).path
                    nom = re.sub(r"[^a-z0-9]+", "_", chemin.lower()).strip("_") or "accueil"
                    await page.screenshot(path=str(sortie / f"{ecran}_{theme}_{profil}_{nom}.png"), full_page=True)
                    nb_pages += 1
                    nb_problemes += bool(constats)
                    etat = "✅" if not constats else "❌ " + " ; ".join(constats)
                    lignes.append(f"| {ecran} · {theme} | {profil} | `{chemin}` | {etat} |")
                await contexte.close()
        await navigateur.close()
    rapport = sortie / "RAPPORT.md"
    rapport.write_text(
        f"# Balayage de {base}\n\n{nb_pages} pages vérifiées, **{nb_problemes} avec un problème**.\n\n"
        "| Écran · thème | Profil | Page | Résultat |\n|---|---|---|---|\n" + "\n".join(lignes) + "\n", encoding="utf-8")
    print(f"{nb_pages} pages vérifiées, {nb_problemes} avec un problème. Rapport : {rapport}")
    return nb_problemes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--adresse", default="https://observatoire-gipame-demo.onrender.com")
    parser.add_argument("--sortie", default="balayage")
    parser.add_argument("--rapide", action="store_true")
    args = parser.parse_args()
    sortie = Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    sys.exit(1 if asyncio.run(balayer(args.adresse.rstrip("/") + "/", sortie, args.rapide)) else 0)


if __name__ == "__main__":
    main()
