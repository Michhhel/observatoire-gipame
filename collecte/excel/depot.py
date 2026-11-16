"""Dépôt d'un fichier Excel de déclaration.

Deux niveaux de problèmes :
- ERREUR : bloquante, rien n'est enregistré (sauf la trace du dépôt) ;
- ALERTE : le fichier est accepté, mais le membre est invité à vérifier ou commenter.

À exécuter dans le contexte du membre (rôle gipame_membre) : toutes les lectures et écritures passent
alors par la sécurité par ligne. La validation côté serveur est la seule qui compte : les protections
du fichier Excel ne sont qu'un confort.
"""
import hashlib
from dataclasses import asdict, dataclass, field
from datetime import date

from django.db import DatabaseError, IntegrityError, connection, transaction

from ..contexte import garantir_contexte_membre, parametres_publics
from ..models import Boite, Concession, Declaration, DepotFichier, Energie, LigneVente, Marque, Modele, Produit
from . import commun as c

COL_AJ = {"marque": 1, "modele": 2, "finition": 3, "energie": 4, "boite": 5, "cylindree": 6, "puissance": 7,
          "charge": 8, "ptac": 9, "places": 10, "motricite": 11, "segment": 12, "quantite": 13, "note": 14}
MAX_ALERTES_PAR_TYPE = 25


@dataclass
class Probleme:
    gravite: str  # ERREUR | ALERTE
    code: str
    message: str
    feuille: str = ""
    ligne: int | None = None

    def __str__(self):
        lieu = f" [{self.feuille}{'!' + str(self.ligne) if self.ligne else ''}]" if self.feuille else ""
        return f"{self.gravite:6s} {self.code}{lieu} : {self.message}"


@dataclass
class RapportDepot:
    problemes: list = field(default_factory=list)
    declaration_id: int | None = None
    version: int | None = None
    mois: date | None = None
    statut_declaration: str = ""
    nb_lignes: int = 0
    total_unites: int = 0
    nb_ajouts: int = 0
    empreinte: str = ""
    resultat: str = "REJETE"
    depot_id: int | None = None

    def ajouter(self, gravite, code, message, feuille="", ligne=None):
        self.problemes.append(Probleme(gravite, code, message, feuille, ligne))

    @property
    def erreurs(self):
        return [p for p in self.problemes if p.gravite == "ERREUR"]

    @property
    def alertes(self):
        return [p for p in self.problemes if p.gravite == "ALERTE"]

    @property
    def ok(self):
        return not self.erreurs

    def en_texte(self):
        tete = (f"Résultat : {self.resultat} | déclaration {self.declaration_id or '-'} "
                f"(version {self.version or '-'}, {self.statut_declaration or 'non enregistrée'}) | "
                f"{self.nb_lignes} lignes, {self.total_unites} unités, {self.nb_ajouts} ajout(s)")
        return "\n".join([tete, *[str(p) for p in self.problemes]])


# ------------------------------------------------------------------------------ point d'entrée
def deposer_declaration(contenu: bytes, nom_fichier: str, membre, utilisateur=None, soumettre=False, motif_portail=None):
    """`motif_portail` : motif de correction saisi dans la page du portail ; il remplace celui du fichier
    s'il est fourni (la cellule G4 reste utilisable pour un dépôt par un autre canal)."""
    rapport = RapportDepot(empreinte=hashlib.sha256(contenu).hexdigest())
    try:
        with transaction.atomic():
            garantir_contexte_membre(membre.id)
            params = parametres_publics()
            wb = c.lire_classeur_sur(contenu, int(params["import_taille_max_ko"]))
            meta = _lire_meta(wb, rapport)
            if meta is not None:
                _traiter(wb, meta, membre, utilisateur, soumettre, params, rapport, motif_portail)
            if rapport.erreurs:
                raise _Rejet()  # annule toute écriture partielle ; la trace est écrite après
    except _Rejet:
        pass
    except c.FichierInvalide as exc:
        rapport.ajouter("ERREUR", "FICHIER", str(exc))
    except IntegrityError as exc:
        rapport.ajouter("ERREUR", "BASE", _message_base(exc))
    if rapport.erreurs:
        rapport.resultat = "REJETE"
        rapport.declaration_id, rapport.statut_declaration = None, ""
    else:
        rapport.resultat = "ACCEPTE_AVEC_ALERTES" if rapport.alertes else "ACCEPTE"
    _tracer(rapport, contenu, nom_fichier, membre, utilisateur)
    return rapport


class _Rejet(Exception):
    pass


def soumettre_declaration(declaration_id, membre, attestation=False, motif=None, commentaire=None):
    """Soumet un brouillon déjà déposé (le portail l'appelle après lecture du rapport).
    `attestation=True` : le membre a coché « déclaration complète et exacte » sur le portail ;
    `motif` : motif de correction saisi sur le portail (prioritaire sur celui du fichier) ;
    `commentaire` : explications du membre sur les alertes (texte libre, jamais publié)."""
    with transaction.atomic():
        garantir_contexte_membre(membre.id)
        decl = Declaration.objects.get(pk=declaration_id, membre=membre)
        champs = ["statut", "attestation_complete", "modifie_le"]
        if attestation:
            decl.attestation_complete = True
        if motif is not None and motif.strip():
            decl.motif_correction = motif.strip()
            champs.append("motif_correction")
        if commentaire is not None:
            decl.commentaire_portail = commentaire.strip()
            champs.append("commentaire_portail")
        decl.statut = "SOUMISE"
        decl.save(update_fields=champs)
    return decl


# ------------------------------------------------------------------------------ lecture
def _message_base(exc):
    diag = getattr(exc.__cause__, "diag", None)
    return (getattr(diag, "message_primary", None) or str(exc)).strip()


def _lire_meta(wb, rapport):
    for nom in (c.FEUILLE_DECLARATION, c.FEUILLE_AJOUTS, c.FEUILLE_META, c.FEUILLE_LISTES):
        if nom not in wb.sheetnames:
            rapport.ajouter("ERREUR", "STRUCTURE", f"Onglet « {nom} » absent : utilisez le gabarit téléchargé sur le "
                            "portail, sans renommer ni supprimer d'onglet.")
            return None
    ws = wb[c.FEUILLE_META]
    meta = {c.texte_propre(ws.cell(r, 1).value): c.texte_propre(ws.cell(r, 2).value, 500)
            for r in range(1, min(ws.max_row, 100) + 1) if ws.cell(r, 1).value}
    if meta.get("format") != c.FORMAT_DECLARATION:
        rapport.ajouter("ERREUR", "STRUCTURE", "Ce fichier n'est pas un gabarit de déclaration GIPAME.")
        return None
    if meta.get("gabarit_version") not in c.VERSIONS_ACCEPTEES:
        rapport.ajouter("ERREUR", "VERSION_GABARIT", "Version du gabarit non prise en charge : téléchargez le gabarit du mois.")
        return None
    return meta


def _erreur_quantite(code_erreur, qmax):
    return {"vide": "Quantité manquante : saisissez 0 si vous n'avez rien vendu.",
            "booleen": "La quantité doit être un nombre entier.",
            "decimal": "La quantité doit être un nombre entier (pas de décimale).",
            "non_numerique": "La quantité n'est pas un nombre.",
            "negative": "La quantité ne peut pas être négative.",
            "trop_grande": f"Quantité invraisemblable (maximum {qmax} par ligne et par mois)."}[code_erreur]


def _lire_quantite(valeur, qmax):
    """(entier, venait_d_un_texte) ou lève ValueError(code)."""
    q, texte = c.lire_entier(valeur)
    if q < 0:
        raise ValueError("negative")
    if q > qmax:
        raise ValueError("trop_grande")
    return q, texte


def _traiter(wb, meta, membre, utilisateur, soumettre, params, rapport, motif_portail=None):
    qmax = int(params["import_quantite_max"])
    ws_listes = wb[c.FEUILLE_LISTES]
    codes_attendus = [c.texte_propre(ws_listes.cell(r, 4).value, 60) for r in range(2, ws_listes.max_row + 1)
                      if ws_listes.cell(r, 4).value]
    try:
        mois = date.fromisoformat(meta["mois"])
        version = int(meta["version_declaration"])
    except (KeyError, ValueError):
        rapport.ajouter("ERREUR", "STRUCTURE", "Informations du gabarit illisibles : téléchargez de nouveau le gabarit.")
        return
    if not c.signature_valide(meta.get("signature"), meta["gabarit_version"], meta.get("membre_code", ""), mois, version,
                              codes_attendus):
        rapport.ajouter("ERREUR", "SIGNATURE", "Ce fichier n'a pas été généré par le portail, ou il a été modifié "
                        "(onglets cachés, liste des produits). Téléchargez de nouveau le gabarit.")
        return
    if meta["membre_code"] != membre.code:
        rapport.ajouter("ERREUR", "COMPTE", "Ce fichier n'a pas été généré pour votre compte.")
        return
    rapport.mois, rapport.version = mois, version
    if mois > date.today().replace(day=1):
        rapport.ajouter("ERREUR", "MOIS_FUTUR", "Ce fichier concerne un mois qui n'est pas encore commencé.")
        return

    existantes = list(Declaration.objects.filter(membre=membre, mois=mois).values("id", "version", "statut"))
    brouillon = next((e for e in existantes if e["statut"] == "BROUILLON"), None)
    soumise = next((e for e in existantes if e["statut"] == "SOUMISE"), None)
    attendue = brouillon["version"] if brouillon else max((e["version"] for e in existantes), default=0) + 1
    if version != attendue:
        rapport.ajouter("ERREUR", "GABARIT_PERIME",
                        "Ce gabarit n'est plus à jour (une déclaration plus récente existe pour ce mois) : "
                        "téléchargez de nouveau le gabarit, il contient votre dernière version.")
        return

    # ---- onglet DECLARATION
    ws = wb[c.FEUILLE_DECLARATION]
    premiere, col_code, col_q, col_com = (int(meta[k]) for k in ("premiere_ligne", "colonne_code", "colonne_quantite",
                                                                 "colonne_commentaire"))
    lues, fin = {}, min(ws.max_row, premiere + len(codes_attendus) + 200)
    for r in range(premiere, fin + 1):
        code = c.texte_propre(ws.cell(r, col_code).value, 60)
        if not code:
            continue
        if code.upper() == "TOTAL":
            break
        if code in lues:
            rapport.ajouter("ERREUR", "DOUBLON", f"Le code « {code} » apparaît plusieurs fois.", c.FEUILLE_DECLARATION, r)
            continue
        try:
            q, venait_du_texte = _lire_quantite(ws.cell(r, col_q).value, qmax)
        except ValueError as exc:
            rapport.ajouter("ERREUR", "QUANTITE", _erreur_quantite(str(exc), qmax), c.FEUILLE_DECLARATION, r)
            lues[code] = (r, None, "")
            continue
        if venait_du_texte:
            rapport.ajouter("ALERTE", "NOMBRE_EN_TEXTE", "Nombre saisi comme du texte : converti.", c.FEUILLE_DECLARATION, r)
        lues[code] = (r, q, c.texte_propre(ws.cell(r, col_com).value, 200))

    attendus = set(codes_attendus)
    for code, (r, _q, _com) in lues.items():
        if code not in attendus:
            rapport.ajouter("ERREUR", "LIGNE_AJOUTEE", f"Le code « {code} » ne figure pas dans le gabarit généré : n'ajoutez "
                            "pas de ligne dans cet onglet, utilisez l'onglet AJOUTS.", c.FEUILLE_DECLARATION, r)
    manquants = sorted(attendus - set(lues))
    if manquants:
        noms = dict(Produit.objects.filter(code__in=manquants[:5]).values_list("code", "libelle_affiche"))
        exemples = ", ".join(f"{code} ({noms.get(code, '?')})" for code in manquants[:5])
        rapport.ajouter("ERREUR", "LIGNE_MANQUANTE", f"{len(manquants)} ligne(s) du gabarit ont été supprimées ou modifiées "
                        f"(ex. : {exemples}). Ne supprimez aucune ligne : saisissez 0.", c.FEUILLE_DECLARATION)

    # ---- catalogue modifié depuis le téléchargement
    with connection.cursor() as cur:
        cur.execute("SELECT l_code FROM gipame_lignes_gabarit(%s)", [mois])
        actuels = {ligne[0] for ligne in cur.fetchall()}
    for code, (r, q, _com) in lues.items():
        if code in attendus and code not in actuels and q:
            rapport.ajouter("ERREUR", "PRODUIT_RETIRE", f"Le produit « {code} » a été retiré de votre liste depuis le "
                            "téléchargement : contactez le GIPAME ou téléchargez de nouveau le gabarit.",
                            c.FEUILLE_DECLARATION, r)
    nouveaux = actuels - attendus
    if nouveaux:
        rapport.ajouter("ALERTE", "CATALOGUE_PLUS_RECENT", f"{len(nouveaux)} produit(s) ont été ajoutés à votre liste depuis "
                        "le téléchargement : ils sont considérés à 0. Téléchargez de nouveau le gabarit si vous en avez vendu.")

    # ---- attestation, motif
    def cellule(nom):
        return c.texte_propre(ws[meta[nom]].value, 300)

    attestation = c.normaliser(cellule("cellule_attestation"))
    aucune_vente = c.normaliser(cellule("cellule_aucune_vente"))
    motif = c.texte_propre(motif_portail, 300) or cellule("cellule_motif")
    for nom, valeur in (("attestation", attestation), ("aucune vente", aucune_vente)):
        if valeur not in ("", "OUI", "NON"):
            rapport.ajouter("ERREUR", "REPONSE", f"La réponse « {nom} » doit être OUI ou NON.", c.FEUILLE_DECLARATION)
    quantites = {code: q for code, (_r, q, _com) in lues.items() if q is not None and code in attendus}
    total = sum(quantites.values())

    # ---- ajouts de produits
    ajouts = _lire_ajouts(wb, meta, membre, mois, qmax, params, rapport)
    total_avec_ajouts = total + sum(a["quantite"] for a in ajouts)
    rapport.nb_lignes, rapport.total_unites, rapport.nb_ajouts = len(quantites) + len(ajouts), total_avec_ajouts, len(ajouts)

    if total_avec_ajouts == 0 and aucune_vente != "OUI" and not rapport.erreurs:
        rapport.ajouter("ERREUR", "ZERO_NON_CONFIRME", "Toutes les quantités sont à 0 : si c'est exact, répondez OUI à "
                        "« Aucune vente ce mois-ci ? ».", c.FEUILLE_DECLARATION)
    if aucune_vente == "OUI" and total_avec_ajouts > 0:
        rapport.ajouter("ERREUR", "INCOHERENCE", "Vous indiquez « aucune vente » mais des quantités sont supérieures à 0.",
                        c.FEUILLE_DECLARATION)
    if attendue > 1 and not motif:
        rapport.ajouter("ERREUR", "MOTIF_REQUIS", "Une correction exige un motif (cellule « Motif de la correction »).",
                        c.FEUILLE_DECLARATION)
    if attendue > 1 and soumise:
        courantes = dict(LigneVente.objects.filter(declaration_id=soumise["id"]).values_list("produit__code", "quantite"))
        if not ajouts and all(courantes.get(code, 0) == q for code, q in quantites.items()) and not rapport.erreurs:
            rapport.ajouter("ERREUR", "AUCUNE_MODIFICATION", "Aucune quantité ne diffère de la déclaration soumise.")
    if rapport.erreurs:
        return

    _controles_metier(membre, mois, lues, quantites, total_avec_ajouts, params, rapport, correction=attendue > 1)
    _enregistrer(membre, utilisateur, mois, attendue, brouillon, quantites, ajouts, attestation, aucune_vente, motif,
                 soumettre, rapport)


def _controles_metier(membre, mois, lues, quantites, total, params, rapport, correction):
    """Alertes de vraisemblance (jamais bloquantes) par rapport au mois précédent du même membre."""
    pct, mini = int(params["import_variation_alerte_pct"]), int(params["import_variation_min_unites"])
    precedent_mois = (mois - __import__("datetime").timedelta(days=1)).replace(day=1)
    precedent = dict(LigneVente.objects.filter(
        declaration__membre=membre, declaration__mois=precedent_mois, declaration__statut="SOUMISE",
    ).values_list("produit__code", "quantite"))
    if not precedent:
        return
    designations = dict(Produit.objects.filter(code__in=list(quantites)).values_list("code", "libelle_affiche"))
    nb = 0
    for code, q in quantites.items():
        p = precedent.get(code, 0)
        ligne, _q, commentaire = lues[code]
        if max(p, q) >= mini and abs(q - p) * 100 >= pct * max(p, 1) and not commentaire:
            nb += 1
            if nb <= MAX_ALERTES_PAR_TYPE:
                rapport.ajouter("ALERTE", "VARIATION", f"{designations.get(code, code)} : {p} → {q} par rapport au mois "
                                "précédent. Ajoutez un commentaire si cette variation est normale.", c.FEUILLE_DECLARATION, ligne)
    if nb > MAX_ALERTES_PAR_TYPE:
        rapport.ajouter("ALERTE", "VARIATION", f"... et {nb - MAX_ALERTES_PAR_TYPE} autre(s) variation(s) importante(s).")
    total_prec = sum(precedent.values())
    if not correction and total > 0 and total_prec > 0 and all(q == precedent.get(code, 0) for code, q in quantites.items()):
        rapport.ajouter("ALERTE", "IDENTIQUE", "Toutes les quantités sont identiques à celles du mois précédent : "
                        "vérifiez qu'il ne s'agit pas d'une copie.")
    if total_prec >= mini and total <= total_prec * 0.5:
        rapport.ajouter("ALERTE", "BAISSE_TOTALE", f"Votre total baisse fortement ({total_prec} → {total}).")
    if total >= mini and total >= total_prec * 2 and total_prec > 0:
        rapport.ajouter("ALERTE", "HAUSSE_TOTALE", f"Votre total double ou plus ({total_prec} → {total}).")


# ------------------------------------------------------------------------------ onglet AJOUTS
def _lire_ajouts(wb, meta, membre, mois, qmax, params, rapport):
    ws = wb[c.FEUILLE_AJOUTS]
    premiere, nb_max = int(meta["ajouts_premiere_ligne"]), int(params["import_max_ajouts"])
    marques = {c.normaliser(m.nom): m for m in Marque.objects.filter(concessions__membre=membre).distinct()}
    energies = {c.normaliser(e.code): e for e in Energie.objects.all()}
    boites = {c.normaliser(b.code): b for b in Boite.objects.all()}
    ajouts, vus = [], set()
    for r in range(premiere, premiere + int(meta["ajouts_max"])):
        valeurs = {k: ws.cell(r, col).value for k, col in COL_AJ.items()}
        if all(v is None or str(v).strip() == "" for v in valeurs.values()):
            continue
        if len(ajouts) >= nb_max:
            rapport.ajouter("ERREUR", "TROP_D_AJOUTS", f"Maximum {nb_max} nouveaux produits par fichier.", c.FEUILLE_AJOUTS, r)
            break
        nb_erreurs_avant = len(rapport.erreurs)

        def erreur(code, message):
            rapport.ajouter("ERREUR", code, message, c.FEUILLE_AJOUTS, r)

        marque = marques.get(c.normaliser(valeurs["marque"]))
        if not marque:
            erreur("AJOUT_MARQUE", "Marque absente de votre liste de marques (choisissez dans la liste déroulante).")
        nom_modele, finition = c.texte_propre(valeurs["modele"], 120), c.texte_propre(valeurs["finition"], 120).upper()
        if not nom_modele or not finition:
            erreur("AJOUT_INCOMPLET", "Le modèle et la version / finition sont obligatoires.")
        energie = energies.get(c.normaliser(valeurs["energie"]))
        if not energie:
            erreur("AJOUT_ENERGIE", "Énergie obligatoire (choisissez dans la liste déroulante).")
        boite = boites.get(c.normaliser(valeurs["boite"])) if c.texte_propre(valeurs["boite"]) else None
        if c.texte_propre(valeurs["boite"]) and not boite:
            erreur("AJOUT_BOITE", "Boîte non reconnue (choisissez dans la liste déroulante).")
        nombres = {}
        for cle in ("cylindree", "puissance", "charge", "ptac", "places"):
            if c.texte_propre(valeurs[cle]):
                try:
                    nombres[cle] = c.lire_entier(valeurs[cle])[0]
                    if nombres[cle] < 0:
                        raise ValueError("negative")
                except ValueError:
                    erreur("AJOUT_NOMBRE", f"La colonne « {cle} » doit contenir un nombre entier positif.")
        try:
            quantite = _lire_quantite(valeurs["quantite"], qmax)[0]
        except ValueError as exc:
            erreur("AJOUT_QUANTITE", _erreur_quantite(str(exc), qmax))
            quantite = 0
        if len(rapport.erreurs) > nb_erreurs_avant:
            continue
        motricite = c.texte_propre(valeurs["motricite"], 10).upper()
        signature = (marque.id, c.normaliser(nom_modele), c.normaliser(finition), energie.id, boite.id if boite else None,
                     nombres.get("cylindree"), nombres.get("puissance"), motricite)
        if signature in vus:
            erreur("AJOUT_DOUBLON", "Ce produit apparaît deux fois dans l'onglet AJOUTS.")
            continue
        vus.add(signature)
        modele = next((m for m in Modele.objects.filter(marque=marque) if c.normaliser(m.nom) == c.normaliser(nom_modele)), None)
        if modele:
            existants = Produit.objects.filter(modele=modele, statut__in=["ACTIF", "ARCHIVE"])
            exact = next((p for p in existants if c.normaliser(p.finition) == c.normaliser(finition)
                          and p.energie_id == energie.id and p.boite_id == (boite.id if boite else None)
                          and p.cylindree_cm3 == nombres.get("cylindree") and p.puissance_fiscale_cv == nombres.get("puissance")
                          and p.motricite == motricite), None)
            if exact:
                erreur("AJOUT_EXISTE_DEJA", f"Ce produit existe déjà au catalogue (code {exact.code}) : renseignez sa quantité "
                       "dans l'onglet DECLARATION (s'il n'y figure pas, contactez le GIPAME).")
                continue
            proche = next((p for p in existants if c.normaliser(p.finition) == c.normaliser(finition)), None)
            if proche:
                rapport.ajouter("ALERTE", "AJOUT_PROCHE", f"Un produit très proche existe déjà (code {proche.code}) : le GIPAME "
                                "vérifiera qu'il ne s'agit pas d'un doublon.", c.FEUILLE_AJOUTS, r)
        ajouts.append({"ligne": r, "marque": marque, "modele": modele, "nom_modele": nom_modele, "finition": finition,
                       "energie": energie, "boite": boite, "motricite": motricite, "quantite": quantite,
                       "segment": c.texte_propre(valeurs["segment"], 150), "note": c.texte_propre(valeurs["note"], 500),
                       **nombres})
    return ajouts


# ------------------------------------------------------------------------------ enregistrement
def _enregistrer(membre, utilisateur, mois, version, brouillon, quantites, ajouts, attestation, aucune_vente, motif,
                 soumettre, rapport):
    if brouillon:
        decl = Declaration.objects.get(pk=brouillon["id"])
        LigneVente.objects.filter(declaration=decl).delete()  # un brouillon se remplace librement
    else:
        decl = Declaration.objects.create(membre=membre, mois=mois, version=version)
    produits = {p.code: p for p in Produit.objects.filter(code__in=list(quantites))}
    lignes = [LigneVente(declaration=decl, produit=produits[code], quantite=q) for code, q in quantites.items()]
    for a in ajouts:
        produit = _produit_propose(membre, a)
        lignes.append(LigneVente(declaration=decl, produit=produit, quantite=a["quantite"]))
    LigneVente.objects.bulk_create(lignes)
    decl.attestation_complete = attestation == "OUI"
    decl.aucune_vente_confirmee = aucune_vente == "OUI"
    decl.motif_correction = motif
    decl.version_gabarit = c.GABARIT_VERSION
    decl.empreinte_fichier = rapport.empreinte
    decl.save(update_fields=["attestation_complete", "aucune_vente_confirmee", "motif_correction", "version_gabarit",
                             "empreinte_fichier", "modifie_le"])
    rapport.declaration_id, rapport.statut_declaration = decl.id, "BROUILLON"
    if not soumettre:
        return
    if attestation != "OUI":
        rapport.ajouter("ALERTE", "ATTESTATION_MANQUANTE", "Déclaration enregistrée en brouillon : répondez OUI à « Déclaration "
                        "complète et exacte ? » pour la soumettre.")
        return
    try:
        with transaction.atomic():
            decl.statut = "SOUMISE"
            decl.save(update_fields=["statut", "modifie_le"])
        rapport.statut_declaration = "SOUMISE"
    except IntegrityError as exc:
        decl.statut = "BROUILLON"
        rapport.ajouter("ERREUR", "SOUMISSION", _message_base(exc))
        rapport.statut_declaration = "BROUILLON"


def _produit_propose(membre, a):
    """Crée la proposition de produit (ou réutilise la même proposition déjà faite par ce membre)."""
    existante = next((p for p in Produit.objects.filter(propose_par=membre, statut="PROPOSE")
                      if c.normaliser(p.finition) == c.normaliser(a["finition"]) and p.energie_id == a["energie"].id
                      and c.normaliser(p.modele.nom if p.modele else p.modele_propose) == c.normaliser(a["nom_modele"])
                      and (p.modele.marque_id if p.modele else p.marque_proposee_id) == a["marque"].id), None)
    if existante:
        return existante
    return Produit.objects.create(
        code="", modele=a["modele"], marque_proposee=a["marque"], modele_propose="" if a["modele"] else a["nom_modele"],
        finition=a["finition"], energie=a["energie"], boite=a["boite"], cylindree_cm3=a.get("cylindree"),
        puissance_fiscale_cv=a.get("puissance"), charge_utile_kg=a.get("charge"), ptac_kg=a.get("ptac"),
        nb_places=a.get("places"), motricite=a["motricite"], libelle_affiche=f"{a['nom_modele']} {a['finition']}".strip(),
        statut="PROPOSE", propose_par=membre, segment_propose=a["segment"], note_proposition=a["note"])


def _tracer(rapport, contenu, nom_fichier, membre, utilisateur):
    """Trace de chaque dépôt (accepté ou rejeté), même quand rien n'est enregistré."""
    try:
        with transaction.atomic():
            depot = DepotFichier.objects.create(
                membre=membre, mois=rapport.mois, type_depot="DECLARATION", nom_fichier=c.texte_propre(nom_fichier, 255) or "?",
                taille_octets=len(contenu), empreinte_sha256=rapport.empreinte, resultat=rapport.resultat,
                declaration_id=rapport.declaration_id, nb_erreurs=len(rapport.erreurs), nb_alertes=len(rapport.alertes),
                rapport=[asdict(p) for p in rapport.problemes[:200]], depose_par=utilisateur)
            rapport.depot_id = depot.id
    except DatabaseError:
        rapport.ajouter("ALERTE", "TRACE", "La trace du dépôt n'a pas pu être enregistrée.")
