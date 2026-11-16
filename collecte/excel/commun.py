"""Briques communes des fichiers Excel : signature, lecture sûre, conversions, styles.

Règle d'or : tout ce qui vient d'un fichier déposé est une DONNÉE, jamais une instruction. On ne lit
que des valeurs, on refuse macros, liens externes et objets incorporés, et tout texte écrit dans un
fichier généré est forcé en texte (jamais interprété comme une formule).
"""
import hashlib
import hmac
import io
import re
import unicodedata
import zipfile

from django.conf import settings
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

GABARIT_VERSION = "1.0"
VERSIONS_ACCEPTEES = {"1.0"}
FORMAT_DECLARATION = "GIPAME-DECLARATION"

FEUILLE_DECLARATION = "DECLARATION"
FEUILLE_AJOUTS = "AJOUTS"
FEUILLE_LISEZ = "LISEZ-MOI"
FEUILLE_LISTES = "_LISTES"
FEUILLE_META = "_META"

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
           "septembre", "octobre", "novembre", "décembre"]

# ------------------------------------------------------------------------------ styles
POLICE = "Arial"
FOND_TITRE = PatternFill("solid", fgColor="1F3864")
FOND_ENTETE = PatternFill("solid", fgColor="404040")
FOND_SAISIE = PatternFill("solid", fgColor="FFF2CC")
FOND_GRIS = PatternFill("solid", fgColor="F2F2F2")
FOND_ALERTE = PatternFill("solid", fgColor="F8CBAD")
FINE = Side(style="thin", color="BFBFBF")
BORDURE = Border(left=FINE, right=FINE, top=FINE, bottom=FINE)


def police(gras=False, italique=False, couleur="000000", taille=10):
    return Font(name=POLICE, size=taille, bold=gras, italic=italique, color=couleur)


def style_titre(cellule, taille=14):
    cellule.font = police(gras=True, couleur="FFFFFF", taille=taille)
    cellule.fill = FOND_TITRE
    cellule.alignment = Alignment(vertical="center")


def style_entete(cellule):
    cellule.font = police(gras=True, couleur="FFFFFF")
    cellule.fill = FOND_ENTETE
    cellule.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    cellule.border = BORDURE


# ------------------------------------------------------------------------------ textes
def libelle_mois(d):
    return f"{MOIS_FR[d.month - 1]} {d.year}"


def normaliser(texte):
    """MAJUSCULES, sans accents, espaces et tirets réduits : pour comparer des libellés."""
    s = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[\s\-_/]+", " ", s).strip().upper()


def texte_propre(valeur, max_len=200):
    if valeur is None:
        return ""
    s = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(valeur))
    return re.sub(r"\s+", " ", s).strip()[:max_len]


def ecrire_texte(cellule, valeur):
    """Écrit un texte en le forçant au type chaîne : '=1+1' reste un texte, jamais une formule."""
    cellule.value = texte_propre(valeur, 500)
    cellule.data_type = "s"


def lire_entier(valeur):
    """Renvoie (entier, venait_d_un_texte). Accepte 12, 12.0, '12', '1 200' ; lève ValueError sinon.
    Messages : vide | booleen | decimal | non_numerique."""
    if valeur is None or (isinstance(valeur, str) and not valeur.strip()):
        raise ValueError("vide")
    if isinstance(valeur, bool):
        raise ValueError("booleen")
    if isinstance(valeur, int):
        return valeur, False
    if isinstance(valeur, float):
        if valeur != valeur or valeur in (float("inf"), float("-inf")):
            raise ValueError("non_numerique")
        if abs(valeur - round(valeur)) > 1e-9:
            raise ValueError("decimal")
        return int(round(valeur)), False
    if isinstance(valeur, str):
        s = valeur.replace("\u00a0", "").replace(" ", "").strip()
        if re.fullmatch(r"-?\d+", s):
            return int(s), True
        if re.fullmatch(r"-?\d+[.,]0+", s):
            return int(float(s.replace(",", "."))), True
        if re.fullmatch(r"-?\d+[.,]\d+", s):
            raise ValueError("decimal")
        raise ValueError("non_numerique")
    raise ValueError("non_numerique")


# ------------------------------------------------------------------------------ signature
def _cle():
    return (getattr(settings, "GIPAME_CLE_GABARIT", None) or settings.SECRET_KEY).encode()


def empreinte_codes(codes):
    return hashlib.sha256("\n".join(sorted(codes)).encode()).hexdigest()


def signer(gabarit_version, membre_code, mois, version, codes):
    """HMAC du couple (membre, mois, version de déclaration) et de la liste des produits générés :
    détecte un fichier modifié, un fichier d'un autre membre ou un fichier non généré par le système."""
    message = "|".join([FORMAT_DECLARATION, gabarit_version, membre_code, f"{mois:%Y-%m}", str(version),
                        empreinte_codes(codes)])
    return hmac.new(_cle(), message.encode(), hashlib.sha256).hexdigest()


def signature_valide(signature, gabarit_version, membre_code, mois, version, codes):
    attendue = signer(gabarit_version, membre_code, mois, version, codes)
    return hmac.compare_digest(str(signature or ""), attendue)


# ------------------------------------------------------------------------------ lecture sûre
class FichierInvalide(Exception):
    pass


def lire_classeur_sur(contenu: bytes, taille_max_ko=2048, lecture_seule=False):
    """Ouvre un .xlsx déposé en lecture seule de valeurs, après contrôles de sûreté."""
    if len(contenu) > taille_max_ko * 1024:
        raise FichierInvalide(f"Fichier trop volumineux (maximum {taille_max_ko} Ko).")
    if not zipfile.is_zipfile(io.BytesIO(contenu)):
        raise FichierInvalide("Ce n'est pas un classeur Excel .xlsx (CSV, .xls et .xlsm ne sont pas acceptés).")
    with zipfile.ZipFile(io.BytesIO(contenu)) as z:
        infos = z.infolist()
        noms = [i.filename.lower() for i in infos]
        if sum(i.file_size for i in infos) > 50 * 1024 * 1024 or sum(i.file_size for i in infos) > 200 * max(len(contenu), 1):
            raise FichierInvalide("Fichier refusé : taille décompressée anormale.")
        if any(n.startswith(("xl/vbaproject", "xl/externallinks/", "xl/embeddings/", "xl/activex/")) or n.endswith("vbaproject.bin")
               for n in noms):
            raise FichierInvalide("Fichier refusé : macros, liens externes ou objets incorporés interdits.")
        if "xl/workbook.xml" not in noms:
            raise FichierInvalide("Ce n'est pas un classeur Excel .xlsx valide.")
    try:
        return load_workbook(io.BytesIO(contenu), data_only=True, read_only=lecture_seule)
    except Exception as exc:  # noqa: BLE001 - tout échec de lecture = fichier refusé
        raise FichierInvalide("Fichier Excel illisible ou corrompu.") from exc
