"""Données de démonstration FICTIVES (aucune donnée réelle) : 6 membres dont 3 d'un même groupe,
7 marques, 19 produits, 2 mois de déclarations. Les quantités sont calibrées pour exercer
chaque règle de confidentialité (seuil, dominance, groupe, suppression complémentaire)."""
from datetime import date
from types import SimpleNamespace

from .models import (Boite, ClassementProduit, Concession, Declaration, Energie, GroupeEconomique,
                     LigneVente, Marque, Membre, Modele, Origine, PeriodeAdhesion, Poste, Produit,
                     Segment, Segmentation, TitulairePoste, Utilisateur)

DEBUT = date(2025, 1, 1)

MARQUES = {  # code: (nom, origine)
    "ALPHA-M": "JAPONAISE", "ALPHA-S": "JAPONAISE", "ALPHA-T": "JAPONAISE",
    "BETA": "EUROPEENNE", "GAMMA": "COREENNE", "DELTA": "CHINOISE", "SIGMA": "AUTRES",
}
CONCESSIONS = {"A1": ["ALPHA-M"], "A2": ["ALPHA-S"], "A3": ["ALPHA-T"],
               "B1": ["BETA", "SIGMA"], "B2": ["GAMMA", "SIGMA"], "B3": ["DELTA"]}
PRODUITS = [  # code, marque, modèle, finition, segment, énergie
    ("P01", "ALPHA-M", "Citadine", "LIFE", "AB", "ESSENCE"),
    ("P02", "ALPHA-S", "Mini", "STYLE", "AB", "ESSENCE"),
    ("P03", "ALPHA-T", "Cross", "GL", "SUV", "ESSENCE"),
    ("P04", "BETA", "Compacte", "BASE", "AB", "ESSENCE"),
    ("P05", "GAMMA", "Petite", "EX", "AB", "ESSENCE"),
    ("P06", "DELTA", "Citadine", "PLUS", "AB", "ESSENCE"),
    ("P07", "BETA", "Berline", "CONFORT", "M2", "ESSENCE"),
    ("P08", "GAMMA", "Berline", "LUXE", "M2", "ESSENCE"),
    ("P09", "DELTA", "Executive", "PRESTIGE", "H", "ESSENCE"),
    ("P10", "SIGMA", "Crossover", "STD", "SUV", "DIESEL"),
    ("P11", "SIGMA", "Pick", "4X2", "PU_4X2", "DIESEL"),
    ("P12", "DELTA", "Pick", "4X2", "PU_4X2", "DIESEL"),
    ("P13", "DELTA", "Pick", "4X4", "PU_4X4", "DIESEL"),
    ("P14", "ALPHA-M", "Berline", "SPORT", "M1", "ESSENCE"),
    ("P15", "ALPHA-S", "Berline", "SPORT", "M1", "ESSENCE"),
    ("P16", "ALPHA-T", "Berline", "SPORT", "M1", "ESSENCE"),
    ("P17", "BETA", "Compacte", "PLUS", "M1", "ESSENCE"),
    ("P18", "SIGMA", "Van", "CARGO", "VAN", "DIESEL"),
    ("P19", "DELTA", "Van", "CARGO", "VAN", "DIESEL"),
]
VENTES = {  # membre -> {produit: quantité}
    "A1": {"P01": 100, "P14": 10},
    "A2": {"P02": 80, "P15": 8},
    "A3": {"P03": 70, "P16": 6},
    "B1": {"P04": 40, "P07": 15, "P10": 10, "P11": 12, "P17": 4, "P18": 90},
    "B2": {"P05": 30, "P08": 5, "P10": 5, "P11": 9, "P18": 5},
    "B3": {"P06": 20, "P09": 7, "P12": 14, "P13": 6, "P19": 5},
}
TOTAL_PLEIN = 551  # somme de VENTES


def premier_du_mois(decalage=0, ref=None):
    ref = ref or date.today()
    m = ref.year * 12 + ref.month - 1 + decalage
    return date(m // 12, m % 12 + 1, 1)


def charger_demo(recul=0):
    """recul : décale de N mois en arrière les deux mois déclarés (la démonstration en ligne laisse ainsi
    le mois dernier entièrement à déclarer pour A1 et B3)."""
    mois_plein, mois_partiel = premier_du_mois(-2 - recul), premier_du_mois(-1 - recul)
    d = SimpleNamespace(mois_plein=mois_plein, mois_partiel=mois_partiel, membres={}, produits={}, users={})

    groupe = GroupeEconomique.objects.create(nom="Groupe Alpha (démo)")
    noms = {"A1": "Alpha Motors", "A2": "Alpha Trucks", "A3": "Alpha Auto", "B1": "Beta Distribution",
            "B2": "Gamma Automobiles", "B3": "Delta Véhicules"}
    for code, nom in noms.items():
        m = Membre.objects.create(code=code, raison_sociale=f"{nom} (démo)", groupe=groupe if code[0] == "A" else None)
        PeriodeAdhesion.objects.create(membre=m, date_debut=DEBUT)
        u = Utilisateur(username=f"user_{code.lower()}", role_metier="MEMBRE", membre=m)
        u.set_unusable_password()
        u.save()
        d.membres[code], d.users[code] = m, u

    for nom, role in (("gestionnaire", "GESTION"), ("technicien", "TECHNIQUE"), ("autre_technicien", "TECHNIQUE"),
                      ("president", "BUREAU"), ("vice_president", "BUREAU"), ("delegue_general", "BUREAU")):
        u = Utilisateur(username=nom, role_metier=role)
        u.set_unusable_password()
        u.save()
        d.users[nom] = u
    for poste, nom in (("PRESIDENT", "president"), ("VICE_PRESIDENT", "vice_president"),
                       ("DELEGUE_GENERAL", "delegue_general")):
        TitulairePoste.objects.create(poste=Poste.objects.get(code=poste), utilisateur=d.users[nom], date_debut=DEBUT)

    marques = {c: Marque.objects.create(code=c, nom=c, origine=Origine.objects.get(code=o)) for c, o in MARQUES.items()}
    for membre, liste in CONCESSIONS.items():
        for marque in liste:
            Concession.objects.create(membre=d.membres[membre], marque=marques[marque], date_debut=DEBUT)

    seg = Segmentation.objects.get(code="GIPAME-V1")
    bvm = Boite.objects.get(code="BVM")
    modeles = {}
    for code, marque, modele, finition, segment, energie in PRODUITS:
        mo = modeles.get((marque, modele)) or modeles.setdefault(
            (marque, modele), Modele.objects.create(marque=marques[marque], code=f"{marque}-{modele}".upper(), nom=modele))
        p = Produit.objects.create(
            code=code, modele=mo, finition=finition, energie=Energie.objects.get(code=energie), boite=bvm,
            libelle_affiche=f"{marque} {modele} {finition}", statut="ACTIF",
            motricite="4X4" if finition == "4X4" else "")
        ClassementProduit.objects.create(
            produit=p, segmentation=seg, segment=Segment.objects.get(categorie__segmentation=seg, code=segment))
        d.produits[code] = p

    def declarer(membre, mois):
        decl = Declaration.objects.create(membre=d.membres[membre], mois=mois, version=1)
        for marque in CONCESSIONS[membre]:  # gabarit : tous les produits des marques du membre, pré-remplis à 0
            for code, m, *_ in PRODUITS:
                if m == marque:
                    LigneVente.objects.create(declaration=decl, produit=d.produits[code],
                                              quantite=VENTES[membre].get(code, 0))
        decl.attestation_complete = True
        decl.statut = "SOUMISE"
        decl.save()
        return decl

    for membre in VENTES:
        declarer(membre, mois_plein)
        if membre != "B3":  # B3 n'a pas encore déposé le mois suivant
            declarer(membre, mois_partiel)
    return d


SAISON = {1: 1.10, 2: 0.92, 3: 1.00, 4: 0.95, 5: 0.97, 6: 1.05, 7: 0.93, 8: 0.85, 9: 1.00, 10: 1.04, 11: 1.02, 12: 1.18}


def enrichir_historique(d, nb_mois=22, graine=2026):
    """Ajoute jusqu'à nb_mois de déclarations soumises FICTIVES (saisonnalité + tendance) jusqu'au mois dernier, puis
    calcule les publications : graphiques et tableaux de bord prennent vie pour une démonstration.
    Le mois dernier reste à déclarer pour A1 et B3, afin qu'un visiteur puisse essayer le parcours complet."""
    import random

    from django.db import transaction

    from .contexte import en_role
    from .services import calculer_publication

    hasard = random.Random(graine)
    dernier = premier_du_mois(-1)
    mois = [m for m in (premier_du_mois(-1 - k) for k in reversed(range(nb_mois))) if m >= DEBUT]
    for m in mois:
        t = (m.year - mois[0].year) * 12 + m.month - mois[0].month
        for code, ventes in VENTES.items():
            membre = d.membres[code]
            if (m == dernier and code in ("A1", "B3")) or Declaration.objects.filter(membre=membre, mois=m).exists():
                continue
            with transaction.atomic():
                decl = Declaration.objects.create(membre=membre, mois=m, version=1)
                for marque in CONCESSIONS[code]:
                    for pcode, pm, *_ in PRODUITS:
                        if pm != marque:
                            continue
                        base = ventes.get(pcode, 0)
                        q = 0 if base == 0 else max(0, round(base * SAISON[m.month] * (0.86 + 0.007 * t) * hasard.uniform(0.88, 1.12)))
                        LigneVente.objects.create(declaration=decl, produit=d.produits[pcode], quantite=q)
                decl.attestation_complete = True
                decl.statut = "SOUMISE"
                decl.save()
    for m in mois:
        with transaction.atomic(), en_role("gipame_calcul"):
            calculer_publication(m, statut="PROVISOIRE" if m == dernier else "DEFINITIVE")
    return mois
