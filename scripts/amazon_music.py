#!/usr/bin/env python3
"""Añade a data/episodes.json el enlace de cada episodio en Amazon Music.

Amazon Music no tiene RSS ni API pública y su web es una aplicación
JavaScript, así que se abre la página del programa con un navegador sin
interfaz (Playwright + Chromium) y se recogen los enlaces de los episodios.
Su robots.txt permite las páginas de podcasts. Amazon publica los mismos
títulos que el RSS, así que se emparejan por título.

Incremental: solo busca los episodios sin `amazon_url` y deja de bajar por
la lista en cuanto los ha encontrado (los nuevos están arriba).

    pip install playwright && python -m playwright install chromium
    python3 scripts/amazon_music.py           # episodios sin enlace
    python3 scripts/amazon_music.py --check   # sale con 0 si hay trabajo
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "data" / "episodes.json"
SHOW_URL = "https://music.amazon.es/podcasts/8d40639a-0141-4f6f-8461-5a237bfdbc48/lo-que-t-digas-con-alex-fidalgo"
LINKS_JS = """[...document.querySelectorAll('a[href*="/episodes/"]')]
  .map(a => [a.href, (a.getAttribute('aria-label') || a.textContent || '').trim()])"""


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def key(title):
    t = unicodedata.normalize("NFKD", title.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", t)


def scrape(wanted, max_stall=6):
    """{título normalizado: enlace} bajando por la lista hasta encontrar `wanted`."""
    from playwright.sync_api import sync_playwright

    found = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(locale="es-ES", viewport={"width": 1280, "height": 1000})
        page.goto(SHOW_URL, wait_until="networkidle", timeout=90000)
        stall = 0
        while stall < max_stall and not wanted <= found.keys():
            before = len(found)
            for href, title in page.evaluate(LINKS_JS):
                found.setdefault(key(title), href.split("?")[0])
            page.mouse.wheel(0, 8000)  # carga la siguiente página de 20 episodios
            page.wait_for_timeout(1800)
            stall = stall + 1 if len(found) == before else 0
        browser.close()
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="solo dice si hay episodios sin enlace")
    args = ap.parse_args()

    data = json.loads(EPISODES.read_text(encoding="utf-8"))
    missing = [e for e in data["episodes"] if not e.get("amazon_url")]
    if args.check:
        log(f"{len(missing)} episodios sin enlace de Amazon Music")
        sys.exit(0 if missing else 1)
    if not missing:
        log("Todos los episodios tienen enlace de Amazon Music.")
        return

    links = scrape({key(e["title"]) for e in missing})
    added = 0
    for e in missing:
        url = links.get(key(e["title"]))
        if url:
            e["amazon_url"] = url
            added += 1
    log(f"{len(links)} episodios en Amazon Music; {added} de {len(missing)} enlaces nuevos.")
    if added:
        tmp = EPISODES.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(EPISODES)


if __name__ == "__main__":
    main()
