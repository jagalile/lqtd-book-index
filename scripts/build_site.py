#!/usr/bin/env python3
"""Construye la web estática en _site/ a partir de site/ y data/.

Copia los ficheros de site/ y genera _site/books.json: los libros de
data/books.json con los datos de sus episodios ya unidos, en el formato
compacto que usa la web. Solo usa la librería estándar.

    python3 scripts/build_site.py && python3 -m http.server -d _site
"""

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "site"
OUT = ROOT / "_site"


def clean_title(title):
    """Quita el número y la coletilla del podcast: ya se muestran aparte."""
    t = re.sub(r"^#\d+\s*(\([A-Z]\))?\s*:\s*", "", title)
    t = re.sub(r"\s*[-|]\s*#\d+\s*(\([A-Z]\))?\s*$", "", t)
    t = re.sub(r"\s*\|\s*lo que t[uú] digas.*$", "", t, flags=re.I)
    return t.strip(" -|")


def compact_episode(ep):
    out = {
        "n": ep.get("number") if ep.get("kind") == "episodio" else None,
        "title": clean_title(ep["title"]),
        "date": (ep.get("published") or "")[:10],
        "yt": ep.get("youtube_id"),
        "sp": ep.get("spotify_url"),
        "iv": ep.get("ivoox_url"),
    }
    return {k: v for k, v in out.items() if v not in (None, "")}


def compact_book(book, episodes):
    eps = sorted((compact_episode(episodes[e]) for e in book["episodes"] if e in episodes),
                 key=lambda e: e["date"], reverse=True)
    out = {
        "id": book["id"],
        "t": book["title"],
        "a": book.get("author"),
        "th": book.get("themes") or [],
        "y": book.get("year"),
        "pub": book.get("publisher"),
        "isbn": book.get("isbn"),
        "cover": book.get("cover"),
        "buy": book.get("buy_url"),
        # Solo se marca la excepción: por defecto es un libro del invitado.
        "m": 1 if book.get("relation") == "mencionado" else None,
        "date": eps[0]["date"] if eps else "",
        "eps": eps,
    }
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def main():
    books = json.loads((ROOT / "data" / "books.json").read_text(encoding="utf-8"))
    episodes = {e["id"]: e for e in json.loads((ROOT / "data" / "episodes.json").read_text(encoding="utf-8"))["episodes"]}
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SRC, OUT)
    payload = {
        "updated": books.get("updated_at"),
        "themes": books["themes"],
        "books": [compact_book(b, episodes) for b in books["books"]],
    }
    (OUT / "books.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"_site/ generado con {len(payload['books'])} libros")


if __name__ == "__main__":
    main()
