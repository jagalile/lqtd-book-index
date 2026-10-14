"use strict";

// Tono de color de cada temática (HSL). Los nombres vienen de books.json.
const HUES = {
  salud: 145, psicologia: 268, ciencia: 205, desarrollo: 38, filosofia: 228,
  espiritualidad: 300, misterio: 175, crimen: 0, sociedad: 18, historia: 48,
  tecnologia: 190, economia: 118, comunicacion: 330, sexualidad: 345, crianza: 85,
  deporte: 160, memorias: 12, novela: 245, poesia: 318, humor: 60, arte: 282,
};
const PLATFORMS = [
  ["yt", "YouTube", "#ff0000", (v) => `https://www.youtube.com/watch?v=${v}`],
  ["sp", "Spotify", "#1db954", (v) => v],
  ["iv", "iVoox", "#f79c00", (v) => v],
  ["am", "Amazon Music", "#25d1da", (v) => v],
];
const SHELF_SIZE = 18;

const $ = (id) => document.getElementById(id);
const els = {
  q: $("q"), rel: $("rel"), sort: $("sort"), chips: $("chips"), shelves: $("shelves"), grid: $("grid"),
  count: $("count"), empty: $("empty"), lede: $("lede"), updated: $("updated"), dialog: $("detail"),
};

let books = [];
let themes = {};
const byId = new Map();
const state = { q: "", theme: "", rel: "", sort: "new" };

// --- Utilidades --------------------------------------------------------------

const norm = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dateFmt = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", year: "numeric" });
const fmtDate = (d) => (d ? dateFmt.format(new Date(d + "T12:00:00")) : "");
const hue = (b) => HUES[b.th?.[0]] ?? 25;
const collator = new Intl.Collator("es", { sensitivity: "base" });

function coverHTML(b) {
  const gen = `<div class="gen"><span class="gt">${esc(b.t)}</span><span class="ga">${esc(b.a || "")}</span></div>`;
  return `<div class="cover" style="--h:${hue(b)}">` +
    (b.m ? `<span class="ribbon">Mencionado</span>` : "") +
    (b.cover ? `<img class="cv" src="${esc(b.cover)}" alt="" loading="lazy" decoding="async">` +
      `<template>${gen}</template>` : gen) + `</div>`;
}

// Portada que no carga (Open Library a veces falla): se sustituye por la generada.
document.addEventListener("error", (ev) => {
  const img = ev.target;
  if (img.tagName === "IMG" && img.classList.contains("cv")) {
    const tpl = img.nextElementSibling;
    if (tpl?.tagName === "TEMPLATE") img.replaceWith(tpl.content.cloneNode(true));
  }
}, true);

const bookHTML = (b) => `<button type="button" class="book" data-id="${esc(b.id)}">${coverHTML(b)}
  <span class="bt">${esc(b.t)}</span><span class="ba">${esc(b.a || "")}</span></button>`;

function tagHTML(t) {
  return `<button type="button" class="tag" data-theme="${esc(t)}" style="--h:${HUES[t] ?? 25}">${esc(themes[t] || t)}</button>`;
}

// --- Estado en la URL --------------------------------------------------------

function readURL() {
  const p = new URLSearchParams(location.search);
  state.q = p.get("q") || "";
  state.theme = p.get("tema") || "";
  state.rel = { invitados: "g", mencionados: "m" }[p.get("libros")] || "";
  state.sort = p.get("orden") || "new";
}

function writeURL() {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  if (state.theme) p.set("tema", state.theme);
  if (state.rel) p.set("libros", state.rel === "m" ? "mencionados" : "invitados");
  if (state.sort !== "new") p.set("orden", state.sort);
  const qs = p.toString();
  history.replaceState(null, "", (qs ? `?${qs}` : location.pathname) + location.hash);
}

// --- Vista -------------------------------------------------------------------

const SORTS = {
  new: (a, b) => b.date.localeCompare(a.date) || collator.compare(a.t, b.t),
  title: (a, b) => collator.compare(a.t, b.t),
  author: (a, b) => collator.compare(a.a || "", b.a || "") || collator.compare(a.t, b.t),
};

function apply() {
  const terms = norm(state.q.trim()).split(/\s+/).filter(Boolean);
  const filtering = terms.length || state.theme || state.rel;
  const list = books
    .filter((b) => (!state.theme || b.th?.includes(state.theme)) &&
      (!state.rel || (state.rel === "m") === !!b.m) &&
      terms.every((t) => b._hay.includes(t)))
    .sort(SORTS[state.sort] || SORTS.new);

  els.shelves.hidden = !!filtering;
  els.grid.hidden = !filtering;
  if (filtering) {
    els.grid.innerHTML = list.map((b) => `<li>${bookHTML(b)}</li>`).join("");
    const what = [
      state.rel === "g" ? (list.length === 1 ? " de invitado" : " de invitados") : state.rel === "m" ? (list.length === 1 ? " mencionado" : " mencionados") : "",
      state.theme ? ` de ${themes[state.theme] || state.theme}` : "",
    ].join("");
    els.count.textContent = `${list.length} ${list.length === 1 ? "libro" : "libros"}${what}`;
  } else {
    renderShelves(list);
    els.count.textContent = `${books.length} libros en ${Object.keys(themes).length} temáticas`;
  }
  els.empty.hidden = list.length > 0;
  renderChips();
  writeURL();
}

function renderShelves(sorted) {
  const count = (t) => books.filter((b) => b.th?.includes(t)).length;
  const order = Object.keys(themes).filter(count).sort((a, b) => count(b) - count(a));
  const recent = [...books].sort(SORTS.new).slice(0, SHELF_SIZE);
  const shelf = (id, title, list, total) => `<section class="shelf" style="--h:${HUES[id] ?? 25}">
    <div class="shelf-head"><h2>${esc(title)} <small>${total}</small></h2>
    ${id !== "_new" ? `<button type="button" class="more" data-theme="${esc(id)}">Ver todos →</button>` : ""}</div>
    <ul class="row">${list.map((b) => `<li>${bookHTML(b)}</li>`).join("")}</ul></section>`;
  els.shelves.innerHTML =
    shelf("_new", "Recién llegados", recent, "") +
    order.map((t) => {
      const list = sorted.filter((b) => b.th?.includes(t));
      return shelf(t, themes[t], list.slice(0, SHELF_SIZE), list.length);
    }).join("");
}

function renderChips() {
  const counts = {};
  books.forEach((b) => (b.th || []).forEach((t) => (counts[t] = (counts[t] || 0) + 1)));
  const order = Object.keys(themes).filter((t) => counts[t]).sort((a, b) => counts[b] - counts[a]);
  els.chips.innerHTML =
    `<button type="button" class="chip" data-theme="" aria-pressed="${!state.theme}">Todas</button>` +
    order.map((t) => `<button type="button" class="chip" data-theme="${esc(t)}" style="--h:${HUES[t] ?? 25}"
      aria-pressed="${state.theme === t}"><span class="dot"></span>${esc(themes[t])}<small>${counts[t]}</small></button>`).join("");
}

function setTheme(t) {
  state.theme = state.theme === t ? "" : t;
  apply();
  document.querySelector(".toolbar").scrollIntoView({ block: "start" });
  if (els.dialog.open) els.dialog.close();
}

// --- Ficha -------------------------------------------------------------------

function buyLinks(b) {
  const q = encodeURIComponent(`${b.t} ${b.a || ""}`.trim());
  const links = [];
  if (b.buy) links.push([b.buy, "Comprar (enlace del episodio)"]);
  links.push([`https://www.todostuslibros.com/busquedas?keyword=${encodeURIComponent(b.isbn || `${b.t} ${b.a || ""}`)}`, "Librerías independientes"]);
  if (!b.buy) links.push([`https://www.amazon.es/s?k=${q}&i=stripbooks`, "Amazon"]);
  return links.map(([href, text], i) =>
    `<a href="${esc(href)}" target="_blank" rel="noopener nofollow" class="${i === 0 ? "primary" : ""}">${esc(text)}</a>`).join("");
}

const pad = (n) => String(n).padStart(2, "0");
const clock = (s) => (s >= 3600 ? `${Math.floor(s / 3600)}:${pad(Math.floor(s / 60) % 60)}` : `${Math.floor(s / 60)}`) + `:${pad(s % 60)}`;

// Mención encontrada en la transcripción: cita, quién y enlace al minuto exacto.
function mentionHTML(e) {
  if (!e.q && e.at == null) return "";
  const who = { "Álex": "Álex Fidalgo", "invitado": "el invitado" }[e.by] || e.by || "";
  const at = e.at != null && e.yt
    ? `<a href="https://www.youtube.com/watch?v=${esc(e.yt)}&t=${e.at}s" target="_blank" rel="noopener">▶ ${clock(e.at)}</a>`
    : (e.at != null ? clock(e.at) : "");
  return `<blockquote class="ep-quote">${e.q ? `«${esc(e.q)}»` : ""}
    <footer>${who ? `Lo menciona ${esc(who)}` : "Se menciona"}${at ? ` en el minuto ${at}` : ""}</footer></blockquote>`;
}

function epHTML(e) {
  const thumb = e.yt
    ? `<img src="https://i.ytimg.com/vi/${esc(e.yt)}/mqdefault.jpg" alt="" loading="lazy">`
    : (e.n ? `#${e.n}` : "LQTD");
  const links = PLATFORMS.filter(([k]) => e[k]).map(([k, name, color, url]) =>
    `<a href="${esc(url(e[k]))}" target="_blank" rel="noopener"><span class="dot" style="background:${color}"></span>${name}</a>`).join("");
  return `<li class="ep"><div class="ep-thumb">${thumb}</div><div>
    <p class="ep-title">${esc(e.title)}</p>
    <p class="ep-meta">${[e.n ? `Episodio #${e.n}` : "", fmtDate(e.date)].filter(Boolean).join(" · ")}</p>
    ${mentionHTML(e)}
    <div class="ep-links">${links}</div></div></li>`;
}

// --- Transición de la portada entre la lista y la ficha ----------------------
// View Transitions API: la portada pulsada «vuela» hasta la ficha y vuelve al
// cerrarla. En navegadores sin soporte (o con movimiento reducido) se abre y
// cierra sin animación.

const canMorph = () => document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches;
let fromCover = null; // portada de la lista desde la que se abrió la ficha
const dialogCover = () => $("d-cover").querySelector(".cover");

function inView(el) {
  if (!el?.isConnected) return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
}

// Espera (como mucho 300 ms) a que la imagen esté lista para que la ficha no
// aparezca con la portada en blanco en mitad de la animación.
function coverReady() {
  const img = dialogCover()?.querySelector("img");
  return img ? Promise.race([img.decode().catch(() => {}), new Promise((r) => setTimeout(r, 300))]) : Promise.resolve();
}

function morph(from, update, to) {
  from.style.viewTransitionName = "book-cover";
  const t = document.startViewTransition(async () => {
    from.style.viewTransitionName = "";
    await update();
    const target = to();
    if (target) target.style.viewTransitionName = "book-cover";
  });
  t.finished.finally(() => { const target = to(); if (target) target.style.viewTransitionName = ""; });
}

function openDetailFrom(b, cover) {
  if (!canMorph() || els.dialog.open || !inView(cover)) return openDetail(b);
  fromCover = cover;
  morph(cover, () => { openDetail(b); return coverReady(); }, dialogCover);
}

function closeDetail() {
  if (!els.dialog.open) return;
  const back = fromCover;
  if (!canMorph() || !dialogCover() || !inView(back)) return els.dialog.close();
  morph(dialogCover(), () => els.dialog.close(), () => back);
}

function openDetail(b, push = true) {
  els.dialog.querySelector(".d-wrap").style.setProperty("--h", hue(b));
  $("d-cover").innerHTML = coverHTML(b).replace('loading="lazy"', 'fetchpriority="high"');
  $("d-rel").textContent = b.m ? "Mencionado en el episodio" : "Libro del invitado";
  $("d-tags").innerHTML = (b.th || []).map(tagHTML).join("");
  $("d-title").textContent = b.t;
  $("d-author").textContent = b.a || "";
  $("d-meta").textContent = [b.y, b.pub, b.isbn && `ISBN ${b.isbn}`].filter(Boolean).join(" · ");
  $("d-buy").innerHTML = buyLinks(b);
  $("d-eps").innerHTML = (b.eps || []).map(epHTML).join("");
  if (push) history.replaceState(null, "", location.pathname + location.search + "#" + encodeURIComponent(b.id));
  if (!els.dialog.open) els.dialog.showModal();
  els.dialog.scrollTop = 0;
}

function openFromHash() {
  const b = byId.get(decodeURIComponent(location.hash.slice(1)));
  if (b) openDetail(b, false);
}

// --- Arranque ----------------------------------------------------------------

function bind() {
  let t;
  els.q.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => { state.q = els.q.value; apply(); }, 120);
  });
  els.sort.addEventListener("change", () => { state.sort = els.sort.value; apply(); });
  els.rel.addEventListener("change", () => { state.rel = els.rel.value; apply(); });
  $("reset").addEventListener("click", () => {
    Object.assign(state, { q: "", theme: "", rel: "" });
    els.q.value = ""; els.rel.value = "";
    apply();
  });
  document.addEventListener("click", (ev) => {
    const themeBtn = ev.target.closest("[data-theme]");
    if (themeBtn) return setTheme(themeBtn.dataset.theme);
    const book = ev.target.closest(".book");
    if (book) openDetailFrom(byId.get(book.dataset.id), book.querySelector(".cover"));
  });
  els.dialog.addEventListener("close", () => {
    fromCover = null;
    history.replaceState(null, "", location.pathname + location.search);
  });
  els.dialog.addEventListener("click", (ev) => { if (ev.target === els.dialog) closeDetail(); });
  // Botón × y Escape: cierre animado de vuelta a la lista.
  els.dialog.querySelector(".close-form").addEventListener("submit", (ev) => { ev.preventDefault(); closeDetail(); });
  els.dialog.addEventListener("cancel", (ev) => { ev.preventDefault(); closeDetail(); });
  window.addEventListener("hashchange", openFromHash);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "/" && document.activeElement !== els.q && !els.dialog.open) {
      ev.preventDefault();
      els.q.focus();
    }
  });
}

async function init() {
  readURL();
  bind();
  let data;
  try {
    data = await (await fetch("books.json")).json();
  } catch {
    els.count.textContent = "No se pudieron cargar los libros. Recarga la página.";
    return;
  }
  themes = data.themes;
  books = data.books;
  books.forEach((b) => {
    b.date ||= "";
    b._hay = norm([b.t, b.a, b.pub, b.isbn, ...(b.th || []).map((t) => themes[t]),
      ...(b.eps || []).map((e) => `${e.title} #${e.n || ""}`)].join(" "));
    byId.set(b.id, b);
  });
  els.q.value = state.q;
  els.sort.value = state.sort;
  els.rel.value = state.rel;
  const eps = new Set(books.flatMap((b) => (b.eps || []).map((e) => e.title))).size;
  const mentioned = books.filter((b) => b.m).length;
  els.lede.textContent = `${books.length - mentioned} libros de los invitados de Álex Fidalgo y ${mentioned} mencionados en sus conversaciones, de ${eps} episodios, ordenados por temática.`;
  if (data.updated) els.updated.textContent = `Actualizado el ${fmtDate(data.updated.slice(0, 10))}.`;
  apply();
  openFromHash();
}

init();
