"""
Génère les logos « Observatoire GIPAME » (fichiers SVG autonomes, texte converti en tracés).

Usage : python docs/identite/generer_logos.py
Sorties : docs/identite/logos/<piste>/{icone,icone-mono,bloc,bloc-inverse,bloc-mono}.svg
          + planche_logos.html (comparaison des pistes, à ouvrir dans un navigateur).

Les couleurs sont celles de la charte (voir portail/static/portail/css/tokens.css).
Police : Inter (OFL), lue dans /usr/share/fonts si présente ; sinon le texte reste du <text> SVG.
"""
from pathlib import Path

NUIT = "#0B1238"
PETROLE = "#246A90"
BLANC = "#FFFFFF"

ICI = Path(__file__).resolve().parent
SORTIE = ICI / "logos"
POLICES = Path("/usr/share/fonts/opentype/inter")


# ---------------------------------------------------------------- texte → tracés
def texte_en_tracés(texte, police, taille, interlettre=0.0):
    """Retourne (chemin SVG, largeur) du texte, origine à la ligne de base, en unités utilisateur."""
    try:
        from fontTools.pens.svgPathPen import SVGPathPen
        from fontTools.pens.transformPen import TransformPen
        from fontTools.ttLib import TTFont
    except ImportError:
        return None, None
    fichier = POLICES / police
    if not fichier.exists():
        return None, None
    fonte = TTFont(fichier)
    upm = fonte["head"].unitsPerEm
    cmap = fonte.getBestCmap()
    glyphes = fonte.getGlyphSet()
    hmtx = fonte["hmtx"]
    echelle = taille / upm
    x = 0.0
    morceaux = []
    for car in texte:
        nom = cmap.get(ord(car))
        if nom is None:
            x += taille * 0.3
            continue
        pen = SVGPathPen(glyphes)
        glyphes[nom].draw(TransformPen(pen, (echelle, 0, 0, -echelle, x, 0)))
        d = pen.getCommands()
        if d:
            morceaux.append(d)
        x += hmtx[nom][0] * echelle + interlettre
    return " ".join(morceaux), x - interlettre


# ---------------------------------------------------------------- les quatre icônes (viewBox 0 0 64 64)
def lunette(c1, c2, fond=None):
    return f"""
<path d="M53.2 44.2 A 24 24 0 1 1 44.2 10.8" fill="none" stroke="{c1}" stroke-width="6" stroke-linecap="round"/>
<path d="M17 42 C 25 42, 27 31, 34 30 S 44 23, 52 15" fill="none" stroke="{c2}" stroke-width="5.5" stroke-linecap="round"/>
<circle cx="53" cy="14" r="4.5" fill="{c2}"/>"""


def horizon(c1, c2, fond=None):
    return f"""
<path d="M5 46 A 27 27 0 0 1 59 46" fill="none" stroke="{c1}" stroke-width="5.5" stroke-linecap="round"/>
<path d="M15 46 A 17 17 0 0 1 49 46" fill="none" stroke="{c2}" stroke-width="4.5" stroke-linecap="round"/>
<circle cx="32" cy="46" r="5" fill="{c1}"/>
<path d="M5 56 H 59" stroke="{c1}" stroke-width="5.5" stroke-linecap="round"/>"""


def monogramme(c1, c2, fond=None):
    # carré nuit, anneau blanc ouvert à droite, barre pétrole : « O » et « G » en un signe
    blanc = BLANC if fond is None else fond
    return f"""
<rect x="0" y="0" width="64" height="64" rx="14" fill="{c1}"/>
<path d="M47.4 38.5 A 17 17 0 1 1 47.4 25.5" fill="none" stroke="{blanc}" stroke-width="7" stroke-linecap="round"/>
<path d="M33 32 H 49" stroke="{c2 if c2 != c1 else blanc}" stroke-width="7" stroke-linecap="round"/>"""


def jauge(c1, c2, fond=None, ident="g"):
    return f"""
<defs><linearGradient id="{ident}" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{c1}"/><stop offset="1" stop-color="{c2}"/></linearGradient></defs>
<path d="M9.45 46.2 A 24 24 0 1 1 54.55 46.2" fill="none" stroke="url(#{ident})" stroke-width="7" stroke-linecap="round"/>
<path d="M32 38 L 42.5 20.5" stroke="{c1}" stroke-width="4.5" stroke-linecap="round"/>
<circle cx="32" cy="38" r="5" fill="{c1}"/><circle cx="32" cy="38" r="2" fill="{BLANC if fond is None else fond}"/>"""


def jauge_carre(c1, c2, fond=None, ident="gc"):
    """Jauge sur carré arrondi (fond c1). Sur fond nuit : cadran clair → c2, aiguille claire."""
    clair = BLANC if fond is None else fond
    return f"""
<defs><linearGradient id="{ident}" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{c2}"/><stop offset="1" stop-color="{clair}"/></linearGradient></defs>
<rect x="0" y="0" width="64" height="64" rx="14" fill="{c1}"/>
<path d="M13.2 44.4 A 20 20 0 1 1 50.8 44.4" fill="none" stroke="url(#{ident})" stroke-width="6" stroke-linecap="round"/>
<path d="M32 38 L 41 23" stroke="{clair}" stroke-width="4" stroke-linecap="round"/>
<circle cx="32" cy="38" r="4.5" fill="{clair}"/><circle cx="32" cy="38" r="1.8" fill="{c1}"/>"""


PISTES = {
    "1-lunette": ("La lunette", lunette),
    "2-horizon": ("L'horizon", horizon),
    "3-monogramme": ("Le monogramme", monogramme),
    "4-jauge": ("La jauge", jauge),
    "5-jauge-carre": ("La jauge encadrée", jauge_carre),
}


def svg(largeur, hauteur, contenu, fond=None, titre=""):
    rect = f'<rect width="{largeur}" height="{hauteur}" fill="{fond}"/>' if fond else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largeur} {hauteur}" width="{largeur}" height="{hauteur}" role="img" aria-label="{titre}">'
            f"{rect}{contenu}\n</svg>\n")


def icone(dessin, c1, c2, fond=None):
    return svg(64, 64, dessin(c1, c2, fond), titre="Observatoire GIPAME")


def bloc(dessin, c1, c2, c_texte1, c_texte2, fond=None, c_ame=None):
    """Bloc-marque horizontal : icône 48 px + « Observatoire » / « GIPAME »."""
    d1, l1 = texte_en_tracés("Observatoire", "Inter-SemiBold.otf", 26)
    c_ame = c_ame or c_texte2
    d2, l2 = texte_en_tracés("GIP", "Inter-Bold.otf", 12.5, interlettre=2.4)
    d3, l3 = texte_en_tracés("AME", "Inter-Bold.otf", 12.5, interlettre=2.4)
    x0 = 72
    if d1 is None:  # repli : texte SVG (nécessite Inter côté lecteur)
        t = (f'<text x="{x0}" y="31" font-family="Inter, Arial, sans-serif" font-weight="600" font-size="26" fill="{c_texte1}">Observatoire</text>'
             f'<text x="{x0}" y="50" font-family="Inter, Arial, sans-serif" font-weight="700" font-size="12.5" letter-spacing="2.4" fill="{c_texte2}">GIPAME</text>')
        largeur = x0 + 170
    else:
        t = (f'<path transform="translate({x0} 31)" d="{d1}" fill="{c_texte1}"/>'
             f'<path transform="translate({x0 + 1} 50)" d="{d2}" fill="{c_texte2}"/>'
             f'<path transform="translate({x0 + 1 + l2 + 2.4} 50)" d="{d3}" fill="{c_ame}"/>')
        largeur = round(x0 + max(l1, l2 + l3 + 2.4) + 4)
    ic = f'<g transform="translate(2 2) scale(0.9375)">{dessin(c1, c2, fond)}</g>'
    return svg(largeur, 64, ic + t, fond=fond, titre="Observatoire GIPAME")


def main():
    for cle, (nom, dessin) in PISTES.items():
        dossier = SORTIE / cle
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / "icone.svg").write_text(icone(dessin, NUIT, PETROLE), encoding="utf-8")
        (dossier / "icone-mono.svg").write_text(icone(dessin, NUIT, NUIT), encoding="utf-8")
        (dossier / "icone-inverse.svg").write_text(icone(dessin, BLANC, BLANC, fond=NUIT) if cle not in ("3-monogramme", "5-jauge-carre")
                                                   else icone(dessin, BLANC, PETROLE, fond=NUIT), encoding="utf-8")
        (dossier / "bloc.svg").write_text(bloc(dessin, NUIT, PETROLE, NUIT, NUIT, c_ame=PETROLE), encoding="utf-8")
        (dossier / "bloc-mono.svg").write_text(bloc(dessin, NUIT, NUIT, NUIT, NUIT), encoding="utf-8")
        (dossier / "bloc-inverse.svg").write_text(bloc(dessin, BLANC, "#7FC4E6", BLANC, BLANC, fond=NUIT, c_ame="#7FC4E6") if cle not in ("3-monogramme", "5-jauge-carre")
                                                  else bloc(dessin, BLANC, PETROLE, BLANC, BLANC, fond=NUIT, c_ame="#7FC4E6"), encoding="utf-8")
        print("écrit :", dossier)


if __name__ == "__main__":
    main()
