# lqtd-index

Índice fan (no oficial) de los episodios de *LO QUE TÚ DIGAS* con Álex Fidalgo.

## Datos de episodios

```sh
pip install -r requirements.txt   # solo para YouTube (yt-dlp)
python3 scripts/fetch_episodes.py
```

Genera `data/episodes.json`. Salvo yt-dlp, solo usa la librería estándar de Python; si yt-dlp no está instalado, se omite YouTube.

- **Fuente principal:** el RSS de Spotify for Creators (`spreaker.com/show/5819922/episodes/feed`), con descripción completa, fecha, duración, MP3 y enlace de cada episodio.
- **Enlaces de iVoox:** se sacan del listado paginado de iVoox (JSON-LD de cada página).
- **Enlaces de YouTube:** se sacan del canal [@loquetudigas](https://www.youtube.com/@loquetudigas) con yt-dlp. Los títulos de YouTube son distintos de los del podcast, así que se emparejan por número de episodio, por similitud de título, por el nombre del invitado y por duración, respetando el orden cronológico. La primera vez se lista el canal entero; después, solo los últimos 50 vídeos y los episodios de los últimos 120 días. `--youtube-full` fuerza el listado completo. Unos 60 episodios antiguos (sobre todo de 2020-2021) no tienen vídeo o tienen uno reeditado que no se puede emparejar con seguridad.
- **Incremental:** `episodes.json` hace también de estado. Los episodios que ya están (por `id`) no se tocan, así que se conservan las ediciones manuales y los campos que añadan pasos posteriores. En iVoox el recorrido se para en la primera página que no trae nada nuevo.
- `--refresh` vuelve a escribir los campos de origen de los episodios existentes, sin borrar los añadidos. `--no-ivoox` se salta iVoox.

## Web

HTML, CSS y JS sin dependencias ni framework, en `site/`. `scripts/build_site.py` la copia a `_site/` junto con un `episodes.json` compacto (unos 180 KB comprimido):

```sh
python3 scripts/build_site.py && python3 -m http.server -d _site
```

Tiene buscador (sin tildes, también por nº de episodio: `#554`), filtros por tipo, año, «con vídeo» y orden, y una ficha de cada episodio con el vídeo incrustado y los enlaces a YouTube, Spotify e iVoox. Los filtros quedan en la URL y cada ficha tiene enlace propio (`/#554`). Cuando los episodios tengan `tags` y `book` (`{title, author, cover, url}`), aparecerán solos los filtros por etiqueta, «con libro» y la ficha del libro.

## Actualización y publicación automáticas

`.github/workflows/update-episodes.yml`:

- Los martes y viernes a las 08:00 UTC (los episodios salen esos días a las 07:00, hora de Madrid) y todos los días a las 21:00 UTC (para los episodios fuera de calendario) ejecuta `fetch_episodes.py`. Si `data/` cambia, hace commit y vuelve a publicar la web; si no, no hace nada más.
- Cada push a `main` que toque la web o los datos la vuelve a publicar.
- También se puede lanzar a mano desde la pestaña *Actions*.

Para activar GitHub Pages: *Settings → Pages → Source: GitHub Actions*.

Los episodios #181–#258 (salvo #238, #240 y #256) no están publicados en abierto ni en el RSS ni en iVoox.
