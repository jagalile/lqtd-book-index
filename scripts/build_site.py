#!/usr/bin/env python3
"""Construye la web estática en _site/ a partir de site/ y data/episodes.json.

Copia los ficheros de site/ y genera _site/episodes.json, una versión compacta
de los datos con solo lo que usa la web. Solo usa la librería estándar.

    python3 scripts/build_site.py && python3 -m http.server -d _site
"""

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "site"
DATA = ROOT / "data" / "episodes.json"
OUT = ROOT / "_site"


def clean_title(title):
    """Quita el número y la coletilla del podcast: ya se muestran aparte."""
    t = re.sub(r"^#\d+\s*(\([A-Z]\))?\s*:\s*", "", title)
    t = re.sub(r"\s*[-|]\s*#\d+\s*(\([A-Z]\))?\s*$", "", t)
    t = re.sub(r"\s*\|\s*lo que t[uú] digas.*$", "", t, flags=re.I)
    return t.strip(" -|")


def compact(ep):
    out = {
        "id": ep["id"],
        "n": ep.get("number"),
        "part": ep.get("part"),
        "kind": ep["kind"],
        "title": clean_title(ep["title"]),
        "date": (ep.get("published") or "")[:10],
        "dur": ep.get("duration_seconds"),
        "desc": ep.get("description", ""),
        "yt": ep.get("youtube_id"),
        "sp": ep.get("spotify_url"),
        "iv": ep.get("ivoox_url"),
    }
    # Campos que añadirán pasos posteriores (etiquetado, libros).
    if ep.get("tags"):
        out["tags"] = ep["tags"]
    if ep.get("guest"):
        out["guest"] = ep["guest"]
    if ep.get("book"):
        out["book"] = ep["book"]
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SRC, OUT)
    episodes = [compact(e) for e in data["episodes"] if (e.get("duration_seconds") or 0) >= 600]
    payload = {"updated": data.get("updated_at"), "episodes": episodes}
    (OUT / "episodes.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"_site/ generado con {len(episodes)} episodios")


if __name__ == "__main__":
    main()
