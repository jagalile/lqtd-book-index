#!/usr/bin/env python3
"""Mantiene data/books.json: los libros de los invitados de LO QUE TÚ DIGAS.

data/books.json es un fichero curado a mano (título, autor, temáticas) que este
script completa de forma incremental. Cada libro es, por defecto, un libro del
invitado; los que solo se mencionan en el episodio llevan
`"relation": "mencionado"`.

  1. Detección: revisa solo los episodios de data/episodes.json que aún no
     están en `checked_episodes` y busca libros en su descripción
     («Compra 'X'», «publica el libro 'X'»…). Los libros detectados así se
     marcan con `review: true` y sin temáticas, para revisarlos a mano.
  2. Fichas: a los libros que aún no se han buscado (`lookup` ausente) les
     añade ISBN, año, editorial y portada desde Open Library, o desde Google
     Books si hay una GOOGLE_BOOKS_API_KEY en el entorno (es gratuita).

Las ediciones manuales se respetan: nunca se sobrescribe un campo que ya
tenga valor. Solo usa la librería estándar.
"""

import argparse
import difflib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOOKS = ROOT / "data" / "books.json"
EPISODES = ROOT / "data" / "episodes.json"
USER_AGENT = "lqtd-index/0.1 (web fan no oficial de Lo que tú digas)"

# Temáticas: id -> nombre visible. La web las lee de books.json.
THEMES = {
    "salud": "Salud y nutrición",
    "psicologia": "Psicología y mente",
    "ciencia": "Ciencia",
    "desarrollo": "Desarrollo personal",
    "filosofia": "Filosofía",
    "espiritualidad": "Espiritualidad",
    "misterio": "Misterio",
    "crimen": "Crimen y justicia",
    "sociedad": "Sociedad y actualidad",
    "historia": "Historia",
    "tecnologia": "Tecnología",
    "economia": "Economía y empresa",
    "comunicacion": "Comunicación y escritura",
    "sexualidad": "Sexualidad y relaciones",
    "crianza": "Familia y crianza",
    "deporte": "Deporte",
    "memorias": "Memorias y biografías",
    "novela": "Novela",
    "poesia": "Poesía",
    "humor": "Humor",
    "arte": "Cine, música y arte",
}


def log(msg):
    print(msg, file=sys.stderr)


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def norm(s):
    return slug(s).replace("-", " ")


def book_id(title, author):
    first_author = re.split(r"\s+y\s+|,", author)[0] if author else ""
    return slug(f"{title} {first_author}")[:80]


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            if attempt == 2:
                raise
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(2 * (attempt + 1))


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


# --- 1. Detección en episodios nuevos ----------------------------------------

QUOTE = r"['‘\"«“]([^'’\"»”\n]{3,90}?)['’\"»”]"
BOOK_PATTERNS = [
    re.compile(r"(?:Compra|Reserva)(?:lo)?\s+(?:su (?:último )?libro\s+|el libro\s+)?" + QUOTE, re.I),
    # «Compra Todos gordos aquí: https://amzn.to/…», sin comillas.
    re.compile(r"(?:Compra|Reserva)\s+(?!su\b|el libro\b|aquí\b)([^'‘\"«“:\n]{3,80}?)\s+aquí\s*:", re.I),
    re.compile(r"\b(?:libro|novela|ensayo|poemario|memorias|autobiografía)\b[^.'‘\"«“]{0,60}?" + QUOTE, re.I),
    # Sin «presenta»: casi siempre es un programa de radio o televisión.
    re.compile(r"\bpublica(?:r|do|da)?\b[^.'‘\"«“]{0,40}?" + QUOTE, re.I),
]
STORE = re.compile(r"https?://(?:amzn\.to|www\.amazon\.es|www\.casadellibro\.com|www\.todostuslibros\.com)\S+")


def guest_from_title(title):
    """Invitado según el formato del título: '#12: Nombre - Tema',
    'Tema - Nombre - #554' o 'Tema | Nombre - #546'."""
    m = re.match(r"#\d+\s*(?:\([A-Z]\))?\s*:\s*(.+?)\s+-\s", title)
    if m:
        return m.group(1)
    t = re.sub(r"\s*-\s*#\d+\s*$", "", title)
    parts = re.split(r"\s+[-|]\s+", t)
    return parts[-1].strip() if len(parts) > 1 else ""


def detect(episode):
    desc = episode.get("description") or ""
    titles = []
    for pat in BOOK_PATTERNS:
        for m in pat.finditer(desc):
            t = m.group(1).strip(" .,")
            if t and norm(t) not in {norm(x) for x in titles}:
                titles.append(t)
    store = STORE.search(desc)
    author = guest_from_title(episode["title"])
    return [
        {"title": t, "author": author, "buy_url": store.group(0).rstrip(".,)") if store and i == 0 else None}
        for i, t in enumerate(titles)
    ]


def detect_new(books, episodes):
    checked = set(books["checked_episodes"])
    by_id = {b["id"]: b for b in books["books"]}
    found = 0
    for ep in episodes:
        if ep["id"] in checked:
            continue
        for cand in detect(ep):
            bid = book_id(cand["title"], cand["author"])
            book = by_id.get(bid)
            if book is None:
                book = {"id": bid, "title": cand["title"], "author": cand["author"],
                        "themes": [], "episodes": [], "review": True}
                if cand["buy_url"]:
                    book["buy_url"] = cand["buy_url"]
                books["books"].append(book)
                by_id[bid] = book
                found += 1
                log(f"  + «{cand['title']}» ({cand['author']}) — revisar")
            if ep["id"] not in book["episodes"]:
                book["episodes"].append(ep["id"])
        books["checked_episodes"].append(ep["id"])
    return found


# --- 2. Fichas: Open Library / Google Books ---------------------------------

def short_title(title):
    return re.split(r"[:.¿?¡!]\s", title)[0].strip() or title


def spanish_edition(work_key, title):
    """La edición en español con portada que más se parece al título, o None.

    La portada de la búsqueda es la de la obra, que en los libros traducidos
    suele ser la de la edición original (inglesa, alemana…)."""
    data = fetch_json(f"https://openlibrary.org{work_key}/editions.json?limit=200"
                      "&fields=title,languages,covers,isbn_13,publishers") or {}
    best, best_score = None, 0
    for e in data.get("entries") or []:
        if not e.get("covers") or e["covers"][0] <= 0:
            continue
        if not any(l.get("key") == "/languages/spa" for l in e.get("languages") or []):
            continue
        isbn = next((i for i in e.get("isbn_13") or [] if i.startswith("97884")), None)
        score = difflib.SequenceMatcher(None, norm(title), norm(e.get("title") or "")).ratio() + (0.3 if isbn else 0)
        if score > best_score:
            best_score = score
            best = {"cover": f"https://covers.openlibrary.org/b/id/{e['covers'][0]}-L.jpg",
                    "isbn": isbn or next(iter(e.get("isbn_13") or []), None),
                    "publisher": (e.get("publishers") or [None])[0]}
    return best


def lookup_openlibrary(book):
    author = re.split(r"\s+y\s+|,", book["author"])[0]
    fields = "key,title,author_name,first_publish_year,isbn,cover_i,publisher,number_of_pages_median,language"
    for title in dict.fromkeys([book["title"], short_title(book["title"])]):
        q = urllib.parse.urlencode({"title": title, "author": author, "limit": 5, "fields": fields})
        data = fetch_json(f"https://openlibrary.org/search.json?{q}") or {}
        docs = data.get("docs") or []
        # Preferir una edición con portada e ISBN español (978-84).
        docs.sort(key=lambda d: (not d.get("cover_i"), not any(i.startswith("97884") for i in d.get("isbn", []))))
        if docs:
            d = docs[0]
            isbns = d.get("isbn") or []
            isbn = next((i for i in isbns if i.startswith("97884")), next((i for i in isbns if len(i) == 13), None))
            info = {
                "isbn": isbn,
                "year": d.get("first_publish_year"),
                "publisher": (d.get("publisher") or [None])[0],
                "pages": d.get("number_of_pages_median"),
                "cover": f"https://covers.openlibrary.org/b/id/{d['cover_i']}-L.jpg" if d.get("cover_i") else None,
            }
            # Obra con ediciones en varios idiomas: mejor la portada española.
            if d.get("key") and "spa" in (d.get("language") or []) and len(d["language"]) > 1:
                info.update({k: v for k, v in (spanish_edition(d["key"], book["title"]) or {}).items() if v})
            return info
    return None


def lookup_google(book, key):
    author = re.split(r"\s+y\s+|,", book["author"])[0]
    q = f'intitle:"{short_title(book["title"])}" inauthor:"{author}"'
    url = "https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(
        {"q": q, "maxResults": 5, "printType": "books", "key": key})
    items = (fetch_json(url) or {}).get("items") or []
    items.sort(key=lambda i: (not i["volumeInfo"].get("imageLinks"), i["volumeInfo"].get("language") != "es"))
    if not items:
        return None
    v = items[0]["volumeInfo"]
    ids = {x["type"]: x["identifier"] for x in v.get("industryIdentifiers", [])}
    cover = (v.get("imageLinks") or {}).get("thumbnail")
    return {
        "isbn": ids.get("ISBN_13") or ids.get("ISBN_10"),
        "year": int(v["publishedDate"][:4]) if v.get("publishedDate", "")[:4].isdigit() else None,
        "publisher": v.get("publisher"),
        "pages": v.get("pageCount"),
        "cover": cover.replace("http://", "https://").replace("&edge=curl", "") if cover else None,
    }


def enrich(books, limit, delay):
    key = os.environ.get("GOOGLE_BOOKS_API_KEY")
    pending = [b for b in books["books"] if "lookup" not in b][:limit]
    for b in pending:
        info, source = None, "none"
        try:
            if key:
                info, source = lookup_google(b, key), "google"
            if not info or not info.get("cover"):
                ol = lookup_openlibrary(b)
                if ol and (not info or ol.get("cover")):
                    info, source = {**(info or {}), **{k: v for k, v in ol.items() if v}}, "openlibrary"
        except (urllib.error.URLError, TimeoutError) as e:
            log(f"  ! {b['title']}: {e} (se reintentará)")
            continue
        for k, v in (info or {}).items():
            if v and not b.get(k):
                b[k] = v
        b["lookup"] = source if info else "none"
        log(f"  {'✓' if info else '·'} {b['title']}{' (portada)' if b.get('cover') else ''}")
        time.sleep(delay)
    return len(pending)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-detect", action="store_true", help="no busca libros en episodios nuevos")
    ap.add_argument("--no-enrich", action="store_true", help="no consulta Open Library / Google Books")
    ap.add_argument("--limit", type=int, default=400, help="máximo de libros a buscar por ejecución")
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args()

    books = load(BOOKS, {"themes": THEMES, "checked_episodes": [], "books": []})
    before = json.dumps(books, sort_keys=True)
    books["themes"] = THEMES
    episodes = load(EPISODES, {"episodes": []})["episodes"]

    if not args.no_detect:
        log("Buscando libros en episodios nuevos…")
        log(f"  {detect_new(books, episodes)} libros nuevos detectados")
    if not args.no_enrich:
        log("Completando fichas…")
        log(f"  {enrich(books, args.limit, args.delay)} libros consultados")

    books["books"].sort(key=lambda b: b["id"])
    if json.dumps(books, sort_keys=True) != before:
        books["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save(BOOKS, books)
    with_cover = sum(1 for b in books["books"] if b.get("cover"))
    review = sum(1 for b in books["books"] if b.get("review"))
    log(f"Listo: {len(books['books'])} libros, {with_cover} con portada, {review} pendientes de revisar.")


if __name__ == "__main__":
    main()
