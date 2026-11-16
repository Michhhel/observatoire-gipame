"""Ancien fichier annuel FICTIF au format réel (feuille « MTM <année> », mêmes colonnes, mêmes lignes de structure).

Sert à essayer la reprise de l'historique sans toucher au vrai fichier : il contient volontairement les défauts
connus de l'ancien fichier (sous-total mal libellé, doublon, valeur négative, texte dans une cellule numérique,
lignes de totaux et de récapitulatif).
"""
import io

from openpyxl import Workbook


def fabriquer_historique(annee=2024, decalage=0):
    """Ancien fichier annuel : mêmes colonnes et mêmes lignes de structure que le vrai, y compris ses défauts
    (sous-total mal libellé, doublon, valeur négative, texte dans une cellule numérique, lignes de totaux)."""
    wb = Workbook()
    ws = wb.active
    ws.title = f"MTM {annee}"
    ws["A1"] = f"ANNEE {annee} - "
    ws["A2"] = "VENTES MENSUELLES GIPAME TOUTES CATEGORIES ET ORIGINES"
    entetes = ["ORIGINES", "MARQUES", "MODELES", "DISTRIBUTEURS", "CYLINDREES", "ENERGIES", "CHEVAUX", "BVA ou BVM",
               "CHARGES UTILES", *range(1, 13), "CUMUL", "PART EN %"]
    for i, v in enumerate(entetes, 1):
        ws.cell(3, i, v)
    lignes = [
        ("S", "CATEGORIES VEHICULES PARTICULIERS (VP = AB + M1 + M2 + H)"),
        ("S", "SEGMENT A/B"),
        ("P", "TOYOTA", "STARLET 1.5 ESS STYLE 4-AT", "CFAO MOTORS", "1,5L", "ESS", 106, "BVA", None, [10, 12, 15]),
        ("P", "TOYOTA", "STARLET 1.5 PETROL LIFE 5MT", "CFAO MOTORS", "1.5 L", "PETROL", 0, "BVM", None, [3, 0, 4]),
        ("P", "SUZUKI", "ALTO 800 MC1", "SOCIDA", "0.8L", "ESS", None, "BVM", None, [5, -2, "x"]),
        ("P", "TOYOTA", "STARLET 1.5 ESS STYLE 4-AT", "CFAO MOTORS", "1,5L", "ESS", 106, "BVA", None, [1, None, 2]),  # doublon
        ("P", "NISSAN", "SOUS-TOTAL A/B", "ATC COMAFRIQUE", None, None, None, None, None, [999, 999, 999]),  # à ignorer
        ("S", "TOTAL ORIGINE JAPONAIS - SEGMENT A / B", [9999]),
        ("P", "VOLKSWAGEN", "POLO 1.0 TSI", "SIFF", "1.0L", "ESS", 95, "BVA", None, [7, 8, 9]),
        ("S", "TOTAL ORIGINE EUROPEENNE - SEGMENT A / B", [9999]),
        ("S", "SEGMENT SUV"),
        ("P", "HYUNDAI", "TUCSON 2.0 DIESEL", "SMT CI", "2.0L", "DIESEL", 120, "BVA", None, [4, 0, 0]),
        ("S", "TOTAL ORIGINE COREENNE - SEGMENT SUV", [9999]),
        ("S", "CATEGORIES VEHICULES VAN"),
        ("P", "RENAULT", "KANGOO VAN", "SOCIDA", "1.5L", "DIESEL", None, "BVM", 650, [0, 0, 0]),
        ("S", "TOTAL ORIGINE EUROPEENNE - CATEGORIE VAN", [9999]),
        ("S", "CFAO MOTORS"),
        ("S", "CUMUL GLOBAL 2024"),
    ]
    r = 4
    for ligne in lignes:
        if ligne[0] == "S":
            ws.cell(r, 1, ligne[1])
            for k, v in enumerate(ligne[2] if len(ligne) > 2 else []):
                ws.cell(r, 10 + k, v)
        else:
            _, marque, libelle, distributeur, cyl, ene, chev, boite, charge, valeurs = ligne
            for col, v in enumerate((None, marque, libelle, distributeur, cyl, ene, chev, boite, charge), 1):
                ws.cell(r, col, v)
            for k, v in enumerate(valeurs):
                ws.cell(r, 10 + k, (v + decalage) if isinstance(v, int) and v > 0 else v)
        r += 1
    sortie = io.BytesIO()
    wb.save(sortie)
    return sortie.getvalue()
