/* Observatoire GIPAME — comportements légers (sans dépendance) :
   menu mobile, dropzone, disparition des messages, graphiques Chart.js (si présent). */
(function () {
  "use strict";

  // Menu mobile
  var bouton = document.querySelector("[data-menu]");
  if (bouton) {
    bouton.addEventListener("click", function () {
      var nav = document.getElementById("navigation");
      var ouvert = nav.classList.toggle("nav--ouverte");
      bouton.setAttribute("aria-expanded", ouvert ? "true" : "false");
    });
  }

  // Messages flash : disparaissent après 8 s (restent accessibles au clavier avant)
  document.querySelectorAll("[data-flash]").forEach(function (m) {
    setTimeout(function () { m.style.transition = "opacity .4s"; m.style.opacity = "0"; setTimeout(function () { m.remove(); }, 400); }, 8000);
  });

  // Dropzone : glisser-déposer ou clic ; affiche le nom du fichier ; soumet le formulaire
  document.querySelectorAll("[data-dropzone]").forEach(function (zone) {
    var entree = zone.querySelector("input[type=file]");
    var nom = zone.querySelector("[data-nom-fichier]");
    var formulaire = zone.closest("form");
    var bouton = formulaire ? formulaire.querySelector("[data-bouton-depot]") : null;
    function choisi() {
      if (!entree.files.length) return;
      var f = entree.files[0];
      zone.classList.add("dropzone--pret");
      if (nom) nom.textContent = f.name + " (" + Math.max(1, Math.round(f.size / 1024)) + " Ko)";
      if (bouton) { bouton.disabled = false; bouton.focus(); }
      if (zone.hasAttribute("data-auto")) formulaire.requestSubmit();
    }
    ["dragenter", "dragover"].forEach(function (e) { zone.addEventListener(e, function (ev) { ev.preventDefault(); zone.classList.add("dropzone--survol"); }); });
    ["dragleave", "drop"].forEach(function (e) { zone.addEventListener(e, function (ev) { ev.preventDefault(); zone.classList.remove("dropzone--survol"); }); });
    zone.addEventListener("drop", function (ev) {
      if (ev.dataTransfer && ev.dataTransfer.files.length) { entree.files = ev.dataTransfer.files; choisi(); }
    });
    zone.addEventListener("click", function (ev) { if (ev.target !== entree) entree.click(); });
    zone.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); entree.click(); } });
    entree.addEventListener("change", choisi);
    if (formulaire) formulaire.addEventListener("submit", function () {
      var barre = formulaire.querySelector("[data-progression] > div");
      if (barre) { formulaire.querySelector("[data-progression]").hidden = false; barre.style.width = "90%"; }
      if (bouton) { bouton.disabled = true; bouton.textContent = "Vérification en cours…"; }
    });
  });

  // Graphiques : <canvas data-graphique='{"type":"line","labels":[...],"series":[{"label":..,"data":[..]}]}'>
  function dessiner() {
    if (!window.Chart) return;
    var style = getComputedStyle(document.documentElement);
    var couleurs = [style.getPropertyValue("--petrole-600").trim(), style.getPropertyValue("--nuit-900").trim(),
                    style.getPropertyValue("--succes-600").trim(), style.getPropertyValue("--alerte-600").trim(),
                    style.getPropertyValue("--petrole-300").trim(), style.getPropertyValue("--texte-3").trim()];
    Chart.defaults.font.family = style.getPropertyValue("--police");
    Chart.defaults.color = style.getPropertyValue("--texte-2").trim();
    document.querySelectorAll("canvas[data-graphique]").forEach(function (canvas) {
      var cfg = JSON.parse(canvas.getAttribute("data-graphique"));
      var datasets = cfg.series.map(function (s, i) {
        var c = s.couleur || couleurs[i % couleurs.length];
        return Object.assign({ label: s.label, data: s.data, borderColor: c, backgroundColor: cfg.type === "line" ? c + "22" : c,
          borderWidth: 2.5, tension: 0.35, pointRadius: 3, pointHoverRadius: 5, fill: cfg.type === "line" && i === 0, spanGaps: false,
          borderRadius: 6, maxBarThickness: 36 }, s.options || {});
      });
      new Chart(canvas, {
        type: cfg.type || "line",
        data: { labels: cfg.labels, datasets: datasets },
        options: {
          responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
          plugins: {
            legend: { display: datasets.length > 1, position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
            tooltip: { callbacks: { label: function (ctx) {
              var v = ctx.parsed.y; return " " + ctx.dataset.label + " : " + (v === null ? "non disponible" : v.toLocaleString("fr-FR")); } } }
          },
          scales: {
            x: { grid: { display: false } },
            y: { beginAtZero: true, grid: { color: "rgba(11,18,56,.06)" }, ticks: { precision: 0, callback: function (v) { return v.toLocaleString("fr-FR"); } } }
          }
        }
      });
    });
  }
  if (document.querySelector("canvas[data-graphique]")) {
    var s = document.createElement("script");
    s.src = document.body.getAttribute("data-chart-js") || "/static/portail/js/chart.umd.js";
    s.onload = dessiner;
    document.body.appendChild(s);
  }
  // Démonstration : un clic sur un profil remplit l'adresse et le mot de passe de la page de connexion.
  document.querySelectorAll("[data-remplir-email]").forEach(function (bouton) {
    bouton.addEventListener("click", function () {
      var email = document.getElementById("id_username"), mdp = document.getElementById("id_password");
      if (!email || !mdp) return;
      email.value = bouton.getAttribute("data-remplir-email");
      mdp.value = bouton.getAttribute("data-remplir-mdp");
      document.querySelectorAll(".compte-demo.est-choisi").forEach(function (b) { b.classList.remove("est-choisi"); });
      bouton.classList.add("est-choisi");
      var envoyer = email.form && email.form.querySelector("button[type=submit]");
      if (envoyer) envoyer.focus();
    });
  });
  // Déconnexion : confirmation (un clic malheureux ne doit pas fermer la session). Sans JavaScript, le bouton
  // déconnecte directement.
  var dialogue = document.getElementById("dialogue-deconnexion");
  document.querySelectorAll("form[data-confirmer-deconnexion]").forEach(function (formulaire) {
    formulaire.addEventListener("submit", function (ev) {
      if (!dialogue || typeof dialogue.showModal !== "function" || formulaire.dataset.confirme === "1") return;
      ev.preventDefault();
      dialogue.showModal();
      dialogue.querySelector("[data-annuler]").focus();
      dialogue.querySelector("[data-annuler]").onclick = function () { dialogue.close(); };
      dialogue.querySelector("[data-confirmer]").onclick = function () {
        formulaire.dataset.confirme = "1";
        dialogue.close();
        formulaire.submit();
      };
    });
  });
  if (dialogue) dialogue.addEventListener("click", function (ev) { if (ev.target === dialogue) dialogue.close(); });
})();
