"use strict";

const PAGE = 48;
const KINDS = {
  "episodio": "Episodios",
  "ultima-hora": "Última hora",
  "especial": "Especiales",
  "entre-amigos": "Entre amigos",
  "otro": "Otros",
};
const PLATFORMS = [
  ["yt", "YouTube", "#ff0000", (v) => `https://www.youtube.com/watch?v=${v}`],
  ["sp", "Spotify", "#1db954", (v) => v],
  ["iv", "iVoox", "#f79c00", (v) => v],
];

const $ = (id) => document.getElementById(id);
const els = {
  q: $("q"), year: $("year"), sort: $("sort"), chips: $("chips"), grid: $("grid"),
  count: $("count"), empty: $("empty"), sentinel: $("sentinel"), lede: $("lede"),
  updated: $("updated"), dialog: $("detail"),
};

let all = [];
let results = [];
let shown = 0;
const state = { q: "", kind: "", tag: "", year: "", sort: "new", video: false, book: false };

// --- Utilidades --------------------------------------------------------------

const norm = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dateFmt = new Intl.DateTimeFormat("es-ES", { day: "numeric", month: "short", year: "numeric" });
const fmtDate = (d) => (d ? dateFmt.format(new Date(d + "T12:00:00")) : "");
function fmtDur(s) {
  if (!s) return "";
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  return h ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
}
const shortDur = (s) => (s ? `${Math.floor(s / 3600)}:${String(Math.round((s % 3600) / 60)).padStart(2, "0")}` : "");
const key = (e) => (e.n != null && e.kind === "episodio" ? `${e.n}${e.part || ""}` : e.id);
function label(e) {
  if (e.kind !== "episodio") return KINDS[e.kind] || "";
  return e.n != null ? `#${e.n}${e.part ? ` (${e.part})` : ""}` : "";
}

function linkify(text) {
  return text
    .split(/\n{2,}/)
    .map((p) => "<p>" + esc(p).replace(/\n/g, "<br>")
      .replace(/https?:\/\/[^\s<]+[^\s<.,;:)!?]/g, (u) => `<a href="${u}" target="_blank" rel="noopener nofollow">${u}</a>`) + "</p>")
    .join("");
}

// --- Estado en la URL --------------------------------------------------------

function readURL() {
  const p = new URLSearchParams(location.search);
  state.q = p.get("q") || "";
  state.kind = p.get("tipo") || "";
  state.tag = p.get("tag") || "";
  state.year = p.get("anio") || "";
  state.sort = p.get("orden") || "new";
  state.video = p.has("video");
  state.book = p.has("libro");
}

function writeURL() {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  if (state.kind) p.set("tipo", state.kind);
  if (state.tag) p.set("tag", state.tag);
  if (state.year) p.set("anio", state.year);
  if (state.sort !== "new") p.set("orden", state.sort);
  if (state.video) p.set("video", "");
  if (state.book) p.set("libro", "");
  const qs = p.toString().replace(/=(?=&|$)/g, "");
  history.replaceState(null, "", (qs ? `?${qs}` : location.pathname) + location.hash);
}

// --- Filtros -----------------------------------------------------------------

function matches(e, terms, num) {
  if (state.kind && e.kind !== state.kind) return false;
  if (state.tag && !(e.tags || []).includes(state.tag)) return false;
  if (state.year && !e.date.startsWith(state.year)) return false;
  if (state.video && !e.yt) return false;
  if (state.book && !e.book) return false;
  if (num != null) return e.n === num;
  return terms.every((t) => e._hay.includes(t));
}

function apply() {
  const q = norm(state.q.trim());
  const m = q.match(/^#?(\d{1,4})$/);
  const num = m ? Number(m[1]) : null;
  const terms = q.split(/\s+/).filter(Boolean);
  results = all.filter((e) => matches(e, terms, num));
  const by = {
    new: (a, b) => b.date.localeCompare(a.date),
    old: (a, b) => a.date.localeCompare(b.date),
    long: (a, b) => (b.dur || 0) - (a.dur || 0),
    short: (a, b) => (a.dur || 0) - (b.dur || 0),
  }[state.sort] || ((a, b) => b.date.localeCompare(a.date));
  results.sort(by);

  els.grid.replaceChildren();
  shown = 0;
  renderMore();
  rearm();
  const n = results.length;
  els.count.textContent = n === all.length ? `${n} episodios` : `${n} de ${all.length} episodios`;
  els.empty.hidden = n > 0;
  renderChips();
  writeURL();
}

function chip(text, count, pressed, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "chip";
  b.setAttribute("aria-pressed", pressed);
  b.innerHTML = `${esc(text)}${count != null ? `<small>${count}</small>` : ""}`;
  b.addEventListener("click", onClick);
  return b;
}

function renderChips() {
  const frag = document.createDocumentFragment();
  const kinds = {};
  all.forEach((e) => (kinds[e.kind] = (kinds[e.kind] || 0) + 1));
  frag.append(chip("Todos", null, !state.kind, () => { state.kind = ""; apply(); }));
  Object.keys(KINDS).filter((k) => kinds[k]).forEach((k) =>
    frag.append(chip(KINDS[k], kinds[k], state.kind === k, () => { state.kind = state.kind === k ? "" : k; apply(); })));

  const sep = () => Object.assign(document.createElement("span"), { className: "chip-sep" });
  frag.append(sep());
  frag.append(chip("▶ Con vídeo", all.filter((e) => e.yt).length, state.video, () => { state.video = !state.video; apply(); }));
  const books = all.filter((e) => e.book).length;
  if (books) frag.append(chip("📖 Con libro", books, state.book, () => { state.book = !state.book; apply(); }));

  const tags = {};
  all.forEach((e) => (e.tags || []).forEach((t) => (tags[t] = (tags[t] || 0) + 1)));
  const tagList = Object.entries(tags).sort((a, b) => b[1] - a[1]);
  if (tagList.length) {
    frag.append(sep());
    tagList.forEach(([t, c]) =>
      frag.append(chip(t, c, state.tag === t, () => { state.tag = state.tag === t ? "" : t; apply(); })));
  }
  els.chips.replaceChildren(frag);
}

// --- Rejilla -----------------------------------------------------------------

function thumbHTML(e) {
  const badge = label(e);
  const badgeCls = e.kind === "episodio" ? "badge" : "badge alt";
  const inner = e.yt
    ? `<img src="https://i.ytimg.com/vi/${e.yt}/mqdefault.jpg" alt="" loading="lazy" decoding="async" width="320" height="180">`
    : `<span>${e.n != null ? "#" + e.n : "LQTD"}</span>`;
  return `<div class="thumb${e.yt ? "" : " ph"}">${inner}` +
    (badge ? `<span class="${badgeCls}">${esc(badge)}</span>` : "") +
    (e.dur ? `<span class="dur">${shortDur(e.dur)}</span>` : "") + `</div>`;
}

function cardHTML(e) {
  const tags = (e.tags || []).slice(0, 3).map((t) => `<span class="tag">${esc(t)}</span>`).join("");
  return `<button type="button" class="card" data-key="${esc(key(e))}">${thumbHTML(e)}
    <div class="card-body">
      <h3>${esc(e.title)}</h3>
      ${tags ? `<div class="mini-tags">${tags}</div>` : ""}
      ${e.book ? `<span class="has-book">📖 ${esc(e.book.title)}</span>` : ""}
      <p class="meta">${fmtDate(e.date)}</p>
    </div></button>`;
}

function renderMore() {
  const slice = results.slice(shown, shown + PAGE);
  if (!slice.length) return;
  els.grid.insertAdjacentHTML("beforeend", slice.map((e) => `<li>${cardHTML(e)}</li>`).join(""));
  shown += slice.length;
}

// --- Ficha -------------------------------------------------------------------

const byKey = new Map();

function openDetail(e, push = true) {
  const media = $("d-media");
  if (e.yt) {
    media.className = "media";
    media.innerHTML = `<img src="https://i.ytimg.com/vi/${e.yt}/hqdefault.jpg" alt="">
      <button type="button" class="play" aria-label="Reproducir en YouTube aquí"><span><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></span></button>`;
    media.querySelector(".play").addEventListener("click", () => {
      media.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${e.yt}?autoplay=1" title="${esc(e.title)}"
        allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>`;
    });
  } else {
    media.className = "media ph";
    media.innerHTML = "";
  }
  $("d-meta").textContent = [label(e), fmtDate(e.date), fmtDur(e.dur)].filter(Boolean).join(" · ");
  $("d-title").textContent = e.title;
  $("d-tags").innerHTML = (e.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("");
  $("d-links").innerHTML = PLATFORMS.filter(([k]) => e[k]).map(([k, name, color, url], i) =>
    `<a href="${esc(url(e[k]))}" target="_blank" rel="noopener" class="${i === 0 ? "primary" : ""}">
      <span class="dot" style="background:${color}"></span>${name}</a>`).join("");

  const book = $("d-book");
  if (e.book) {
    const b = e.book;
    book.hidden = false;
    book.innerHTML = (b.cover ? `<img src="${esc(b.cover)}" alt="" loading="lazy">` : "") +
      `<div><p class="label">Libro del invitado</p><h3>${esc(b.title)}</h3>` +
      (b.author ? `<p>${esc(b.author)}</p>` : "") +
      (b.url ? `<a href="${esc(b.url)}" target="_blank" rel="noopener sponsored">Ver el libro →</a>` : "") + `</div>`;
  } else {
    book.hidden = true;
    book.innerHTML = "";
  }
  $("d-desc").innerHTML = linkify(e.desc || "");
  if (push) history.replaceState(null, "", location.pathname + location.search + "#" + encodeURIComponent(key(e)));
  if (!els.dialog.open) els.dialog.showModal();
  els.dialog.scrollTop = 0;
}

function closeDetail() {
  $("d-media").innerHTML = ""; // para el vídeo si estaba sonando
  history.replaceState(null, "", location.pathname + location.search);
}

function openFromHash() {
  const k = decodeURIComponent(location.hash.slice(1));
  const e = k && byKey.get(k);
  if (e) openDetail(e, false);
}

// --- Arranque ----------------------------------------------------------------

function bind() {
  let t;
  els.q.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => { state.q = els.q.value; apply(); }, 120);
  });
  els.year.addEventListener("change", () => { state.year = els.year.value; apply(); });
  els.sort.addEventListener("change", () => { state.sort = els.sort.value; apply(); });
  $("reset").addEventListener("click", () => {
    Object.assign(state, { q: "", kind: "", tag: "", year: "", video: false, book: false });
    els.q.value = ""; els.year.value = "";
    apply();
  });
  els.grid.addEventListener("click", (ev) => {
    const card = ev.target.closest(".card");
    if (card) openDetail(byKey.get(card.dataset.key));
  });
  els.dialog.addEventListener("close", closeDetail);
  els.dialog.addEventListener("click", (ev) => { if (ev.target === els.dialog) els.dialog.close(); });
  window.addEventListener("hashchange", openFromHash);
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "/" && document.activeElement !== els.q && !els.dialog.open) {
      ev.preventDefault();
      els.q.focus();
    }
  });
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && shown < results.length) {
      renderMore();
      rearm();
    }
  }, { rootMargin: "800px" });
  observer.observe(els.sentinel);
}

// Volver a observar fuerza un aviso nuevo si el centinela sigue a la vista
// (pantallas altas o tras filtrar).
let observer;
function rearm() {
  if (!observer) return;
  observer.unobserve(els.sentinel);
  observer.observe(els.sentinel);
}

async function init() {
  readURL();
  bind();
  let data;
  try {
    const res = await fetch("episodes.json");
    data = await res.json();
  } catch (err) {
    els.count.textContent = "No se pudieron cargar los episodios. Recarga la página.";
    return;
  }
  all = data.episodes;
  all.forEach((e) => {
    e._hay = norm([label(e), e.title, e.guest, e.desc, (e.tags || []).join(" "), e.book?.title, e.book?.author].join(" "));
    byKey.set(key(e), e);
  });

  const years = [...new Set(all.map((e) => e.date.slice(0, 4)))].sort().reverse();
  els.year.insertAdjacentHTML("beforeend", years.map((y) => `<option>${y}</option>`).join(""));
  els.q.value = state.q;
  els.year.value = state.year;
  els.sort.value = state.sort;

  const eps = all.filter((e) => e.kind === "episodio").length;
  els.lede.textContent = `${eps} conversaciones de Álex Fidalgo, con buscador, filtros y enlaces para escucharlas o verlas.`;
  if (data.updated) els.updated.textContent = `Datos actualizados el ${fmtDate(data.updated.slice(0, 10))}.`;

  apply();
  openFromHash();
}

init();
