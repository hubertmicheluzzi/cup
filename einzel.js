/* einzel.js – Einzelspiele im Cup-Baum (27.10.2026)
   Klinkt sich in die bestehenden Seiten ein, ohne sie umzubauen:
   - Handy (handy.html): ergänzt die Infobox (#infoText) beim Antippen einer Paarung.
   - PC (index.html): ergänzt das Hinweisfenster (title) beim Darüberfahren.
   Daten: data/<bewerb>.json, Feld "einzel" je gespieltem Spiel (von tools/fetch.py).
   Spieler nur mit Vornamen. Eingebunden mit einer Zeile vor </body>:
   <script src="einzel.js"></script> */
(function () {
  "use strict";
  const cache = {};
  const key = s => String(s == null ? "" : s).replace(/\s+/g, "").toUpperCase();
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const bewerb = () => (location.hash || "").slice(1);

  function daten(id) {
    if (!id) return Promise.resolve(null);
    if (!cache[id]) {
      cache[id] = fetch("data/" + id + ".json?t=" + Date.now(), {cache: "no-store"})
        .then(r => (r.ok ? r.json() : null)).catch(() => null);
      setTimeout(() => { delete cache[id]; }, 10 * 60 * 1000);
    }
    return cache[id];
  }

  async function spielZu(heim, gast) {
    const d = await daten(bewerb());
    if (!d) return null;
    const h = key(heim), g = key(gast);
    const treffer = (d.spiele || []).filter(s => s.einzel && s.einzel.length &&
      ((key(s.heim) === h && key(s.gast) === g) || (key(s.heim) === g && key(s.gast) === h)));
    return treffer.length ? treffer[treffer.length - 1] : null;
  }

  /* ---------- Handy: Infobox ---------- */
  const info = document.getElementById("infoText");
  if (info) {
    const ergaenzen = async () => {
      if (info.querySelector(".ez")) return;
      const m = /<br>([^<]+?) – ([^<]+?)(?: <b>|<br>|$)/.exec(info.innerHTML);
      if (!m) return;
      const s = await spielZu(m[1].trim(), m[2].trim());
      if (!s || info.querySelector(".ez")) return;
      const zeilen = s.einzel.map(e => {
        const sh = e.sieger === "H";
        return `<div style="display:grid;grid-template-columns:34px 1fr auto;gap:6px">` +
          `<span style="opacity:.6">${esc(e.nr)}</span>` +
          `<span>${sh ? "<b>" + esc(e.heim) + "</b>" : esc(e.heim)} – ${sh ? esc(e.gast) : "<b>" + esc(e.gast) + "</b>"}</span>` +
          `<span style="font-variant-numeric:tabular-nums">${esc(e.saetze)}</span></div>`;
      }).join("");
      const box = document.createElement("div");
      box.className = "ez";
      box.style.cssText = "margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,.2);font-size:12px;line-height:1.5;max-height:40vh;overflow:auto";
      box.innerHTML = `<div style="opacity:.7;margin-bottom:2px">Einzelspiele (${esc(s.heim)} – ${esc(s.gast)})</div>` + zeilen;
      info.appendChild(box);
    };
    new MutationObserver(ergaenzen).observe(info, {childList: true});
  }

  /* ---------- PC: Hinweisfenster (title) ---------- */
  if (!info) {
    const MARKE = "\nEinzelspiele:";
    const pending = new WeakSet();
    const ergaenzen = async el => {
      const t = el.getAttribute("title") || "";
      if (!t || t.includes(MARKE) || pending.has(el)) return;
      const m = /^[^\n]*: (.+?) – (.+?)$/m.exec(t);
      if (!m) return;
      pending.add(el);
      const s = await spielZu(m[1].trim(), m[2].trim());
      pending.delete(el);
      if (!s || (el.getAttribute("title") || "") !== t) return;
      const zeilen = s.einzel.map(e => `${e.nr}  ${e.heim} – ${e.gast}  ${e.saetze}`).join("\n");
      el.setAttribute("title", t + "\n" + MARKE + "\n" + zeilen);
    };
    document.addEventListener("mouseover", ev => {
      let el = ev.target;
      while (el && el !== document.body) {
        if (el.hasAttribute && el.hasAttribute("title")) { ergaenzen(el); break; }
        el = el.parentElement;
      }
    }, true);
  }
})();
