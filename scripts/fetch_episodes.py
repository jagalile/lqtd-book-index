#!/usr/bin/env python3
"""Genera/actualiza data/episodes.json con los episodios de LO QUE TÚ DIGAS.

Fuentes:
  1. Feed RSS de Spotify for Creators (enlazado desde iVoox como `webFeed`):
     una sola petición con casi todo el archivo, descripciones completas,
     duración, fecha y MP3.
  2. Listado paginado de iVoox: solo para añadir el enlace a iVoox de cada
     episodio. Se recorre desde la página más reciente y se para en cuanto
     una página no aporta nada nuevo.
  3. Canal de YouTube (vía yt-dlp, opcional): enlace al vídeo de cada
     episodio. Los títulos de YouTube no coinciden con los del podcast, así
     que se emparejan por número, por similitud de título y por duración
     (ver match_youtube). La primera vez se lista el canal entero; después,
     solo los vídeos más recientes.

Incremental: episodes.json es también el estado. Un episodio ya presente
(por su `id`) no se toca, de modo que las ediciones manuales y los campos que
añadan pasos posteriores (etiquetas, libros...) se conservan. Con --refresh se
actualizan los campos de origen de los existentes sin borrar los demás.

Solo usa la librería estándar, salvo yt-dlp para YouTube (si no está
instalado, se omite ese paso).
"""

import argparse
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

SPREAKER_FEED_URL = "https://www.spreaker.com/show/5819922/episodes/feed"
IVOOX_PAGE_URL = "https://www.ivoox.com/podcast-lo-que-tu-digas-alex-fidalgo_sq_f1424550_{page}.html"
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/channel/UCcpOe_g8sfr2GSoLZISy6yA/videos"
USER_AGENT ="lqtd-index/0.1 (web fan no oficial; +https://github.com/)"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "episodes.json"

# Campos que pertenecen a las fuentes; --refresh solo sobrescribe estos.
SOURCE_FIELDS = (
    "title", "number", "part", "kind", "published", "duration_seconds",
    "description", "links", "audio_url", "image", "spotify_url",
)


def fetch(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if attempt == retries - 1:
                raise
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
        time.sleep(2 * (attempt + 1))


# --- Normalización -----------------------------------------------------------

def html_to_text(s):
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>\s*", "\n\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\r\n", "\n").replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def extract_links(text):
    return list(dict.fromkeys(m.rstrip(".,;)") for m in re.findall(r"https?://\S+", text)))


def norm_title(s):
    s = unicodedata.normalize("NFKD", html.unescape(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def parse_duration(s):
    """'01:02:03', '62:03', '3723' o ISO 'PT1H2M3S' -> segundos."""
    if not s:
        return None
    s = s.strip()
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s)
    if m:
        h, mi, se = (int(x or 0) for x in m.groups())
        return h * 3600 + mi * 60 + se
    if re.fullmatch(r"[\d:]+", s):
        secs = 0
        for part in s.split(":"):
            secs = secs * 60 + int(part)
        return secs
    return None


def classify(title):
    """Devuelve (kind, number, part) a partir del título."""
    t = title.strip()
    if re.search(r"entre amigos", t, re.I):
        m = re.search(r"#\s?(\d+)", t)
        return "entre-amigos", int(m.group(1)) if m else None, None
    if t.upper().startswith("ÚLTIMA HORA"):
        return "ultima-hora", None, None
    # "#329: Invitado - Tema" (formato antiguo) o "Tema - Invitado - #554" (nuevo)
    m = re.match(r"#(\d+)\s*(?:\(([A-Z])\))?\s*:", t) or re.search(r"#(\d+)\s*(?:\(([A-Z])\))?\s*$", t)
    if m:
        return "episodio", int(m.group(1)), m.group(2)
    if re.search(r"especial", t, re.I):
        return "especial", None, None
    return "otro", None, None


# --- Fuente 1: RSS -----------------------------------------------------------

def parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    episodes = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        kind, number, part = classify(title)
        duration = parse_duration(item.findtext(f"{ITUNES}duration"))
        # Desde 2026 algunos episodios normales salen sin número en el título.
        if kind == "otro" and (duration or 0) >= 30 * 60:
            kind = "episodio"
        description = html_to_text(item.findtext("description") or item.findtext(f"{ITUNES}summary"))
        enclosure = item.find("enclosure")
        image = item.find(f"{ITUNES}image")
        pub = item.findtext("pubDate")
        ep = {
            "id": guid,
            "title": title,
            "number": number,
            "part": part,
            "kind": kind,
            "published": parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat() if pub else None,
            "duration_seconds": duration,
            "description": description,
            "links": extract_links(description),
            "audio_url": enclosure.get("url") if enclosure is not None else None,
            "image": image.get("href") if image is not None else None,
            "spotify_url": (item.findtext("link") or "").strip() or None,
            "ivoox_url": None,
            "youtube_url": None,
        }
        # Los episodios antiguos conservan el guid de iVoox: enlace directo.
        m = re.fullmatch(r"https://www\.ivoox\.com/(\d+)", guid)
        if m:
            ep["ivoox_id"] = m.group(1)
        episodes.append(ep)
    return episodes


# --- Fuente 2: iVoox ---------------------------------------------------------

def parse_ivoox_page(page_html):
    m = re.search(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page_html, re.S)
    if not m:
        return []
    graph = json.loads(m.group(1)).get("@graph", [])
    entries = []
    for node in graph:
        for media in node.get("associatedMedia", []):
            url = media.get("embedUrl")
            idm = re.search(r"_rf_(\d+)_", url or "")
            if not idm:
                continue
            entries.append({
                "ivoox_id": idm.group(1),
                "url": url,
                "title": media.get("name", ""),
                "published": (media.get("datePublished") or "")[:10],
            })
    return entries


def match_ivoox(entry, episodes, by_ivoox_id, by_title, by_number):
    if entry["ivoox_id"] in by_ivoox_id:
        return by_ivoox_id[entry["ivoox_id"]]
    ep = by_title.get(norm_title(entry["title"]))
    if ep:
        return ep
    kind, number, part = classify(entry["title"])
    if kind == "episodio" and number is not None:
        return by_number.get((number, part))
    # Último recurso: mismo día de publicación y un único candidato sin enlace.
    same_day = [e for e in episodes if not e.get("ivoox_url") and (e["published"] or "")[:10] == entry["published"]]
    return same_day[0] if len(same_day) == 1 else None


def enrich_with_ivoox(episodes, max_pages, delay, log):
    by_ivoox_id = {e["ivoox_id"]: e for e in episodes if e.get("ivoox_id")}
    by_title = {norm_title(e["title"]): e for e in episodes}
    by_number = {}
    for e in episodes:
        if e["kind"] == "episodio" and e["number"] is not None:
            by_number[(e["number"], e["part"])] = e
    known_urls = {e["ivoox_url"] for e in episodes if e.get("ivoox_url")}

    unmatched = []
    for page in range(1, max_pages + 1):
        if all(e.get("ivoox_url") for e in episodes):
            break
        page_html = fetch(IVOOX_PAGE_URL.format(page=page))
        entries = parse_ivoox_page(page_html) if page_html else []
        if not entries:
            break
        new_on_page = 0
        for entry in entries:
            if entry["url"] in known_urls:
                continue
            new_on_page += 1
            ep = match_ivoox(entry, episodes, by_ivoox_id, by_title, by_number)
            if ep and not ep.get("ivoox_url"):
                ep["ivoox_url"] = entry["url"]
                ep["ivoox_id"] = entry["ivoox_id"]
                known_urls.add(entry["url"])
            else:
                unmatched.append(entry)
        log(f"  iVoox página {page}: {len(entries)} entradas, {new_on_page} sin enlazar antes")
        # Página entera ya conocida: lo que queda más atrás también lo está.
        if new_on_page == 0:
            break
        time.sleep(delay)
    return unmatched


# --- Fuente 3: YouTube -------------------------------------------------------

# Por debajo de esto son clips o avances, no episodios completos.
YT_MIN_DURATION = 25 * 60
YT_STOPWORDS = set(
    "el la los las de del y a en que lo un una es por con para se no mi tu su al "
    "como sobre digas ultima hora esto este esta".split()
)


def list_youtube_videos(limit, log):
    """Vídeos del canal, del más reciente al más antiguo: [{id, title, duration}]."""
    try:
        import yt_dlp
    except ImportError:
        log("  yt-dlp no está instalado; se omite YouTube (pip install -r requirements.txt)")
        return None
    opts = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        # Sin esto YouTube devuelve los títulos traducidos al inglés.
        "extractor_args": {"youtube": {"lang": ["es"]}},
    }
    if limit:
        opts["playlistend"] = limit
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(YOUTUBE_CHANNEL_URL, download=False)
    except Exception as e:  # YouTube a veces bloquea IPs de centros de datos.
        log(f"  Error listando YouTube, se omite: {e}")
        return None
    return [
        {"id": v["id"], "title": v.get("title") or "", "duration": v.get("duration")}
        for v in info.get("entries") or []
        if v.get("id")
    ]


def title_tokens(s):
    s = re.sub(r"lo que tu digas\s*#?\d*|#\d+(\s*\([ab]\))?", "", norm_title(s))
    return {w for w in s.split() if len(w) > 2 and w not in YT_STOPWORDS}


def youtube_number(title):
    """Número de episodio en un título de YouTube: '#165' o '| Lo Que Tú Digas 165'."""
    t = norm_title(title)
    if "entre amigos" in t:
        return None
    m = re.search(r"#(\d+)", title) or re.search(r"lo que tu digas (\d+)\b", t)
    return int(m.group(1)) if m else None


def match_youtube(episodes, videos):
    """Empareja episodios y vídeos. Devuelve [(episodio, vídeo)].

    1. Mismo número de episodio (YouTube resubió episodios antiguos fuera de
       orden, así que esto no puede depender del orden).
    2. Títulos casi iguales y duración parecida, también sin importar el orden.
    3. El resto, con un alineamiento que respeta el orden cronológico de ambas
       listas: así una duración idéntica al segundo es fiable aunque el título
       de YouTube no se parezca en nada al del podcast.
    """
    videos = [v for v in videos if (v["duration"] or 0) >= YT_MIN_DURATION]
    pairs, used_e, used_v = [], set(), set()

    def take(e, v):
        pairs.append((e, v))
        used_e.add(id(e))
        used_v.add(v["id"])

    def dur_diff(e, v):
        return abs((e["duration_seconds"] or 0) - v["duration"])

    def similarity(e, v):
        a, b = title_tokens(e["title"]), title_tokens(v["title"])
        return len(a & b) / max(1, min(len(a), len(b)))

    by_number = {}
    for v in videos:
        n = youtube_number(v["title"])
        if n is not None:
            by_number.setdefault(n, []).append(v)
    for e in episodes:
        if e["kind"] != "episodio" or e["number"] is None or e["part"]:
            continue
        cands = [v for v in by_number.get(e["number"], [])
                 if v["id"] not in used_v and dur_diff(e, v) < 1800]
        if len(cands) == 1:
            take(e, cands[0])

    strong = sorted(
        ((similarity(e, v), e, v) for e in episodes if id(e) not in used_e
         for v in videos if v["id"] not in used_v and dur_diff(e, v) <= 300),
        key=lambda x: -x[0],
    )
    for sim, e, v in strong:
        if sim < 0.75:
            break
        if id(e) not in used_e and v["id"] not in used_v:
            take(e, v)

    # Formato antiguo "#123: Invitado - Tema": el nombre del invitado completo
    # en un único vídeo basta, aunque la resubida tenga otro título y se haya
    # reeditado (la duración cambia unos minutos).
    for e in episodes:
        m = re.match(r"#\d+\s*:\s*(.+?)\s*-\s", e["title"])
        if id(e) in used_e or not m:
            continue
        guest = title_tokens(m.group(1)) - {"alex", "fidalgo"}  # el presentador no identifica
        if not guest:
            continue
        cands = [v for v in videos if v["id"] not in used_v and dur_diff(e, v) <= 900
                 and guest <= title_tokens(v["title"])]
        if len(cands) == 1:
            take(e, cands[0])

    def entre_amigos(title):
        """(es «Entre Amigos», número). En YouTube hay además una serie
        posterior «Episodio N | LQTD Entre Amigos» que no está en el feed."""
        if "entre amigos" not in norm_title(title):
            return False, None
        m = re.search(r"#\s?(\d+)", title)
        return True, int(m.group(1)) if m else None

    def score(e, v):
        ea_e, ea_v = entre_amigos(e["title"]), entre_amigos(v["title"])
        if (ea_e[0] or ea_v[0]) and (ea_e != ea_v or ea_e[1] is None):
            return None
        ne = e["number"] if e["kind"] == "episodio" else None
        nv = youtube_number(v["title"])
        if ne is not None and nv is not None and ne != nv:
            return None
        dd = dur_diff(e, v)
        if dd > 900:
            return None
        s = 2 * similarity(e, v)
        s += 1.5 if dd <= 5 else max(0.0, 1 - dd / 300)
        return s if s >= 1.0 else None

    eps = sorted((e for e in episodes if id(e) not in used_e), key=lambda e: e["published"] or "")
    vids = [v for v in reversed(videos) if v["id"] not in used_v]  # del más antiguo al más nuevo
    n, m = len(eps), len(vids)
    S = [[score(e, v) for v in vids] for e in eps]
    D = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = max(D[i - 1][j], D[i][j - 1])
            s = S[i - 1][j - 1]
            if s is not None:
                best = max(best, D[i - 1][j - 1] + s)
            D[i][j] = best
    i, j = n, m
    while i and j:
        s = S[i - 1][j - 1]
        if s is not None and D[i][j] == D[i - 1][j - 1] + s:
            take(eps[i - 1], vids[j - 1])
            i, j = i - 1, j - 1
        elif D[i][j] == D[i - 1][j]:
            i -= 1
        else:
            j -= 1
    return pairs


def enrich_with_youtube(episodes, recent_limit, full, log):
    assigned = {e["youtube_id"] for e in episodes if e.get("youtube_id")}
    pending = [e for e in episodes if not e.get("youtube_id")]
    if not pending:
        return 0
    # Sin ningún enlace aún (primera ejecución) hay que listar el canal entero.
    limit = None if full or not assigned else recent_limit
    if limit:
        # Con solo los vídeos recientes, un episodio antiguo sin vídeo podría
        # acabar emparejado con uno nuevo de duración parecida.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        pending = [e for e in pending if (e["published"] or "") >= cutoff]
        if not pending:
            return 0
    videos = list_youtube_videos(limit, log)
    if videos is None:
        return 0
    log(f"  {len(videos)} vídeos listados")
    videos = [v for v in videos if v["id"] not in assigned]
    pairs = match_youtube(pending, videos)
    for e, v in pairs:
        e["youtube_id"] = v["id"]
        e["youtube_url"] = f"https://www.youtube.com/watch?v={v['id']}"
    return len(pairs)


# --- Principal ---------------------------------------------------------------

def load(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"episodes": []}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--refresh", action="store_true",
                    help="actualiza los campos de origen de los episodios ya existentes")
    ap.add_argument("--no-ivoox", action="store_true", help="no consulta iVoox")
    ap.add_argument("--max-ivoox-pages", type=int, default=60)
    ap.add_argument("--delay", type=float, default=1.0, help="pausa entre páginas de iVoox (s)")
    ap.add_argument("--no-youtube", action="store_true", help="no consulta YouTube")
    ap.add_argument("--youtube-full", action="store_true",
                    help="lista el canal de YouTube entero en vez de solo los vídeos recientes")
    ap.add_argument("--youtube-recent", type=int, default=50,
                    help="vídeos recientes a revisar en modo incremental")
    args = ap.parse_args()
    log = lambda msg: print(msg, file=sys.stderr)

    data = load(args.output)
    before = json.dumps(data["episodes"], sort_keys=True)
    existing = {e["id"]: e for e in data["episodes"]}

    log("Descargando RSS…")
    feed = parse_feed(fetch(SPREAKER_FEED_URL))
    log(f"  {len(feed)} episodios en el feed")

    added = refreshed = 0
    for ep in feed:
        if not ep["id"]:
            continue
        current = existing.get(ep["id"])
        if current is None:
            ep["first_seen"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            existing[ep["id"]] = ep
            added += 1
        elif args.refresh:
            current.update({k: ep[k] for k in SOURCE_FIELDS})
            refreshed += 1

    episodes = sorted(existing.values(), key=lambda e: e["published"] or "", reverse=True)

    unmatched = []
    if not args.no_ivoox:
        log("Buscando enlaces de iVoox…")
        unmatched = enrich_with_ivoox(episodes, args.max_ivoox_pages, args.delay, log)

    if not args.no_youtube:
        log("Buscando vídeos de YouTube…")
        yt_new = enrich_with_youtube(episodes, args.youtube_recent, args.youtube_full, log)
        log(f"  {yt_new} episodios enlazados ahora con YouTube")

    # Solo se escribe si algo cambió, para no generar commits vacíos.
    if json.dumps(episodes, sort_keys=True) != before:
        data["episodes"] = episodes
        data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save(args.output, data)

    with_ivoox = sum(1 for e in episodes if e.get("ivoox_url"))
    with_yt = sum(1 for e in episodes if e.get("youtube_url"))
    log(f"Listo: {len(episodes)} episodios ({added} nuevos"
        + (f", {refreshed} refrescados" if args.refresh else "") + f"), "
        f"{with_ivoox} con enlace a iVoox, {with_yt} con enlace a YouTube.")
    if unmatched:
        log(f"Aviso: {len(unmatched)} entradas de iVoox sin episodio correspondiente:")
        for u in unmatched[:20]:
            log(f"  - {u['title']} ({u['published']})")


if __name__ == "__main__":
    main()
