/* Roue de Secours — comportement du panneau (sans dépendance).
   - La conversation est gardée dans l'onglet (sessionStorage, clé propre au compte) et effacée à la déconnexion.
   - Les réponses arrivent au fil de l'eau (lignes JSON) ; le texte est affiché via un rendu Markdown SÛR :
     tout est échappé, seuls **gras**, listes, `code` et liens vers des pages du portail (/…) sont rendus.
   - Animations : la roue tourne pendant la recherche, avance au rythme du texte, vacille en cas d'erreur. */
(function () {
  "use strict";

  var racine = document.querySelector("[data-roue]");
  if (!racine || !window.fetch) return;

  var $ = function (sel) { return racine.querySelector(sel); };
  var lanceur = $("[data-roue-lanceur]"), panneau = $("[data-roue-panneau]"), fil = $("[data-roue-fil]");
  var accueil = $("[data-roue-accueil]"), formulaire = $("[data-roue-formulaire]"), champ = $("[data-roue-question]");
  var envoyer = $("[data-roue-envoyer]"), etat = $("[data-roue-etat]"), embleme = $("[data-roue-embleme]");
  var logo = $("[data-roue-logo]"), pastille = $("[data-roue-pastille]"), annonce = $("[data-roue-annonce]");
  var compteur = $("[data-roue-compteur]"), astuce = $("[data-roue-astuce]");
  var CLE = racine.getAttribute("data-cle"), CSRF = racine.getAttribute("data-csrf");
  var URL_Q = racine.getAttribute("data-url-question"), URL_A = racine.getAttribute("data-url-avis");
  var IA = racine.getAttribute("data-ia") === "1";
  var PLEINE_PAGE = racine.hasAttribute("data-pleine-page");
  var URL_PAGE = racine.getAttribute("data-url-page");
  var MAX = parseInt(champ.getAttribute("maxlength"), 10) || 800;
  var ETAT_REPOS = IA ? "Pour vous dépanner sur le portail" : "Mode simplifié : extraits de l'aide, sans IA";

  var conversation = lire();
  var enCours = null, angle = 0;

  // ---------------------------------------------------------------- stockage (onglet seulement)
  function lire() { try { return JSON.parse(sessionStorage.getItem(CLE)) || []; } catch (e) { return []; } }
  function sauver() {
    var propre = conversation.slice(-30).map(function (m) { var c = {}; for (var k in m) if (k !== "_el") c[k] = m[k]; return c; });
    try { sessionStorage.setItem(CLE, JSON.stringify(propre)); } catch (e) { /* plein ou interdit */ }
  }
  function oublierTout() {
    try { Object.keys(sessionStorage).forEach(function (k) { if (k.indexOf("roue-") === 0) sessionStorage.removeItem(k); }); } catch (e) { /* rien */ }
  }

  // ---------------------------------------------------------------- rendu Markdown sûr
  function echapper(t) {
    return String(t).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  function enLigne(t) { // t est déjà échappé
    return t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[([^\]]+)\]\((\/[A-Za-z0-9\-._~\/?#=%]*)\)/g, '<a href="$2">$1</a>');
  }
  function rendre(md) {
    var html = "", liste = null, para = [];
    // Markdown standard : un simple retour à la ligne est une espace (les fiches sont coupées à ~120 caractères).
    function fermerPara() { if (para.length) { html += "<p>" + enLigne(para.join(" ")) + "</p>"; para = []; } }
    function fermerListe() { if (liste) { html += "</" + liste + ">"; liste = null; } }
    echapper(md).split("\n").forEach(function (l) {
      var m;
      if (/^\s*$/.test(l)) { fermerPara(); fermerListe(); return; }
      if ((m = l.match(/^\s*[-*•]\s+(.*)$/))) { fermerPara(); if (liste !== "ul") { fermerListe(); html += "<ul>"; liste = "ul"; } html += "<li>" + enLigne(m[1]) + "</li>"; return; }
      if ((m = l.match(/^\s*\d+[.)]\s+(.*)$/))) { fermerPara(); if (liste !== "ol") { fermerListe(); html += "<ol>"; liste = "ol"; } html += "<li>" + enLigne(m[1]) + "</li>"; return; }
      if ((m = l.match(/^#{1,6}\s+(.*)$/))) { fermerPara(); fermerListe(); html += "<p><strong>" + enLigne(m[1]) + "</strong></p>"; return; }
      if (liste && /^\s{2,}\S/.test(l)) { html = html.replace(/<\/li>$/, " " + enLigne(l.trim()) + "</li>"); return; }
      fermerListe(); para.push(l);
    });
    fermerPara(); fermerListe();
    return html;
  }

  // ---------------------------------------------------------------- éléments
  function el(tag, classe, texte) {
    var e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texte) e.textContent = texte;
    return e;
  }
  var ICONES = {
    page: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>',
    utile: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10v11H4V10z"/><path d="M7 10l4-7a2 2 0 0 1 3 2l-1 5h6a2 2 0 0 1 2 2l-2 7a2 2 0 0 1-2 2H7"/></svg>',
    revoir: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 14V3H4v11z"/><path d="M7 14l4 7a2 2 0 0 0 3-2l-1-5h6a2 2 0 0 0 2-2l-2-7a2 2 0 0 0-2-2H7"/></svg>'
  };

  function bulleMoi(texte) { return el("div", "roue__msg roue__msg--moi", texte); }

  function bulleRoue(msg) {
    var bloc = el("div", "roue__msg roue__msg--roue");
    var bulle = el("div", "roue__bulle");
    var texte = el("div", "roue__texte");
    bulle.appendChild(texte);
    bloc.appendChild(bulle);
    msg._el = { bloc: bloc, bulle: bulle, texte: texte };
    if (msg.texte) majTexte(msg, false);
    if (msg.fini) pied(msg);
    if (msg.erreur) bloc.classList.add("roue__msg--erreur");
    return bloc;
  }

  function reflexion(msg, phrase) {
    var t = msg._el.texte;
    var r = t.querySelector(".roue__reflexion");
    if (!r) {
      r = el("div", "roue__reflexion");
      var route = el("span", "roue__route");
      route.innerHTML = '<svg class="roue__logo" aria-hidden="true"><use href="#roue-logo"/></svg>';
      r.appendChild(route);
      r.appendChild(el("span", "roue__reflexion-texte"));
      t.innerHTML = "";
      t.appendChild(r);
    }
    r.querySelector(".roue__reflexion-texte").textContent = phrase;
  }

  var rafEnAttente = false;
  function majTexte(msg, ecrit) {
    var t = msg._el.texte;
    t.innerHTML = rendre(msg.texte);
    t.classList.toggle("roue__texte--ecrit", !!ecrit);
  }
  function majTexteBientot(msg) {
    if (rafEnAttente) return;
    rafEnAttente = true;
    requestAnimationFrame(function () { rafEnAttente = false; majTexte(msg, !msg.fini); defiler(); });
  }

  function pied(msg) {
    var p = el("div", "roue__pied");
    if (msg.mode === "hors_ligne" && IA) p.appendChild(el("span", "roue__mode", "Mode simplifié : extraits de l'aide"));
    if (msg.sources && msg.sources.length) {
      var ul = el("ul", "roue__sources");
      ul.setAttribute("aria-label", "Sources");
      msg.sources.forEach(function (s) {
        var li = document.createElement("li");
        var lien = s.lien ? el("a") : el("span");
        if (s.lien) lien.href = s.lien;
        lien.innerHTML = ICONES.page;
        lien.appendChild(document.createTextNode(s.titre));
        li.appendChild(lien);
        ul.appendChild(li);
      });
      p.appendChild(ul);
    }
    if (!msg.erreur) p.appendChild(boutonsAvis(msg));
    msg._el.bloc.appendChild(p);
  }

  function boutonsAvis(msg) {
    var zone = el("div", "roue__avis");
    if (msg.avis) { zone.appendChild(el("span", "roue__merci", "Merci pour votre avis.")); return zone; }
    if (msg.sansFiche) {
      var signaler = el("button", "roue__lien-bouton", "Signaler cette question au GIPAME");
      signaler.type = "button";
      signaler.title = "Votre question (sans votre nom) sera lue par l'équipe technique pour compléter l'aide.";
      signaler.addEventListener("click", function () { donnerAvis(msg, 0, "", zone); });
      zone.appendChild(signaler);
      return zone;
    }
    [["utile", 1, "Utile"], ["revoir", -1, "À revoir"]].forEach(function (b) {
      var bouton = el("button");
      bouton.type = "button";
      bouton.innerHTML = ICONES[b[0]];
      bouton.appendChild(document.createTextNode(b[2]));
      bouton.setAttribute("aria-pressed", "false");
      bouton.addEventListener("click", function () {
        if (b[1] === 1) { donnerAvis(msg, 1, "", zone); return; }
        demanderCommentaire(msg, zone);
      });
      zone.appendChild(bouton);
    });
    return zone;
  }

  function demanderCommentaire(msg, zone) {
    zone.innerHTML = "";
    var form = el("div", "roue__retour");
    var txt = el("textarea");
    txt.maxLength = 1000;
    txt.placeholder = "Qu'est-ce qui n'allait pas ? (facultatif, sans chiffres de ventes)";
    txt.setAttribute("aria-label", "Ce qui n'allait pas dans la réponse");
    var actions = el("div", "roue__retour-actions");
    var annuler = el("button", "roue__bouton roue__bouton--leger", "Annuler");
    var ok = el("button", "roue__bouton", "Envoyer");
    annuler.type = ok.type = "button";
    annuler.addEventListener("click", function () { zone.replaceWith(boutonsAvis(msg)); });
    ok.addEventListener("click", function () { donnerAvis(msg, -1, txt.value, zone); });
    actions.appendChild(annuler); actions.appendChild(ok);
    form.appendChild(txt); form.appendChild(actions);
    zone.appendChild(form);
    zone.style.width = "100%";
    txt.focus();
  }

  function donnerAvis(msg, note, commentaire, zone) {
    var corps = { note: note, question: msg.question || "", reponse: msg.texte || "", commentaire: commentaire || "",
                  sources: (msg.sources || []).map(function (s) { return s.titre; }), mode: msg.mode || "", page: location.pathname };
    fetch(URL_A, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF }, body: JSON.stringify(corps) })
      .then(function (r) { return r.ok ? null : r.json().then(function (j) { throw new Error(j.erreur || "échec"); }); })
      .then(function () {
        msg.avis = note; sauver();
        zone.innerHTML = ""; zone.style.width = "";
        zone.appendChild(el("span", "roue__merci", note === 0 ? "Merci, la question est transmise." : "Merci pour votre avis."));
      })
      .catch(function (e) { zone.innerHTML = ""; zone.appendChild(el("span", "roue__note", e.message || "Avis non envoyé.")); });
  }

  // ---------------------------------------------------------------- animation de la roue
  function angleActuel(svg) {
    var m = getComputedStyle(svg).transform;
    if (!m || m === "none") return 0;
    var v = m.match(/matrix\(([^)]+)\)/);
    if (!v) return 0;
    var p = v[1].split(",").map(parseFloat);
    return Math.atan2(p[1], p[0]) * 180 / Math.PI;
  }
  function occupe(oui) {
    racine.classList.toggle("roue--occupee", oui);
    logo.classList.toggle("roue--tourne", oui);
  }
  function commencerEcriture() {
    // La roue cesse de tourner seule et avance désormais au rythme du texte (sans à-coup : on part de l'angle atteint).
    angle = angleActuel(logo);
    logo.classList.remove("roue--tourne");
    logo.style.transform = "rotate(" + angle + "deg)";
  }
  function avancer(n) { angle += Math.min(n, 60) * 2.2; logo.style.transform = "rotate(" + angle + "deg)"; }
  function crever() {
    embleme.classList.remove("roue--crevaison");
    void embleme.offsetWidth;
    embleme.classList.add("roue--crevaison");
  }

  // ---------------------------------------------------------------- envoi d'une question
  function defiler() { fil.scrollTop = fil.scrollHeight; }
  function majEnvoi() {
    envoyer.disabled = !enCours && !champ.value.trim();
    envoyer.setAttribute("aria-label", enCours ? "Arrêter la réponse" : "Envoyer la question");
    var reste = MAX - champ.value.length;
    compteur.hidden = reste > 150;
    compteur.textContent = reste;
  }
  function ajusterHauteur() { champ.style.height = "auto"; champ.style.height = Math.min(champ.scrollHeight, 140) + "px"; }

  function messageStatut(code) {
    if (code === 401) return "Votre session a expiré : reconnectez-vous pour continuer.";
    if (code === 403) return "La page a expiré : rechargez-la puis reposez votre question.";
    if (code === 429) return "Beaucoup de questions en peu de temps : patientez quelques minutes.";
    return "La Roue de Secours ne répond pas pour le moment. Réessayez dans un instant, ou consultez la page Aide.";
  }

  function poser(question) {
    question = (question || "").trim();
    if (!question || enCours) return;
    accueil.hidden = true;
    var historique = conversation.filter(function (m) { return !m.erreur && m.texte; }).slice(-6)
      .map(function (m) { return { role: m.role, texte: m.texte }; });
    var moi = { role: "user", texte: question };
    conversation.push(moi);
    fil.appendChild(bulleMoi(question));
    var msg = { role: "assistant", texte: "", sources: [], mode: "", question: question };
    fil.appendChild(bulleRoue(msg));
    reflexion(msg, "Je cherche dans l'aide…");
    etat.textContent = "Je cherche dans l'aide…";
    occupe(true);
    champ.value = ""; ajusterHauteur();
    enCours = new AbortController();
    majEnvoi();
    defiler();

    var commence = false;
    function traiter(ligne) {
      if (!ligne.trim()) return;
      var ev;
      try { ev = JSON.parse(ligne); } catch (e) { return; }
      if (ev.t === "sources") {
        msg.sources = ev.sources || []; msg.sansFiche = !!ev.sans_fiche;
        var n = msg.sources.length;
        var phrase = n ? (IA ? "J'ai trouvé " + n + " fiche" + (n > 1 ? "s" : "") + ", je rédige…" : "Je rassemble les extraits…")
                       : "Je prépare une réponse…";
        reflexion(msg, phrase); etat.textContent = phrase;
      } else if (ev.t === "texte") {
        if (!commence) { commence = true; commencerEcriture(); etat.textContent = "Je réponds…"; }
        msg.texte += ev.d; avancer(ev.d.length); majTexteBientot(msg);
      } else if (ev.t === "mode") {
        msg.mode = "hors_ligne";
      } else if (ev.t === "erreur") {
        msg.erreurTexte = ev.message;
      } else if (ev.t === "fin") {
        msg.mode = ev.mode; msg.sansFiche = !!ev.sans_fiche;
      }
    }

    fetch(URL_Q, {
      method: "POST", credentials: "same-origin", signal: enCours.signal,
      headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
      body: JSON.stringify({ question: question, historique: historique, page: location.pathname })
    }).then(function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (j) { throw new Error(j.erreur || messageStatut(r.status)); });
      }
      var lecteur = r.body.getReader(), dec = new TextDecoder(), tampon = "";
      function pomper() {
        return lecteur.read().then(function (res) {
          if (res.done) { if (tampon) traiter(tampon); return; }
          tampon += dec.decode(res.value, { stream: true });
          var i;
          while ((i = tampon.indexOf("\n")) >= 0) { traiter(tampon.slice(0, i)); tampon = tampon.slice(i + 1); }
          return pomper();
        });
      }
      return pomper();
    }).then(function () {
      if (!msg.texte) throw new Error(msg.erreurTexte || messageStatut(0));
      if (msg.erreurTexte) msg.texte += "\n\n" + msg.erreurTexte;
      finir(msg, false);
    }).catch(function (e) {
      if (e && e.name === "AbortError") {
        msg.texte = msg.texte ? msg.texte + "\n\n(Réponse arrêtée.)" : "Réponse arrêtée.";
        finir(msg, false);
        return;
      }
      msg.texte = (e && e.message) || messageStatut(0);
      msg.erreur = true;
      finir(msg, true);
    });
  }

  function finir(msg, enErreur) {
    enCours = null;
    occupe(false);
    if (enErreur) { msg._el.bloc.classList.add("roue__msg--erreur"); crever(); }
    else { logo.style.transform = "rotate(" + (Math.round(angle / 72) * 72) + "deg)"; } // se pose sur un rayon
    msg.fini = true;
    majTexte(msg, false);
    pied(msg);
    conversation.push(msg);
    sauver();
    etat.textContent = ETAT_REPOS;
    annonce.textContent = enErreur ? "La Roue de Secours n'a pas pu répondre." : "Réponse de la Roue de Secours prête.";
    if (panneau.hidden && pastille) pastille.hidden = false;
    majEnvoi();
    defiler();
  }

  // ---------------------------------------------------------------- ouverture / fermeture
  function ouvrir() {
    panneau.hidden = false;
    if (!lanceur) return;
    lanceur.setAttribute("aria-expanded", "true");
    pastille.hidden = true;
    if (astuce) astuce.hidden = true;
    document.documentElement.classList.add("roue-ouverte");
    defiler();
    setTimeout(function () { champ.focus(); }, 60);
  }
  function fermer() {
    if (PLEINE_PAGE) return;
    panneau.hidden = true;
    lanceur.setAttribute("aria-expanded", "false");
    document.documentElement.classList.remove("roue-ouverte");
    lanceur.focus();
  }
  if (lanceur) lanceur.addEventListener("click", function () { if (panneau.hidden) ouvrir(); else fermer(); });
  if ($("[data-roue-fermer]")) $("[data-roue-fermer]").addEventListener("click", fermer);

  // Agrandir / réduire (choix gardé dans l'onglet).
  var agrandir = $("[data-roue-agrandir]");
  function appliquerTaille(grande) {
    racine.classList.toggle("roue--grande", grande);
    if (!agrandir) return;
    agrandir.setAttribute("aria-pressed", grande ? "true" : "false");
    agrandir.title = grande ? "Réduire" : "Agrandir";
    agrandir.setAttribute("aria-label", grande ? "Réduire la fenêtre de discussion" : "Agrandir la fenêtre de discussion");
  }
  if (agrandir) {
    try { appliquerTaille(sessionStorage.getItem("roue-taille") === "grande"); } catch (e) { /* rien */ }
    agrandir.addEventListener("click", function () {
      var grande = !racine.classList.contains("roue--grande");
      appliquerTaille(grande);
      try { sessionStorage.setItem("roue-taille", grande ? "grande" : "normale"); } catch (e) { /* rien */ }
      defiler(); champ.focus();
    });
  }

  // Ouvrir dans un onglet : la conversation de cet onglet est recopiée par le navigateur dans le nouvel onglet.
  var onglet = $("[data-roue-onglet]");
  if (onglet) onglet.addEventListener("click", function () {
    if (enCours) enCours.abort();
    sauver();
    var w = window.open(URL_PAGE, "_blank");
    if (w) fermer(); else location.href = URL_PAGE;
  });
  panneau.addEventListener("keydown", function (ev) { if (ev.key === "Escape") { ev.stopPropagation(); fermer(); } });
  $("[data-roue-nouvelle]").addEventListener("click", function () {
    if (enCours) enCours.abort();
    conversation = []; sauver();
    Array.prototype.slice.call(fil.children).forEach(function (c) { if (c !== accueil) c.remove(); });
    accueil.hidden = false;
    champ.focus();
  });

  formulaire.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (enCours) { enCours.abort(); return; }
    poser(champ.value);
  });
  champ.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); formulaire.requestSubmit(); }
  });
  champ.addEventListener("input", function () { ajusterHauteur(); majEnvoi(); });
  racine.querySelectorAll("[data-roue-suggestion]").forEach(function (b) {
    b.addEventListener("click", function () { poser(b.textContent); });
  });

  // Déconnexion : la conversation de l'onglet est effacée.
  document.querySelectorAll("form[data-confirmer-deconnexion]").forEach(function (f) { f.addEventListener("submit", oublierTout); });
  var confirmer = document.querySelector("#dialogue-deconnexion [data-confirmer]");
  if (confirmer) confirmer.addEventListener("click", oublierTout);

  // Pleine page : le panneau est la page.
  if (PLEINE_PAGE) { document.documentElement.classList.add("roue-page-dediee"); setTimeout(function () { champ.focus(); }, 60); }

  // Conseil affiché une seule fois sur ce navigateur.
  try {
    if (astuce && !localStorage.getItem("roue-astuce-vue") && !conversation.length) {
      setTimeout(function () { if (panneau.hidden) astuce.hidden = false; }, 1500);
      setTimeout(function () { astuce.hidden = true; }, 9500);
      localStorage.setItem("roue-astuce-vue", "1");
    }
  } catch (e) { /* stockage interdit : pas de conseil */ }
  if (astuce) $("[data-roue-astuce-fermer]").addEventListener("click", function () { astuce.hidden = true; });
  if (PLEINE_PAGE) defiler();

  // Restauration de la conversation de l'onglet.
  if (conversation.length) {
    accueil.hidden = true;
    conversation.forEach(function (m) { fil.appendChild(m.role === "user" ? bulleMoi(m.texte) : bulleRoue(m)); });
  }
  majEnvoi();
})();
