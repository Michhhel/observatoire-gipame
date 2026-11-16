"""
GIPAME - modèle de données de la collecte mensuelle des ventes (v1).

Prérequis : Django >= 5.2, PostgreSQL >= 15 (extension btree_gist).

Principes
- Le schéma appartient à l'ORM. Ce que l'ORM ne sait pas exprimer (rôles, sécurité par
  ligne, triggers, vues, fonctions) est dans la migration 0003 (SQL versionné dans
  collecte/sql/).
- Rien ne se supprime : statuts, dates de validité, versions (triggers d'interdiction).
- Quantités uniquement (pas de prix). Les autres mesures (prix, pièces, stocks,
  importations) iront dans des tables de faits séparées, jamais dans LigneVente.
"""
from django.contrib.auth.models import AbstractUser
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeBoundary, RangeOperators
from django.db import models
from django.db.models import Func, Q, Value
from django.db.models.functions import Now, Trim, Upper


class DateRange(Func):
    """daterange(debut, fin, '[]') ; une borne NULL = période ouverte."""

    function = "DATERANGE"
    output_field = DateRangeField()


class RegexpReplace(Func):
    function = "REGEXP_REPLACE"
    output_field = models.CharField()


def _periode(debut="date_debut", fin="date_fin"):
    return DateRange(debut, fin, RangeBoundary(inclusive_lower=True, inclusive_upper=True))


class Horodate(models.Model):
    cree_le = models.DateTimeField(auto_now_add=True)
    modifie_le = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ListeValeurs(Horodate):
    """Vocabulaire contrôlé : une table (pas un ENUM figé), donc extensible sans migration."""

    code = models.CharField(max_length=30, unique=True)
    libelle = models.CharField(max_length=100)
    ordre = models.PositiveSmallIntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        abstract = True
        ordering = ["ordre", "code"]

    def __str__(self):
        return self.libelle


class Origine(ListeValeurs):
    """Origine de la MARQUE (japonaise, européenne, coréenne, chinoise, autres)."""


class Energie(ListeValeurs):
    pass


class Boite(ListeValeurs):
    pass


# --------------------------------------------------------------------------- membres


class GroupeEconomique(Horodate):
    """Plusieurs membres d'un même groupe comptent pour UN seul contributeur (seuils)."""

    nom = models.CharField(max_length=150, unique=True)

    def __str__(self):
        return self.nom


class Membre(Horodate):
    class Famille(models.TextChoices):
        VEHICULES = "VEHICULES", "Véhicules"
        PIECES_EQUIPEMENTS = "PIECES_EQUIPEMENTS", "Pièces et équipements"

    code = models.CharField(max_length=20, unique=True)  # immuable (trigger)
    raison_sociale = models.CharField(max_length=200)
    famille = models.CharField(max_length=30, choices=Famille.choices, default=Famille.VEHICULES)
    groupe = models.ForeignKey(
        GroupeEconomique, null=True, blank=True, on_delete=models.PROTECT, related_name="membres"
    )

    def __str__(self):
        return f"{self.code} - {self.raison_sociale}"


class PeriodeAdhesion(Horodate):
    """Périodes où le membre est tenu de déclarer : base du taux de couverture et du
    calcul à périmètre constant. Un membre peut sortir puis revenir."""

    membre = models.ForeignKey(Membre, on_delete=models.PROTECT, related_name="periodes")
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)
    declaration_obligatoire = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(date_fin__isnull=True) | Q(date_fin__gte=models.F("date_debut")),
                name="periodeadhesion_dates_ok",
            ),
            ExclusionConstraint(
                name="periodeadhesion_sans_chevauchement",
                expressions=[(_periode(), RangeOperators.OVERLAPS), ("membre", RangeOperators.EQUAL)],
            ),
        ]


# ------------------------------------------------------------ comptes et gouvernance


class Utilisateur(AbstractUser):
    """Compte applicatif. Le rôle métier détermine le rôle PostgreSQL utilisé (middleware).
    Un compte MEMBRE est rattaché à un membre ; les autres rôles ne le sont jamais."""

    class Role(models.TextChoices):
        MEMBRE = "MEMBRE", "Membre (déclarant)"
        GESTION = "GESTION", "Gestion (référentiels, suivi)"
        BUREAU = "BUREAU", "Bureau (dirigeants)"
        TECHNIQUE = "TECHNIQUE", "Technique (développeur, administrateur)"

    role_metier = models.CharField(max_length=10, choices=Role.choices, default=Role.TECHNIQUE)
    membre = models.ForeignKey(
        Membre, null=True, blank=True, on_delete=models.PROTECT, related_name="utilisateurs"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(role_metier="MEMBRE", membre__isnull=False))
                | (~Q(role_metier="MEMBRE") & Q(membre__isnull=True)),
                name="utilisateur_role_membre_coherent",
            )
        ]


class Poste(Horodate):
    """Postes de gouvernance (président, vice-président, délégué général) : l'accord
    exceptionnel repose sur les POSTES, pas sur les personnes ni sur les membres."""

    code = models.CharField(max_length=30, unique=True)
    libelle = models.CharField(max_length=100)

    def __str__(self):
        return self.libelle


class TitulairePoste(Horodate):
    poste = models.ForeignKey(Poste, on_delete=models.PROTECT, related_name="titulaires")
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.PROTECT, related_name="postes_tenus")
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(date_fin__isnull=True) | Q(date_fin__gte=models.F("date_debut")),
                name="titulaireposte_dates_ok",
            ),
            ExclusionConstraint(
                name="titulaireposte_un_seul_titulaire",
                expressions=[(_periode(), RangeOperators.OVERLAPS), ("poste", RangeOperators.EQUAL)],
            ),
        ]


class DemandeAccesExceptionnel(Horodate):
    """Lecture exceptionnelle des données individuelles : demande, accords des postes,
    fenêtre limitée dans le temps. Statut dérivé des approbations (fonction SQL)."""

    demandeur = models.ForeignKey(Utilisateur, on_delete=models.PROTECT, related_name="demandes_acces")
    motif = models.TextField()
    membre_cible = models.ForeignKey(Membre, null=True, blank=True, on_delete=models.PROTECT)
    mois_debut = models.DateField()
    mois_fin = models.DateField()
    duree_minutes = models.PositiveSmallIntegerField(default=60)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(mois_fin__gte=models.F("mois_debut")), name="demandeacces_mois_ok"),
            models.CheckConstraint(
                condition=Q(duree_minutes__gte=1, duree_minutes__lte=480), name="demandeacces_duree_ok"
            ),
        ]


class ApprobationAcces(models.Model):
    class Decision(models.TextChoices):
        APPROUVEE = "APPROUVEE", "Approuvée"
        REFUSEE = "REFUSEE", "Refusée"

    demande = models.ForeignKey(DemandeAccesExceptionnel, on_delete=models.PROTECT, related_name="approbations")
    poste = models.ForeignKey(Poste, on_delete=models.PROTECT)
    approbateur = models.ForeignKey(Utilisateur, on_delete=models.PROTECT)
    decision = models.CharField(max_length=10, choices=Decision.choices)
    commentaire = models.TextField(blank=True)
    decide_le = models.DateTimeField(db_default=Now())  # fixé par le serveur (trigger)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["demande", "poste"], name="approbationacces_un_accord_par_poste")
        ]


class ParametreSysteme(Horodate):
    """Paramètres modifiables sans toucher au code. Catégorie SECURITE : modifiable
    uniquement par le compte propriétaire (sous scellés), jamais par la gestion."""

    class Categorie(models.TextChoices):
        OPERATIONNEL = "OPERATIONNEL", "Opérationnel"
        SECURITE = "SECURITE", "Sécurité"

    cle = models.CharField(max_length=60, unique=True)
    valeur = models.CharField(max_length=200)
    categorie = models.CharField(max_length=15, choices=Categorie.choices, default=Categorie.OPERATIONNEL)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.cle}={self.valeur}"


class JournalModification(models.Model):
    """Piste d'audit complète (alimentée par trigger, jamais par l'application)."""

    table_nom = models.CharField(max_length=63)
    objet_id = models.CharField(max_length=40)
    operation = models.CharField(max_length=6)
    ancien = models.JSONField(null=True)
    nouveau = models.JSONField(null=True)
    utilisateur_id = models.IntegerField(null=True)
    role_db = models.CharField(max_length=63, blank=True)
    cree_le = models.DateTimeField(db_default=Now())


class JournalAcces(models.Model):
    """Journal des accès exceptionnels (qui, quoi, combien de lignes) : base du rapport
    mensuel envoyé aux dirigeants."""

    utilisateur_id = models.IntegerField(null=True)
    demande_id = models.IntegerField(null=True)
    action = models.CharField(max_length=40)
    details = models.JSONField(default=dict)
    nb_lignes = models.IntegerField(default=0)
    cree_le = models.DateTimeField(db_default=Now())


# ---------------------------------------------------------------- référentiel produit


class Marque(Horodate):
    code = models.CharField(max_length=30, unique=True)  # immuable (trigger)
    nom = models.CharField(max_length=100)
    origine = models.ForeignKey(Origine, on_delete=models.PROTECT)

    def __str__(self):
        return self.nom


class Concession(Horodate):
    """Qui distribue quelle marque, et quand. Une marque peut avoir plusieurs membres
    en même temps ; un même couple (membre, marque) ne peut pas se chevaucher."""

    membre = models.ForeignKey(Membre, on_delete=models.PROTECT, related_name="concessions")
    marque = models.ForeignKey(Marque, on_delete=models.PROTECT, related_name="concessions")
    date_debut = models.DateField()
    date_fin = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(date_fin__isnull=True) | Q(date_fin__gte=models.F("date_debut")),
                name="concession_dates_ok",
            ),
            ExclusionConstraint(
                name="concession_sans_chevauchement",
                expressions=[
                    (_periode(), RangeOperators.OVERLAPS),
                    ("membre", RangeOperators.EQUAL),
                    ("marque", RangeOperators.EQUAL),
                ],
            ),
        ]


class Modele(Horodate):
    """Famille de modèle (niveau d'analyse). Les versions déclarées sont des Produit."""

    marque = models.ForeignKey(Marque, on_delete=models.PROTECT, related_name="modeles")
    code = models.CharField(max_length=40, unique=True)
    nom = models.CharField(max_length=120)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["marque", "nom"], name="modele_unique_par_marque")]

    def __str__(self):
        return f"{self.marque} {self.nom}"


class Segmentation(Horodate):
    """Une VERSION de la grille de classement (catégories > segments). On peut toujours
    relire les ventes passées avec l'ancienne grille : rien n'est écrasé."""

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        COURANTE = "COURANTE", "Courante"
        ARCHIVEE = "ARCHIVEE", "Archivée"

    code = models.CharField(max_length=30, unique=True)
    libelle = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON)
    valide_du = models.DateField(null=True, blank=True)
    valide_au = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["statut"], condition=Q(statut="COURANTE"), name="segmentation_une_seule_courante"
            )
        ]

    def __str__(self):
        return self.code


class Categorie(Horodate):
    segmentation = models.ForeignKey(Segmentation, on_delete=models.PROTECT, related_name="categories")
    code = models.CharField(max_length=30)
    libelle = models.CharField(max_length=100)
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["segmentation", "ordre"]
        constraints = [models.UniqueConstraint(fields=["segmentation", "code"], name="categorie_unique")]

    def __str__(self):
        return self.libelle


class Segment(Horodate):
    categorie = models.ForeignKey(Categorie, on_delete=models.PROTECT, related_name="segments")
    code = models.CharField(max_length=30)
    libelle = models.CharField(max_length=100)
    definition = models.TextField(blank=True, help_text="Définition métier à rédiger avec le GIPAME.")
    ordre = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["categorie", "ordre"]
        constraints = [models.UniqueConstraint(fields=["categorie", "code"], name="segment_unique")]

    def __str__(self):
        return self.libelle


class Produit(Horodate):
    """Version déclarable d'un modèle (finition x moteur x boîte), comme aujourd'hui.

    Cycle de vie : PROPOSE (par un membre, visible de lui seul) -> ACTIF (validé par la
    gestion) -> ARCHIVE (plus affiché, jamais supprimé). REJETE / FUSIONNE (doublon)."""

    class Statut(models.TextChoices):
        PROPOSE = "PROPOSE", "Proposé"
        ACTIF = "ACTIF", "Actif"
        ARCHIVE = "ARCHIVE", "Archivé"
        REJETE = "REJETE", "Rejeté"
        FUSIONNE = "FUSIONNE", "Fusionné"

    code = models.CharField(max_length=40, unique=True, blank=True)  # immuable ; auto si vide
    modele = models.ForeignKey(Modele, null=True, blank=True, on_delete=models.PROTECT, related_name="versions")
    finition = models.CharField(max_length=120, blank=True)  # stockée en MAJUSCULES, trimée
    energie = models.ForeignKey(Energie, null=True, blank=True, on_delete=models.PROTECT)
    boite = models.ForeignKey(Boite, null=True, blank=True, on_delete=models.PROTECT)
    cylindree_cm3 = models.PositiveIntegerField(null=True, blank=True)
    puissance_fiscale_cv = models.PositiveSmallIntegerField(null=True, blank=True)
    charge_utile_kg = models.PositiveIntegerField(null=True, blank=True)
    ptac_kg = models.PositiveIntegerField(null=True, blank=True)
    nb_places = models.PositiveSmallIntegerField(null=True, blank=True)
    motricite = models.CharField(max_length=10, blank=True)  # 4X2, 4X4...
    libelle_affiche = models.CharField(max_length=200)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.ACTIF)
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    remplace_par = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="predecesseurs"
    )
    fusionne_dans = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="doublons"
    )
    # --- proposition par un membre (nouveau modèle, nouvelle version, nouveau type/segment)
    propose_par = models.ForeignKey(
        Membre, null=True, blank=True, on_delete=models.PROTECT, related_name="produits_proposes"
    )
    marque_proposee = models.ForeignKey(
        Marque, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    modele_propose = models.CharField(max_length=120, blank=True)
    segment_propose = models.CharField(max_length=150, blank=True)
    note_proposition = models.TextField(blank=True)
    decide_par_id = models.IntegerField(null=True, blank=True)
    decide_le = models.DateTimeField(null=True, blank=True)
    motif_decision = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "modele", "finition", "energie", "boite",
                    "cylindree_cm3", "puissance_fiscale_cv", "motricite",
                ],
                nulls_distinct=False,
                condition=Q(statut__in=["ACTIF", "ARCHIVE"]),
                name="produit_signature_unique",
            ),
            models.CheckConstraint(
                condition=Q(finition=Upper(Trim("finition"))), name="produit_finition_normalisee"
            ),
            models.CheckConstraint(
                condition=Q(modele__isnull=False) | Q(statut__in=["PROPOSE", "REJETE", "FUSIONNE"]),
                name="produit_modele_requis_si_valide",
            ),
            models.CheckConstraint(
                condition=~Q(statut="PROPOSE") | Q(propose_par__isnull=False),
                name="produit_proposition_a_un_auteur",
            ),
            models.CheckConstraint(
                condition=(Q(statut="FUSIONNE", fusionne_dans__isnull=False))
                | (~Q(statut="FUSIONNE") & Q(fusionne_dans__isnull=True)),
                name="produit_fusion_coherente",
            ),
        ]

    def __str__(self):
        return f"{self.code} {self.libelle_affiche}"


class ClassementProduit(Horodate):
    """Segment d'un produit DANS une version de segmentation (cohérence vérifiée par
    trigger). Changer un classement = créer une nouvelle segmentation, pas écraser."""

    class Source(models.TextChoices):
        MANUEL = "MANUEL", "Manuel"
        REGLE = "REGLE", "Règle"
        IMPORT = "IMPORT", "Import"

    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="classements")
    segmentation = models.ForeignKey(Segmentation, on_delete=models.PROTECT)
    segment = models.ForeignKey(Segment, on_delete=models.PROTECT)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUEL)
    justification = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["produit", "segmentation"], name="classement_un_par_segmentation")
        ]


class AliasProduit(Horodate):
    """Libellé libre d'un membre (ou global) -> produit canonique. Sert à l'import de
    l'historique et de la feuille « nouveaux ajouts » : on ne change pas les habitudes
    des membres, le rapprochement se fait une seule fois."""

    class Source(models.TextChoices):
        IMPORT_HISTORIQUE = "IMPORT_HISTORIQUE", "Import historique"
        AJOUT_MEMBRE = "AJOUT_MEMBRE", "Ajout par un membre"
        MANUEL = "MANUEL", "Manuel"

    membre = models.ForeignKey(Membre, null=True, blank=True, on_delete=models.PROTECT, related_name="alias")
    libelle_brut = models.CharField(max_length=250)
    libelle_normalise = models.GeneratedField(
        expression=RegexpReplace(Upper(Trim("libelle_brut")), Value(r"\s+"), Value(" "), Value("g")),
        output_field=models.CharField(max_length=250),
        db_persist=True,
    )
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="alias")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUEL)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["membre", "libelle_normalise"], nulls_distinct=False, name="alias_unique")
        ]


class ProduitMembre(Horodate):
    """Exceptions d'affichage par membre : MASQUE (ne s'affiche plus dans son gabarit,
    mais reste en base et dans l'historique) ou AFFICHE_FORCE."""

    class Etat(models.TextChoices):
        MASQUE = "MASQUE", "Masqué"
        AFFICHE_FORCE = "AFFICHE_FORCE", "Affiché (forcé)"

    class Mode(models.TextChoices):
        MANUEL = "MANUEL", "Manuel"
        AUTO = "AUTO", "Proposé par inactivité"

    membre = models.ForeignKey(Membre, on_delete=models.PROTECT, related_name="exceptions_affichage")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="exceptions_affichage")
    etat = models.CharField(max_length=15, choices=Etat.choices)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.MANUEL)
    motif = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membre", "produit"], name="produitmembre_unique")]


# ------------------------------------------------------------------------ déclarations


class Declaration(Horodate):
    """Une déclaration = un membre, un mois, une version. Une correction est une NOUVELLE
    version (jamais une modification) ; une seule version SOUMISE par (membre, mois)."""

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        SOUMISE = "SOUMISE", "Soumise (courante)"
        REMPLACEE = "REMPLACEE", "Remplacée par une correction"
        ANNULEE = "ANNULEE", "Annulée"

    class Source(models.TextChoices):
        PORTAIL = "PORTAIL", "Portail"
        IMPORT_HISTORIQUE = "IMPORT_HISTORIQUE", "Import historique"

    membre = models.ForeignKey(Membre, on_delete=models.PROTECT, related_name="declarations")
    mois = models.DateField(help_text="Premier jour du mois")
    version = models.PositiveSmallIntegerField(default=1)
    statut = models.CharField(max_length=10, choices=Statut.choices, default=Statut.BROUILLON)
    precedente = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="corrections")
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.PORTAIL)
    version_gabarit = models.CharField(max_length=20, blank=True)
    empreinte_fichier = models.CharField(max_length=64, blank=True)
    attestation_complete = models.BooleanField(default=False)
    aucune_vente_confirmee = models.BooleanField(default=False)
    motif_correction = models.TextField(blank=True)
    commentaire_portail = models.TextField(
        blank=True, default="", help_text="Explications données par le membre sur les alertes, depuis le portail.")
    soumise_le = models.DateTimeField(null=True, blank=True)  # fixé par trigger
    soumise_par = models.ForeignKey(
        Utilisateur, null=True, blank=True, on_delete=models.PROTECT, related_name="declarations_soumises"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(mois__day=1), name="declaration_mois_premier_du_mois"),
            models.CheckConstraint(condition=Q(version__gte=1), name="declaration_version_positive"),
            models.UniqueConstraint(fields=["membre", "mois", "version"], name="declaration_version_unique"),
            models.UniqueConstraint(
                fields=["membre", "mois"], condition=Q(statut="SOUMISE"), name="declaration_une_soumise_courante"
            ),
            models.UniqueConstraint(
                fields=["membre", "mois"], condition=Q(statut="BROUILLON"), name="declaration_un_seul_brouillon"
            ),
            models.CheckConstraint(
                condition=~Q(statut__in=["SOUMISE", "REMPLACEE"]) | Q(attestation_complete=True),
                name="declaration_soumise_attestee",
            ),
            models.CheckConstraint(
                condition=Q(version=1) | Q(statut__in=["BROUILLON", "ANNULEE"]) | ~Q(motif_correction=""),
                name="declaration_correction_motivee",
            ),
        ]


class LigneVente(Horodate):
    """Quantité vendue (véhicules neufs) d'un produit pour une déclaration. Les lignes
    d'un brouillon sont pré-remplies (0) ; elles deviennent immuables à la soumission."""

    declaration = models.ForeignKey(Declaration, on_delete=models.PROTECT, related_name="lignes")
    produit = models.ForeignKey(Produit, on_delete=models.PROTECT, related_name="lignes")
    quantite = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["declaration", "produit"], name="lignevente_unique_par_declaration")
        ]
        indexes = [models.Index(fields=["produit"], name="lignevente_produit_idx")]


class DepotFichier(Horodate):
    """Trace de chaque fichier Excel déposé, accepté ou rejeté : empreinte, résultat, rapport.
    Le fichier lui-même n'est pas conservé (les données validées sont dans la déclaration) ;
    l'empreinte permet de le retrouver chez le membre en cas de litige."""

    class Type(models.TextChoices):
        DECLARATION = "DECLARATION", "Déclaration mensuelle"
        HISTORIQUE = "HISTORIQUE", "Reprise d'historique"

    class Resultat(models.TextChoices):
        ACCEPTE = "ACCEPTE", "Accepté"
        ACCEPTE_AVEC_ALERTES = "ACCEPTE_AVEC_ALERTES", "Accepté avec alertes"
        REJETE = "REJETE", "Rejeté"

    membre = models.ForeignKey(Membre, null=True, blank=True, on_delete=models.PROTECT, related_name="depots")
    mois = models.DateField(null=True, blank=True)
    type_depot = models.CharField(max_length=12, choices=Type.choices, default=Type.DECLARATION)
    nom_fichier = models.CharField(max_length=255)
    taille_octets = models.PositiveIntegerField()
    empreinte_sha256 = models.CharField(max_length=64)
    resultat = models.CharField(max_length=22, choices=Resultat.choices)
    declaration = models.ForeignKey(Declaration, null=True, blank=True, on_delete=models.PROTECT, related_name="depots")
    nb_erreurs = models.PositiveSmallIntegerField(default=0)
    nb_alertes = models.PositiveSmallIntegerField(default=0)
    rapport = models.JSONField(default=list)  # lisible du membre seulement (peut citer des quantités)
    depose_par = models.ForeignKey(Utilisateur, null=True, blank=True, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(type_depot="HISTORIQUE") | Q(membre__isnull=False), name="depot_declaration_a_un_membre"
            )
        ]


# -------------------------------------------------------------------------- publication


class Publication(Horodate):
    """Instantané FIGÉ des agrégats publiés (provisoire puis définitif). Une publication
    ne change jamais après coup : une correction tardive donne une nouvelle version."""

    class Statut(models.TextChoices):
        PROVISOIRE = "PROVISOIRE", "Provisoire"
        DEFINITIVE = "DEFINITIVE", "Définitive"

    mois = models.DateField()
    segmentation = models.ForeignKey(Segmentation, on_delete=models.PROTECT)
    statut = models.CharField(max_length=12, choices=Statut.choices)
    version = models.PositiveSmallIntegerField(default=1)
    calculee_le = models.DateTimeField(auto_now_add=True)
    nb_membres_attendus = models.PositiveSmallIntegerField()
    nb_membres_declarants = models.PositiveSmallIntegerField()
    couverture_pct = models.DecimalField(max_digits=5, decimal_places=2)
    parametres = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["mois", "segmentation", "version"], name="publication_unique")
        ]


class CelluleAgregat(models.Model):
    """Une cellule publiée. `total` est NULL quand la cellule est supprimée : la valeur
    n'est JAMAIS stockée. n_contributeurs / motif sont réservés (pas lisibles des membres)."""

    class Dimension(models.TextChoices):
        TOTAL = "TOTAL"
        CATEGORIE = "CATEGORIE"
        SEGMENT = "SEGMENT"
        ORIGINE = "ORIGINE"
        ENERGIE = "ENERGIE"

    publication = models.ForeignKey(Publication, on_delete=models.PROTECT, related_name="cellules")
    dimension = models.CharField(max_length=10, choices=Dimension.choices)
    cle = models.CharField(max_length=40)
    total = models.IntegerField(null=True)
    supprime = models.BooleanField(default=False)
    n_contributeurs = models.PositiveSmallIntegerField()
    motif_suppression = models.CharField(max_length=15, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["publication", "dimension", "cle"], name="cellule_unique"),
            models.CheckConstraint(
                condition=(Q(supprime=True, total__isnull=True)) | (Q(supprime=False, total__isnull=False)),
                name="cellule_supprimee_sans_valeur",
            ),
        ]


class ProfilUtilisateur(models.Model):
    """Vue en lecture seule (collecte_v_profil_utilisateur) : ce que la gestion et le bureau peuvent
    voir d'un compte (nom affiché), sans jamais toucher la table des comptes."""

    username = models.CharField(max_length=150)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    role_metier = models.CharField(max_length=10)
    membre = models.ForeignKey(Membre, null=True, on_delete=models.DO_NOTHING, related_name="+")
    is_active = models.BooleanField()
    compte_active = models.BooleanField(default=False)   # la personne a choisi son mot de passe
    derniere_connexion = models.DateTimeField(null=True)
    cree_le = models.DateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "collecte_v_profil_utilisateur"

    @property
    def nom_affiche(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email or self.username
