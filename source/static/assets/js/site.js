/* Blind World Hub: display settings, menu, app filters, search, videos and the owner forms. No libraries. */
(function () {
  "use strict";
  var doc = document.documentElement;

  function store(key, value) {
    try {
      if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value);
    } catch (e) { /* private mode: the setting lasts for this page only */ }
  }
  function read(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
  }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  /* ------------------------------------------------ disclosure buttons: Menu and Display settings */
  function disclosure(btn, panel, onClass) {
    if (!btn || !panel) return;
    btn.addEventListener("click", function () {
      var open = btn.getAttribute("aria-expanded") !== "true";
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      if (onClass) panel.classList.toggle(onClass, open); else panel.hidden = !open;
      if (open && !onClass) { var first = panel.querySelector("button"); if (first) first.focus(); }
    });
  }
  disclosure($(".menu-btn"), $("#site-nav"), "open");
  disclosure($(".settings-btn"), $("#display-settings"));

  /* ------------------------------------------------ display settings */
  var STEPS = [0.85, 1, 1.15, 1.3, 1.5, 1.75, 2];
  var status = $(".settings-status");
  function say(text) {
    if (!status) return;
    status.textContent = "";
    setTimeout(function () { status.textContent = text; }, 60);
  }
  function currentScale() {
    var s = parseFloat(getComputedStyle(doc).getPropertyValue("--scale")) || 1;
    var best = 1;
    STEPS.forEach(function (v) { if (Math.abs(v - s) < Math.abs(best - s)) best = v; });
    return best;
  }
  $all("[data-text]").forEach(function (b) {
    b.addEventListener("click", function () {
      var dir = parseInt(b.getAttribute("data-text"), 10);
      var i = STEPS.indexOf(currentScale());
      var next = dir === 0 ? 1 : STEPS[Math.max(0, Math.min(STEPS.length - 1, i + dir))];
      doc.style.setProperty("--scale", String(next));
      store("bwh-text", next === 1 ? null : String(next));
      say("Text size " + Math.round(next * 100) + " percent.");
    });
  });

  var systemDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)");
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)");
  function isDark() {
    var t = doc.getAttribute("data-theme");
    return t ? t === "dark" : !!(systemDark && systemDark.matches);
  }
  function motionOn() { return doc.getAttribute("data-motion") !== "off"; }
  function syncToggles() {
    $all("[data-toggle]").forEach(function (b) {
      var k = b.getAttribute("data-toggle");
      var on = k === "contrast" ? doc.getAttribute("data-contrast") === "high" : k === "theme" ? isDark() : motionOn();
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }
  $all("[data-toggle]").forEach(function (b) {
    b.addEventListener("click", function () {
      var k = b.getAttribute("data-toggle");
      if (k === "contrast") {
        var high = doc.getAttribute("data-contrast") !== "high";
        if (high) doc.setAttribute("data-contrast", "high"); else doc.removeAttribute("data-contrast");
        store("bwh-contrast", high ? "1" : null);
        say(high ? "High contrast on." : "High contrast off.");
      } else if (k === "theme") {
        var dark = !isDark();
        doc.setAttribute("data-theme", dark ? "dark" : "light");
        store("bwh-theme", dark ? "dark" : "light");
        say(dark ? "Dark theme on." : "Dark theme off, light theme on.");
      } else {
        var on = !motionOn();
        if (on) doc.removeAttribute("data-motion"); else doc.setAttribute("data-motion", "off");
        store("bwh-motion", on ? null : "0");
        say(on ? "3D effects on." : "3D effects off.");
        document.dispatchEvent(new CustomEvent("bwh-motion", { detail: on }));
      }
      syncToggles();
    });
  });
  syncToggles();
  window.BWH = { motionOn: motionOn, reduceMotion: function () { return !!(reduceMotion && reduceMotion.matches); } };

  /* ------------------------------------------------ YouTube: a picture until play is pressed */
  document.addEventListener("click", function (e) {
    var btn = e.target.closest ? e.target.closest(".yt-play") : null;
    if (!btn) return;
    var box = btn.parentNode;
    var id = box.getAttribute("data-id");
    var f = document.createElement("iframe");
    f.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(id) + "?autoplay=1&rel=0";
    f.title = (box.getAttribute("data-title") || "Video") + ", YouTube video";
    f.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture";
    f.allowFullscreen = true;
    box.innerHTML = "";
    box.appendChild(f);
    f.focus();
  });

  /* ------------------------------------------------ app filters */
  var list = $("#app-list");
  if (list) {
    var rows = $all(".app-row", list);
    var ft = $("#f-text"), fc = $("#f-cat"), fp = $("#f-plat"), count = $("#app-count");
    var timer = null;
    var apply = function () {
      var words = (ft.value || "").toLowerCase().split(/\s+/).filter(Boolean);
      var c = fc.value, p = fp.value, n = 0;
      rows.forEach(function (r) {
        var text = r.getAttribute("data-text") || "";
        var show = (!c || r.getAttribute("data-cat") === c) && (!p || r.getAttribute("data-plat") === p) &&
          words.every(function (w) { return text.indexOf(w) >= 0; });
        r.hidden = !show;
        if (show) n++;
      });
      count.textContent = n === 0 ? "No apps match. Try another word or All categories." :
        n + (n === 1 ? " app shown." : " apps shown.");
    };
    [fc, fp].forEach(function (s) { s.addEventListener("change", apply); });
    ft.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(apply, 350); });
  }

  /* ------------------------------------------------ search page */
  var results = $("#search-results");
  if (results) {
    var params = new URLSearchParams(location.search);
    var q = (params.get("q") || "").trim();
    var input = $("#search-q");
    var st = $("#search-status");
    if (input) input.value = q;
    if (!q) {
      st.textContent = "Type a word, such as voice or reader, and press Search.";
    } else {
      st.textContent = "Searching.";
      fetch("/search.json").then(function (r) { return r.json(); }).then(function (items) {
        var words = q.toLowerCase().split(/\s+/).filter(Boolean);
        var found = items.map(function (it) {
          var title = (it.t || "").toLowerCase(), all = (it.t + " " + it.d + " " + it.x + " " + it.k).toLowerCase();
          if (!words.every(function (w) { return all.indexOf(w) >= 0; })) return null;
          var score = 0;
          words.forEach(function (w) { if (title.indexOf(w) >= 0) score += 3; });
          if (it.k === "App") score += 1;
          return { it: it, score: score };
        }).filter(Boolean).sort(function (a, b) { return b.score - a.score; });
        results.innerHTML = "";
        found.slice(0, 60).forEach(function (f) {
          var li = document.createElement("li");
          var h = document.createElement("h2");
          var a = document.createElement("a");
          a.href = f.it.u; a.textContent = f.it.t;
          h.appendChild(a);
          var p = document.createElement("p");
          p.textContent = f.it.k + ". " + (f.it.d || "");
          li.appendChild(h); li.appendChild(p);
          results.appendChild(li);
        });
        st.textContent = found.length === 0 ? "No results for " + q + ". Try a shorter word." :
          found.length + (found.length === 1 ? " result" : " results") + " for " + q + ".";
      }).catch(function () { st.textContent = "Search could not load. Check your connection and try again."; });
    }
  }

  /* ------------------------------------------------ owner forms: open GitHub with everything filled in */
  function val(form, name) {
    var el = form.elements[name];
    return el ? String(el.value || "").trim() : "";
  }
  function slug(s) { return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "item"; }
  function stamp() {
    var d = new Date();
    function two(n) { return (n < 10 ? "0" : "") + n; }
    return d.getFullYear() + two(d.getMonth() + 1) + two(d.getDate()) + "-" + two(d.getHours()) + two(d.getMinutes());
  }
  function fail(id, text, field) {
    var e = document.getElementById(id);
    e.textContent = text;
    if (field) field.focus();
  }

  var addApp = $("#add-app");
  if (addApp) addApp.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var name = val(addApp, "name");
    if (!name) return fail("add-app-error", "Type the app or file name first.", addApp.elements.name);
    var version = val(addApp, "version");
    var lines = ["Name: " + name];
    if (version) lines.push("Version: " + version);
    lines.push("Category: " + val(addApp, "category"), "Platform: " + val(addApp, "platform"));
    [["summary", "Summary"], ["video", "Video"], ["playstore", "Play Store"], ["website", "Website"],
      ["virustotal", "VirusTotal"]].forEach(function (k) {
      var v = val(addApp, k[0]);
      if (v) lines.push(k[1] + ": " + v);
    });
    var body = lines.join("\n") + "\n\n" + val(addApp, "description");
    var tag = slug(name) + (version ? "-" + slug(version) : "") + "-" + stamp();
    var url = "https://github.com/" + addApp.getAttribute("data-repo") + "/releases/new?tag=" + encodeURIComponent(tag) +
      "&title=" + encodeURIComponent((name + " " + version).trim()) + "&body=" + encodeURIComponent(body);
    location.href = url;
  });

  var write = $("#write-article");
  if (write) write.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var title = val(write, "title");
    if (!title) return fail("write-error", "Type a title first.", write.elements.title);
    var kind = (write.querySelector("input[name=kind]:checked") || {}).value || "guide";
    var sum = val(write, "summary");
    var by = val(write, "author");
    var body = (by ? "Written by: " + by + "\n" : "") + (sum ? "Summary: " + sum + "\n" : "") +
      (by || sum ? "\n" : "") + val(write, "text");
    location.href = "https://github.com/" + write.getAttribute("data-repo") + "/issues/new?labels=" + kind +
      "&title=" + encodeURIComponent(title) + "&body=" + encodeURIComponent(body);
  });

  var addVideo = $("#add-video");
  if (addVideo) addVideo.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var link = val(addVideo, "video"), title = val(addVideo, "title");
    if (!/youtu\.?be/.test(link)) return fail("video-error", "Paste a YouTube link first.", addVideo.elements.video);
    if (!title) return fail("video-error", "Type a title first.", addVideo.elements.title);
    var sum = val(addVideo, "summary");
    var body = "Video: " + link + (sum ? "\nSummary: " + sum : "");
    location.href = "https://github.com/" + addVideo.getAttribute("data-repo") + "/issues/new?labels=video" +
      "&title=" + encodeURIComponent(title) + "&body=" + encodeURIComponent(body);
  });
})();
