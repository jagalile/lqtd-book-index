# lqtd-index

*La biblioteca de Lo que tú digas*: web fan (no oficial) con los libros de los invitados de *LO QUE TÚ DIGAS* con Álex Fidalgo, clasificados por temática y enlazados a los episodios en los que se habló de ellos.

Web: https://jagalile.github.io/lqtd-index/

## Datos

### Episodios: `data/episodes.json`

```sh
pip install -r requirements.txt   # solo para YouTube (yt-dlp)
python3 scripts/fetch_episodes.py
```

- **Fuente principal:** el RSS de Spotify for Creators (`spreaker.com/show/5819922/episodes/feed`), con descripción completa, fecha, duración, MP3 y enlace de cada episodio.
- **Enlaces de iVoox:** se sacan del listado paginado de iVoox (JSON-LD de cada página).
- **Enlaces de YouTube:** se sacan del canal [@loquetudigas](https://www.youtube.com/@loquetudigas) con yt-dlp. Los títulos de YouTube son distintos de los del podcast, así que se emparejan por número de episodio, por similitud de título, por el nombre del invitado y por duración, respetando el orden cronológico. `--youtube-full` fuerza el listado completo del canal.
- **Incremental:** el fichero hace también de estado. Los episodios que ya están no se tocan; `--refresh` vuelve a escribir los campos de origen sin borrar los añadidos.

Los episodios #181–#258 (salvo #238, #240 y #256) no están publicados en abierto.

### Libros: `data/books.json`

```sh
python3 scripts/books.py
```

Es un fichero **curado a mano**: título, autor, temáticas (`themes`, de la lista que hay en el propio fichero) y episodios de cada libro. El histórico se extrajo leyendo las descripciones de los episodios. Incluye los libros de los invitados y también los que se mencionan en el episodio sin ser suyos; estos llevan `"relation": "mencionado"`. Solo se cuentan títulos explícitos («ha escrito dos libros» no basta). El script lo completa de forma incremental:

1. **Libros de episodios nuevos:** revisa los episodios que no están en `checked_episodes` y busca libros en su descripción («Compra 'X'», «publica el libro 'X'»…). Lo que encuentra se marca con `"review": true` y sin temáticas: hay que revisarlo y asignarle temáticas a mano. Acierta en torno al 70 % de los casos; los títulos sin comillas se le escapan.
2. **Fichas:** a los libros sin `lookup` les añade ISBN, año, editorial y portada desde [Open Library](https://openlibrary.org). Si existe la variable `GOOGLE_BOOKS_API_KEY` (clave gratuita de Google Books), la usa primero, porque tiene más portadas de ediciones españolas. Nunca sobrescribe un campo que ya tenga valor.

Para corregir algo (una portada equivocada, un autor, una temática) se edita `data/books.json` directamente.

## Web

HTML, CSS y JS sin dependencias, en `site/`. `scripts/build_site.py` la copia a `_site/` junto con un `books.json` compacto que ya incluye los datos de los episodios:

```sh
python3 scripts/build_site.py && python3 -m http.server -d _site
```

Portada con estanterías por temática, buscador (libro, autor, temática o episodio), filtros por temática en la URL (`?tema=salud`) y una ficha por libro (`/#id-del-libro`) con dónde comprarlo y los episodios en los que se habló de él. Los libros sin portada en Open Library muestran una portada generada con el color de su temática.

## Actualización y publicación automáticas

`.github/workflows/update-episodes.yml`:

- Los martes y viernes a las 08:00 UTC (los episodios salen esos días a las 07:00, hora de Madrid) y todos los días a las 21:00 UTC ejecuta `fetch_episodes.py` y `books.py`. Si `data/` cambia, hace commit y vuelve a publicar la web.
- Cada push a `main` que toque la web o los datos la vuelve a publicar.
- Para usar Google Books, añade la clave como *secret* `GOOGLE_BOOKS_API_KEY` en *Settings → Secrets and variables → Actions*.
