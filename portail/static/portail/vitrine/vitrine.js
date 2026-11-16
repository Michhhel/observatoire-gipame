/* Observatoire GIPAME : animations de la page de présentation.
   - Ouverture : des traînées de phares qui, au défilement, se rangent en courbe des ventes mensuelles.
   - Segments : piste horizontale pilotée par le défilement (grands écrans).
   - Cycle : le marquage de la route se trace à l'arrivée.
   - Confidentialité : les points des membres se fondent en un total publié.
   Tout est piloté par le défilement de la personne ; « réduire les animations » fige le trafic. */
(function () {
  "use strict";

  var racine = document.documentElement;
  var calme = window.matchMedia("(prefers-reduced-motion: reduce)");
  var sombreSysteme = window.matchMedia("(prefers-color-scheme: dark)");
  var bornes = function (v) { return v < 0 ? 0 : v > 1 ? 1 : v; };
  var adoucir = function (t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
  var auxThemes = [];

  /* ---------------------------------------------------------------- Thème */
  function themeEffectif() {
    var t = racine.getAttribute("data-theme");
    if (t === "clair" || t === "sombre") return t;
    return sombreSysteme.matches ? "sombre" : "clair";
  }
  function themeChange() {
    var bouton = document.querySelector("[data-theme-bascule]");
    if (bouton) bouton.setAttribute("aria-label", themeEffectif() === "sombre" ? "Passer en mode clair" : "Passer en mode sombre");
    auxThemes.forEach(function (f) { f(); });
  }
  var bascule = document.querySelector("[data-theme-bascule]");
  if (bascule) {
    bascule.addEventListener("click", function () {
      var nouveau = themeEffectif() === "sombre" ? "clair" : "sombre";
      racine.setAttribute("data-theme", nouveau);
      try { localStorage.setItem("gipame-theme", nouveau); } catch (e) {}
      themeChange();
    });
  }
  if (sombreSysteme.addEventListener) sombreSysteme.addEventListener("change", themeChange);

  function variable(nom) { return getComputedStyle(racine).getPropertyValue(nom).trim(); }

  /* ---------------------------------------------------------------- Barre du haut */
  var barre = document.querySelector(".barre");
  function majBarre() { if (barre) barre.classList.toggle("est-pleine", window.scrollY > window.innerHeight * 0.75); }

  /* ---------------------------------------------------------------- 1. Ouverture */
  var ouverture = document.querySelector("[data-ouverture]");
  var toile = document.querySelector("[data-toile]");
  var texte = document.querySelector(".ouverture__texte");
  var legende = document.querySelector("[data-legende]");
  var indice = document.querySelector("[data-indice]");
  var serie = [];
  var finSerie = "";
  try {
    var donnees = JSON.parse(document.getElementById("serie-mensuelle").textContent);
    serie = donnees.valeurs || []; finSerie = donnees.fin || "";
  } catch (e) {}

  var ctx = toile ? toile.getContext("2d") : null;
  var L = 0, H = 0, ratio = 1, voies = [], couleurs = {}, progression = 0, visible = true, temps0 = performance.now();

  function lireCouleurs() {
    couleurs = {
      a: variable("--toile-a"), b: variable("--toile-b"), courbe: variable("--toile-courbe"),
      point: variable("--toile-point"), encreRVB: variable("--toile-texte"),
      lueur: parseFloat(variable("--toile-lueur")) || 0
    };
  }
  auxThemes.push(function () { lireCouleurs(); dessiner(performance.now()); });

  function hasard(graine) { var x = Math.sin(graine * 9301 + 49297) * 233280; return x - Math.floor(x); }

  function preparer() {
    if (!toile) return;
    ratio = Math.min(window.devicePixelRatio || 1, 2);
    L = toile.clientWidth; H = toile.clientHeight;
    toile.width = Math.round(L * ratio); toile.height = Math.round(H * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    var n = L < 600 ? 24 : 44, haut = L < 600 ? 0.14 : 0.12, ampleur = L < 600 ? 0.40 : 0.56;
    voies = [];
    for (var i = 0; i < n; i++) {
      var r = (i + hasard(i) * 0.8) / n;
      voies.push({
        y: H * (haut + ampleur * r),
        sens: hasard(i + 7) > 0.5 ? 1 : -1,
        vitesse: 40 + hasard(i + 13) * 170,
        trait: 30 + hasard(i + 17) * 150,
        vide: 70 + hasard(i + 23) * 260,
        epaisseur: 0.8 + r * 1.9,
        opacite: 0.22 + hasard(i + 29) * 0.6,
        decalage: hasard(i + 31) * 400
      });
    }
  }

  // Courbe des ventes : x en pixels → y en pixels (interpolation douce entre les mois)
  function courbeY(x) {
    if (serie.length < 2) return H * 0.42;
    var g = L * 0.06, d = L * 0.94, haut = H * (L < 600 ? 0.26 : 0.26), bas = H * (L < 600 ? 0.56 : 0.72);
    var min = Math.min.apply(null, serie), max = Math.max.apply(null, serie);
    var t = bornes((x - g) / (d - g)) * (serie.length - 1);
    var i = Math.min(Math.floor(t), serie.length - 2), f = t - i, f2 = (1 - Math.cos(f * Math.PI)) / 2;
    var v = serie[i] * (1 - f2) + serie[i + 1] * f2;
    return bas - (v - min) / (max - min) * (bas - haut);
  }

  function dessiner(maintenant) {
    if (!ctx) return;
    var e = adoucir(bornes((progression - 0.04) / 0.72));
    var t = calme.matches ? 0 : (maintenant - temps0) / 1000;
    ctx.clearRect(0, 0, L, H);
    ctx.globalCompositeOperation = couleurs.lueur ? "lighter" : "source-over";
    var pas = e > 0.4 ? 6 : (L < 600 ? 18 : 24);
    voies.forEach(function (v, k) {
      var alpha = v.opacite * Math.pow(1 - e, 1.4);
      if (alpha <= 0.01) return;
      ctx.beginPath();
      for (var x = -pas; x <= L + pas; x += pas) {
        var y = v.y * (1 - e) + courbeY(x) * e;
        if (x === -pas) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.setLineDash([v.trait * (1 + e * 3), v.vide * (1 - e * 0.85)]);
      ctx.lineDashOffset = -(v.decalage + t * v.vitesse * v.sens);
      ctx.lineWidth = v.epaisseur;
      ctx.lineCap = "round";
      ctx.strokeStyle = "rgba(" + (v.sens > 0 ? couleurs.a : couleurs.b) + "," + alpha.toFixed(3) + ")";
      ctx.stroke();
    });
    ctx.setLineDash([]);
    ctx.globalCompositeOperation = "source-over";

    // La courbe elle-même apparaît quand les voies se sont rangées
    var c = bornes((e - 0.55) / 0.45);
    if (c > 0 && serie.length > 1) {
      var g = L * 0.06, d = L * 0.94, bas = H * (L < 600 ? 0.56 : 0.72);
      ctx.beginPath();
      for (var x2 = g; x2 <= d; x2 += 4) { var y2 = courbeY(x2); if (x2 === g) ctx.moveTo(x2, y2); else ctx.lineTo(x2, y2); }
      // aire sous la courbe
      var aire = ctx.createLinearGradient(0, H * 0.2, 0, bas);
      aire.addColorStop(0, "rgba(" + couleurs.courbe + "," + (0.16 * c).toFixed(3) + ")");
      aire.addColorStop(1, "rgba(" + couleurs.courbe + ",0)");
      ctx.save(); ctx.lineTo(d, bas); ctx.lineTo(g, bas); ctx.closePath(); ctx.fillStyle = aire; ctx.fill(); ctx.restore();
      ctx.beginPath();
      for (var x3 = g; x3 <= d; x3 += 4) { var y3 = courbeY(x3); if (x3 === g) ctx.moveTo(x3, y3); else ctx.lineTo(x3, y3); }
      if (couleurs.lueur) { ctx.shadowColor = "rgba(" + couleurs.courbe + ",0.7)"; ctx.shadowBlur = 14; }
      ctx.lineWidth = 3; ctx.strokeStyle = "rgba(" + couleurs.courbe + "," + c.toFixed(3) + ")"; ctx.stroke();
      ctx.shadowBlur = 0;
      // repères des mois et ligne de base
      ctx.fillStyle = "rgba(" + couleurs.courbe + "," + (0.55 * c).toFixed(3) + ")";
      for (var m = 0; m < serie.length; m++) {
        var xm = g + (d - g) * m / (serie.length - 1);
        ctx.fillRect(xm - 0.75, bas + 10, 1.5, m % 12 === 0 ? 12 : 6);
      }
      // dernier mois : point ambre
      var yf = courbeY(d);
      ctx.beginPath(); ctx.arc(d, yf, 6, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(" + couleurs.point + "," + c.toFixed(3) + ")"; ctx.fill();
      ctx.beginPath(); ctx.arc(d, yf, 12 + 6 * (1 - c), 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(" + couleurs.point + "," + (0.35 * c).toFixed(3) + ")"; ctx.lineWidth = 1.5; ctx.stroke();
      // valeur du dernier mois, à gauche du point
      var derniere = serie[serie.length - 1].toLocaleString("fr-FR").replace(/\u202f|\u00a0/g, " ");
      ctx.font = "600 " + (L < 600 ? 15 : 18) + "px Archivo, sans-serif";
      ctx.textAlign = "right"; ctx.textBaseline = "middle";
      ctx.fillStyle = "rgba(" + couleurs.encreRVB + "," + c.toFixed(3) + ")";
      ctx.fillText(derniere + " véhicules", d - 22, yf - 2);
      ctx.font = "400 " + (L < 600 ? 12 : 13) + "px Archivo, sans-serif";
      ctx.fillStyle = "rgba(" + couleurs.encreRVB + "," + (0.7 * c).toFixed(3) + ")";
      ctx.fillText(finSerie, d - 22, yf + 18);
    }
  }

  function majOuverture() {
    if (!ouverture) return;
    var r = ouverture.getBoundingClientRect(), course = r.height - window.innerHeight;
    progression = course > 0 ? bornes(-r.top / course) : 0;
    if (texte) {
      var o = bornes(1 - progression * 2.4);
      texte.style.opacity = o.toFixed(3);
      texte.style.transform = "translateY(" + (-progression * 60).toFixed(1) + "px)";
      texte.style.visibility = o < 0.02 ? "hidden" : "visible";
    }
    if (legende) legende.style.opacity = bornes((progression - 0.62) / 0.22).toFixed(3);
    if (indice) indice.style.opacity = bornes(1 - progression * 8).toFixed(3);
  }

  function boucle(maintenant) {
    if (visible && !document.hidden) dessiner(maintenant);
    if (!calme.matches) requestAnimationFrame(boucle);
  }

  if (toile && ctx) {
    lireCouleurs(); preparer(); majOuverture(); dessiner(performance.now());
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (e) { visible = e[0].isIntersecting; }).observe(ouverture);
    }
    if (!calme.matches) requestAnimationFrame(boucle);
  }

  /* ---------------------------------------------------------------- 3. Segments */
  var segments = document.querySelector("[data-segments]");
  var piste = document.querySelector("[data-piste]");
  var course = 0;
  function preparerSegments() {
    if (!segments || !piste) return;
    var epingler = window.innerWidth > 820 && !calme.matches;
    segments.classList.toggle("est-epinglee", epingler);
    piste.style.transform = "";
    if (!epingler) { segments.style.height = ""; course = 0; return; }
    course = Math.max(0, piste.scrollWidth - window.innerWidth);
    segments.style.height = (window.innerHeight + course) + "px";
  }
  var photos = piste ? Array.prototype.slice.call(piste.querySelectorAll(".vehicule__visuel img")) : [];
  function majPhotos() {
    if (calme.matches || !photos.length) return;
    var milieu = window.innerWidth / 2;
    photos.forEach(function (img) {
      var r = img.parentNode.getBoundingClientRect();
      if (r.right < -200 || r.left > window.innerWidth + 200) return;
      var ecart = (r.left + r.width / 2 - milieu) / window.innerWidth;
      img.style.setProperty("--decalage", (-ecart * 46).toFixed(1) + "px");
    });
  }
  function majSegments() {
    majPhotos();
    if (!course) return;
    var r = segments.getBoundingClientRect();
    var p = bornes(-r.top / course);
    piste.style.transform = "translate3d(" + (-p * course).toFixed(1) + "px,0,0)";
  }

  /* ---------------------------------------------------------------- 4. Cycle */
  var cycle = document.querySelector(".cycle__etapes");
  function majCycle() {
    if (!cycle) return;
    if (calme.matches) { cycle.style.setProperty("--trace", "1"); return; }
    var r = cycle.getBoundingClientRect(), vh = window.innerHeight;
    cycle.style.setProperty("--trace", adoucir(bornes((vh * 0.92 - r.top) / (vh * 0.55))).toFixed(3));
  }

  /* ---------------------------------------------------------------- 5. Confidentialité */
  var schema = document.querySelector("[data-schema]");
  var points = [], barreSecret, etiquette;
  function preparerSchema() {
    if (!schema) return;
    var groupe = schema.querySelector("[data-points]");
    barreSecret = schema.querySelector("[data-barre]");
    etiquette = schema.querySelector("[data-etiquette]");
    groupe.innerHTML = "";
    points = [];
    var palette = variable("--secret-points").split(",").map(function (s) { return s.trim(); });
    var ns = "http://www.w3.org/2000/svg";
    for (var i = 0; i < 14; i++) {
      var c = document.createElementNS(ns, "circle");
      var p = {
        x: 24 + hasard(i + 101) * 220, y: 30 + hasard(i + 151) * 210, r: 7 + hasard(i + 201) * 9,
        cx: 332 + (hasard(i + 251) - 0.5) * 36, cy: 262 - i * 14, el: c
      };
      c.setAttribute("fill", palette[i % palette.length] || "#888");
      groupe.appendChild(c);
      points.push(p);
    }
    majSchema();
  }
  auxThemes.push(preparerSchema);
  function majSchema() {
    if (!schema || !points.length) return;
    var vh = window.innerHeight, r = schema.getBoundingClientRect();
    var q = calme.matches ? 1 : bornes((vh * 0.9 - r.top) / (vh * 0.75));
    points.forEach(function (p, i) {
      var t = adoucir(bornes(q * 1.25 - i * 0.02));
      p.el.setAttribute("cx", (p.x + (p.cx - p.x) * t).toFixed(1));
      p.el.setAttribute("cy", (p.y + (p.cy - p.y) * t).toFixed(1));
      p.el.setAttribute("r", (p.r * (1 - 0.6 * t)).toFixed(2));
      p.el.setAttribute("opacity", (1 - bornes((t - 0.75) / 0.25)).toFixed(3));
    });
    var h = 230 * adoucir(bornes((q - 0.55) / 0.45));
    barreSecret.setAttribute("y", (270 - h).toFixed(1));
    barreSecret.setAttribute("height", h.toFixed(1));
    etiquette.style.opacity = bornes((q - 0.85) / 0.15).toFixed(3);
  }

  /* ---------------------------------------------------------------- 2. Chiffres : comptage à la première apparition */
  var valeurs = Array.prototype.slice.call(document.querySelectorAll(".chiffre__valeur")).filter(function (el) { return /^[+\-]?\d/.test(el.textContent.trim()); });
  if (valeurs.length && !calme.matches && "IntersectionObserver" in window) {
    var compter = function (el) {
      var texte = el.textContent, m = texte.match(/[\d\s\u202f\u00a0]*\d(?:,\d+)?/);
      if (!m) return;
      var brut = m[0], decimales = (brut.split(",")[1] || "").length;
      var cible = parseFloat(brut.replace(/[\s\u202f\u00a0]/g, "").replace(",", "."));
      var debut = performance.now(), duree = 1400;
      el.style.minWidth = el.offsetWidth + "px";
      (function pas(t) {
        var k = adoucir(bornes((t - debut) / duree)), v = cible * k;
        var f = v.toLocaleString("fr-FR", { minimumFractionDigits: decimales, maximumFractionDigits: decimales }).replace(/\u202f/g, " ");
        el.textContent = texte.replace(brut.trim(), f);
        if (k < 1) requestAnimationFrame(pas); else el.textContent = texte;
      })(debut);
    };
    var obs = new IntersectionObserver(function (entrees) {
      entrees.forEach(function (e) { if (e.isIntersecting) { obs.unobserve(e.target); compter(e.target); } });
    }, { threshold: 0.6 });
    valeurs.forEach(function (el) { obs.observe(el); });
  }

  /* ---------------------------------------------------------------- Boucle de défilement */
  var attente = false;
  function surDefilement() {
    if (attente) return;
    attente = true;
    requestAnimationFrame(function () {
      attente = false;
      majBarre(); majOuverture(); majSegments(); majCycle(); majSchema();
      if (calme.matches) dessiner(performance.now());
    });
  }
  window.addEventListener("scroll", surDefilement, { passive: true });
  window.addEventListener("resize", function () { preparer(); preparerSegments(); surDefilement(); dessiner(performance.now()); });
  if (calme.addEventListener) calme.addEventListener("change", function () { location.reload(); });

  preparerSegments(); preparerSchema(); themeChange(); surDefilement();
})();
