"""Busqueda de videos virales en YouTube para la etapa de investigacion.

Dos caminos,decidedos por la presencia de ``YOUTUBE_API_KEY``:

1. **Data API oficial** (preferido cuando hay clave): ``GET /youtube/v3/search`` con
   ``order=viewCount`` y luego ``GET /youtube/v3/videos`` para las metricas. Es el camino
   del notebook ``01_research_scrapegraph.ipynb`` (celda ``search_youtube_videos``).
2. **Extractor sin clave** (por defecto, porque ``YOUTUBE_API_KEY`` esta vacia en el
   ``.env`` local): descarga la pagina de resultados de YouTube con un User-Agent de
   navegador y extrae titulo, canal, vistas y URL con expresiones regulares sobre el
   HTML de resultados (claves ``ytInitialData``, ``"viewCount":{"simpleText":"..."}``,
   ``"shortViewCount"``). Es tolerante: si el formato de YouTube cambia devuelve lo que
   encuentre y lo reporta como ``partial`` en vez de reventar.

Ninguno de los dos caminos lanza excepcion hacia el pipeline: si la red falla o YouTube
bloquea la peticion se devuelve ``status="error"`` con el mensaje y el worker continua.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
YOUTUBE_RESULTS_URL = "https://www.youtube.com/results"
# Filtro de popularidad de YouTube: "ordenar por numero de vistas".
#
# El valor va SIN codificar porque ``requests`` ya codifica los parametros de la
# query. Con la constante anterior (``"CAM%3D"``) se enviava ``sp=CAM%253D``:
# el "%" se escapaba dos veces, YouTube ignoraba el filtro y devolvia los
# resultados ordenados por relevancia en vez de por numero de vistas.
POPULARITY_FILTER = "CAM="
DEFAULT_LIMIT = 6
REQUEST_TIMEOUT = (10, 30)
MAX_TEXT_CHARS = 1200
PLATFORM_DOMAINS: dict[str, tuple[str, ...]] = {
    "reddit": ("reddit.com",),
    "x": ("x.com", "twitter.com"),
    "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",),
    "facebook": ("facebook.com",),
    "youtube": ("youtube.com",),
}

_VIEW_COUNT_PATTERNS = (
    r'"viewCountText":\{"simpleText":"((?:[^"\\]|\\.)*)"',
    r'"viewCount":\{"simpleText":"((?:[^"\\]|\\.)*)"',
    r'"shortViewCount":\{"simpleText":"((?:[^"\\]|\\.)*)"',
    r'"viewCountText":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"',
)
_TITLE_PATTERNS = (
    r'"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"',
    r'"title":\{"simpleText":"((?:[^"\\]|\\.)*)"',
    r'"headline":\{"simpleText":"((?:[^"\\]|\\.)*)"',
)
_CHANNEL_PATTERNS = (
    r'"ownerText":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"',
    r'"longBylineText":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"',
    r'"shortBylineText":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"',
    r'"channelName":"((?:[^"\\]|\\.)*)"',
)
_PUBLISHED_PATTERN = r'"publishedTimeText":\{"simpleText":"((?:[^"\\]|\\.)*)"'
_VIDEO_ID_PATTERN = re.compile(r'"videoId":"([A-Za-z0-9_-]{11})"')
_WINDOW_CHARS = 9000

# Numero de vistas: separadores de miles o decimal, con sufijo de magnitud opcional.
_VIEW_COUNT_RE = re.compile(
    r"(?P<number>\d+(?:[.,\s]\d+)*)\s*"
    r"(?P<suffix>millones|millón|millones|million|millions|billones|billón|"
    r"billion|billions|thousands|thousand|mil|M|B|K|k)?"
    r"(?![A-Za-zÁÉÍÓÚÜÑáéíóúüñ])"
)
_VIEW_COUNT_SUFFIXES = {
    "millones": 1_000_000,
    "millón": 1_000_000,
    "million": 1_000_000,
    "millions": 1_000_000,
    "billones": 1_000_000_000,
    "billón": 1_000_000_000,
    "billion": 1_000_000_000,
    "billions": 1_000_000_000,
    "thousands": 1_000,
    "thousand": 1_000,
    "mil": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
    "K": 1_000,
    "k": 1_000,
}

# Fechas relativas de YouTube en espanol. Las abreviaturas se han medido contra
# la fecha real de publicacion (uploadDate de la pagina de watch): "hace 10 a"
# son 10 anos, "hace 3 m" son 3 meses y "hace 2 sem." son 2 semanas.
# El valor es la duracion aproximada de la unidad en dias.
_RELATIVE_TIME_UNITS: tuple[tuple[str, float], ...] = (
    (r"segundos?", 1 / 86400),
    (r"minutos?", 1 / 1440),
    (r"min", 1 / 1440),
    (r"horas?", 1 / 24),
    (r"h", 1 / 24),
    (r"días?", 1.0),
    (r"dias?", 1.0),
    (r"d", 1.0),
    (r"semanas?", 7.0),
    (r"sem\.", 7.0),
    (r"meses?", 30.44),
    (r"años?", 365.25),
    (r"anos?", 365.25),
    (r"a", 365.25),
    (r"m", 30.44),
)


def _matches_platform(url: str, platform: str) -> bool:
    """Indica si una URL pertenece a los dominios publicos de la plataforma."""
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    allowed = {
        candidate
        for domain in PLATFORM_DOMAINS.get(platform, ())
        for candidate in (domain, f"www.{domain}", f"m.{domain}")
    }
    return host in allowed


def _unescape(value: str) -> str:
    """Convierte una cadena escapada de JSON en texto plano."""
    try:
        return json.loads(f'"{value}"')
    except (ValueError, TypeError):
        return value


def _first_match(patterns: Iterable[str], window: str) -> str | None:
    """Devuelve el primer grupo capturado de los patrones que casen con la ventana."""
    for pattern in patterns:
        match = re.search(pattern, window)
        if match:
            text = _unescape(match.group(1)).strip()
            if text:
                return text
    return None


def parse_view_count(text: str | None) -> int | None:
    """Convierte un texto de vistas ("1.234.567 de vistas", "8.6 M") en un entero.

    YouTube escribe las vistas de dos formas según el layout:

    - **Conteo exacto**: ``"8,259,754 vistas"`` o ``"8.259.754 vistas"``, donde los
      separadores son de miles.
    - **Conteo abreviado**: ``"8.6 M"``, ``"8,6 M"``, ``"2 M"``, ``"12K views"``,
      ``"701 mil vistas"``, ``"4,4 millones de vistas"``. Aqui los separadores son
      decimales y el sufijo indica la magnitud.

    Antes este parser multiplicaba ``"8.6 M"`` por un millon (``86.000.000`` en vez
    de ``8.600.000``) porque se comia el punto como separador de miles.
    """
    if not text:
        return None
    normalized = text.replace("\u00a0", " ").replace("\u202f", " ").strip()
    match = _VIEW_COUNT_RE.search(normalized)
    if not match:
        return None

    number_text = match.group("number")
    suffix = match.group("suffix")
    if suffix is None:
        # Conteo exacto: todos los separadores son de miles.
        digits = re.sub(r"[^\d]", "", number_text)
        if not digits:
            return None
        return int(digits)

    multiplier = _VIEW_COUNT_SUFFIXES[suffix]
    value = _parse_decimal_amount(number_text)
    if value is None:
        return None
    return int(round(value * multiplier))


def _parse_decimal_amount(number_text: str) -> float | None:
    """Interpreta ``"8.6"``, ``"8,6"``, ``"12"`` o ``"1,234"`` como cantidad decimal.

    Con sufijo de magnitud, un unico separador con tres digitos detrás es de miles
    (``1,234`` -> 1234) y en cualquier otro caso es decimal (``8,6`` -> 8.6).
    """
    cleaned = number_text.replace(" ", "")
    parts = re.split(r"[.,]", cleaned)
    if not parts or not parts[0].isdigit():
        return None
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) > 2:
        # Varios grupos: todos son separadores de miles.
        digits = re.sub(r"[^\d]", "", cleaned)
        return float(digits) if digits else None
    whole, fraction = parts
    if len(fraction) == 3:
        digits = re.sub(r"[^\d]", "", cleaned)
        return float(digits) if digits else None
    if not fraction.isdigit():
        return None
    return float(f"{whole}.{fraction}")



def _parse_relative_time(text: str | None) -> str | None:
    """Convierte "hace 3 meses" / "hace 10 a" en una marca ISO aproximada.

    YouTube escribe las fechas relativas en espanol de forma abreviada. Las
    abreviaturas se han medido contra la fecha real de publicacion de cada video
    (``uploadDate`` de la pagina de watch): ``"hace 10 a"`` son 10 anos,
    ``"hace 3 m"`` son 3 meses y ``"hace 2 sem."`` son 2 semanas.

    Devuelve ``None`` si el texto no contiene ninguna cantidad reconocible.
    """
    if not text:
        return None
    lowered = text.lower()
    for pattern, days_per_unit in _RELATIVE_TIME_UNITS:
        match = re.search(
            rf"(\d+)\s*{pattern}(?![A-Za-zÁÉÍÓÚÜÑáéíóúüñ])",
            lowered,
        )
        if not match:
            continue
        amount = int(match.group(1))
        delta = timedelta(days=amount * days_per_unit)
        return (datetime.now(timezone.utc) - delta).isoformat().replace("+00:00", "Z")
    return None



def _source(
    title: str,
    video_id: str,
    channel: str | None,
    views: int | None,
    published_at: str | None,
) -> dict[str, Any]:
    """Construye la entrada de fuente con la forma que espera el contrato de salida."""
    return {
        "platform": "youtube",
        "source_type": "video_metrics",
        "title": title,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "view_count": views,
        "views_per_hour": None,
        "published_at": published_at,
        "channel": channel or "",
    }


def scrape_youtube_results(
    topic: str, limit: int = DEFAULT_LIMIT
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extrae videos de la pagina de resultados de YouTube sin usar ninguna API key.

    Devuelve ``(sources, status)``. Nunca lanza: los fallos de red o de formato se
    traducen en ``status="error"`` o ``status="partial"``.
    """
    params = {"search_query": topic, "sp": POPULARITY_FILTER}
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        response = requests.get(
            YOUTUBE_RESULTS_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT
        )
        response.raise_for_status()
    except requests.RequestException as error:
        message = f"No se pudo consultar YouTube: {error.__class__.__name__}: {error}"[:240]
        logger.warning(message)
        return [], {
            "platform": "youtube",
            "status": "error",
            "result_count": 0,
            "message": message,
        }

    html = response.text
    sources = extract_sources_from_html(html)
    if not sources:
        return [], {
            "platform": "youtube",
            "status": "no_results",
            "result_count": 0,
            "message": (
                "YouTube no devolvio resultados legibles para el tema; "
                "puede haber bloqueado la peticion anonima."
            ),
        }

    ordered = sorted(
        sources,
        key=lambda item: item.get("view_count") if item.get("view_count") else -1,
        reverse=True,
    )[: max(1, limit)]
    with_views = [item for item in ordered if item.get("view_count")]
    status = "ok" if len(with_views) == len(ordered) else "partial"
    message = (
        f"{len(ordered)} videos ordenados por vistas."
        if status == "ok"
        else f"{len(with_views)} de {len(ordered)} videos traen el numero de vistas."
    )
    return ordered, {
        "platform": "youtube",
        "status": status,
        "result_count": len(ordered),
        "message": message,
    }


def _extract_sources_from_html(html: str) -> list[dict[str, Any]]:
    """Extrae las fuentes del HTML de resultados con expresiones regulares.

    Es la via heredada: se queda como respaldo para cuando la pagina no trae
    ``ytInitialData`` legible. La via principal es :func:`extract_sources_from_html`.
    """
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in _VIDEO_ID_PATTERN.finditer(html):
        video_id = match.group(1)
        if video_id in seen:
            continue
        window = html[match.end() : match.end() + _WINDOW_CHARS]
        title = _first_match(_TITLE_PATTERNS, window)
        if not title:
            continue
        seen.add(video_id)
        views_text = _first_match(_VIEW_COUNT_PATTERNS, window)
        channel = _first_match(_CHANNEL_PATTERNS, window)
        published_at = _parse_relative_time(_first_match((_PUBLISHED_PATTERN,), window))
        sources.append(
            _source(title, video_id, channel, parse_view_count(views_text), published_at)
        )
    return sources


# ---------------------------------------------------------------------------
# Extraccion estructural desde ``ytInitialData``
# ---------------------------------------------------------------------------
#
# YouTube sirve los resultados de busqueda en dos layouts distintos y los
# reparte de forma aleatoria entre peticiones:
#
# - **videoRenderer**: ``title.runs[0].text`` y ``viewCountText.simpleText``.
# - **lockupViewModel**: ``metadata.lockupMetadataViewModel.title.content`` y las
#   vistas/fecha en ``metadata.contentMetadataViewModel.metadataRows``.
#
# El extractor anterior solo entendia el primer layout, asi que cuando YouTube
# servia el segundo el worker no encontraba ningun titulo y devolvia
# ``no_results`` (probabilidad medida: 1 de cada 25 a 40 peticiones).


def _iter_nodes(node: Any, key: str) -> Iterable[dict[str, Any]]:
    """Recorre el arbol JSON y devuelve todos los nodos con la clave indicada."""
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key and isinstance(value, dict):
                yield value
            yield from _iter_nodes(value, key)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_nodes(item, key)


def _text_of(node: Any) -> str:
    """Devuelve el texto de un nodo de YouTube con cualquiera de sus formas.

    Acepta ``{"runs": [{"text": ...}]}``, ``{"simpleText": ...}`` y
    ``{"content": ...}``.
    """
    if isinstance(node, str):
        return node.strip()
    if not isinstance(node, dict):
        return ""
    if "simpleText" in node and isinstance(node["simpleText"], str):
        return node["simpleText"].strip()
    if "content" in node and isinstance(node["content"], str):
        return node["content"].strip()
    runs = node.get("runs")
    if isinstance(runs, list):
        for run in runs:
            if isinstance(run, dict) and isinstance(run.get("text"), str):
                return run["text"].strip()
    return ""


def _source_from_video_renderer(renderer: dict[str, Any]) -> dict[str, Any] | None:
    """Construye una fuente a partir de un ``videoRenderer``."""
    video_id = renderer.get("videoId")
    title = _text_of(renderer.get("title"))
    if not isinstance(video_id, str) or not video_id or not title:
        return None
    views_text = _text_of(renderer.get("viewCountText")) or _text_of(
        renderer.get("shortViewCountText")
    )
    channel = _text_of(renderer.get("ownerText")) or _text_of(
        renderer.get("longBylineText")
    )
    published_at = _parse_relative_time(_text_of(renderer.get("publishedTimeText")))
    return _source(
        title, video_id, channel, parse_view_count(views_text), published_at
    )


def _lockup_metadata_parts(lockup: dict[str, Any]) -> list[dict[str, Any]]:
    """Devuelve las partes de metadatos de un ``lockupViewModel``."""
    metadata = lockup.get("metadata")
    if not isinstance(metadata, dict):
        return []
    view_model = metadata.get("lockupMetadataViewModel")
    if not isinstance(view_model, dict):
        return []
    inner = view_model.get("metadata")
    if not isinstance(inner, dict):
        return []
    content = inner.get("contentMetadataViewModel")
    if not isinstance(content, dict):
        return []
    rows = content.get("metadataRows")
    if not isinstance(rows, list):
        return []
    parts: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for part in row.get("metadataParts") or []:
            if isinstance(part, dict):
                parts.append(part)
    return parts


def _source_from_lockup(lockup: dict[str, Any]) -> dict[str, Any] | None:
    """Construye una fuente a partir de un ``lockupViewModel``."""
    video_id = lockup.get("contentId")
    metadata = lockup.get("metadata")
    if not isinstance(video_id, str) or not video_id or not isinstance(metadata, dict):
        return None
    view_model = metadata.get("lockupMetadataViewModel")
    if not isinstance(view_model, dict):
        return None
    title = _text_of(view_model.get("title"))
    if not title:
        return None

    channel = ""
    views_text = ""
    published_text = ""
    for part in _lockup_metadata_parts(lockup):
        accessibility = part.get("accessibilityLabel")
        accessibility = accessibility if isinstance(accessibility, str) else ""
        text = _text_of(part.get("text"))
        avatar = part.get("avatarStack")
        if isinstance(avatar, dict):
            stack = avatar.get("avatarStackViewModel")
            if isinstance(stack, dict):
                channel = _text_of(stack.get("text")) or channel
            continue
        lowered = accessibility.lower()
        if "vistas" in lowered or "views" in lowered:
            # La etiqueta de accesibilidad trae la forma larga ("8.6 millones de
            # vistas"), que no depende de las abreviaturas por idioma.
            views_text = accessibility or views_text
        elif lowered.startswith("hace") or lowered.startswith("transmitido"):
            published_text = accessibility or published_text
        elif not published_text and text.lower().startswith(("hace", "transmitido")):
            published_text = text

    return _source(
        title,
        video_id,
        channel,
        parse_view_count(views_text),
        _parse_relative_time(published_text),
    )


def extract_sources_from_initial_data(payload: Any) -> list[dict[str, Any]]:
    """Extrae las fuentes de los resultados de busqueda de ``ytInitialData``.

    Acepta el diccionario ya parseado o su texto JSON. Reconoce los dos layouts
    que usa YouTube (``videoRenderer`` y ``lockupViewModel``) y descarta los
    videos repetidos, que YouTube devuelve cuando el titulo tiene version
    traducida.
    """
    if isinstance(payload, (str, bytes)):
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            return []
    if not isinstance(payload, dict):
        return []

    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for renderer in _iter_nodes(payload, "videoRenderer"):
        source = _source_from_video_renderer(renderer)
        if source is None:
            continue
        video_id = source["url"].rsplit("=", 1)[-1]
        if video_id in seen:
            continue
        seen.add(video_id)
        sources.append(source)
    for lockup in _iter_nodes(payload, "lockupViewModel"):
        source = _source_from_lockup(lockup)
        if source is None:
            continue
        video_id = source["url"].rsplit("=", 1)[-1]
        if video_id in seen:
            continue
        seen.add(video_id)
        sources.append(source)
    return sources


def extract_initial_data(html: str) -> dict[str, Any] | None:
    """Extrae y parsea el bloque JSON ``ytInitialData`` de la pagina de resultados."""
    index = html.find("var ytInitialData = ")
    if index == -1:
        return None
    start = html.find("{", index)
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for position in range(start, len(html)):
        character = html[position]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : position + 1])
                except ValueError:
                    return None
    return None


def extract_sources_from_html(html: str) -> list[dict[str, Any]]:
    """Extrae las fuentes de la pagina de resultados de YouTube.

    Usa la estructura ``ytInitialData`` cuando esta disponible (es lo normal) y
    recurre al extractor por expresiones regulares como respaldo.
    """
    initial_data = extract_initial_data(html)
    if initial_data is not None:
        sources = extract_sources_from_initial_data(initial_data)
        if sources:
            return sources
    return _extract_sources_from_html(html)



def search_youtube_videos_api(
    topic: str,
    limit: int = DEFAULT_LIMIT,
    region_code: str = "VE",
    api_key: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Busca videos con la Data API oficial de YouTube (``order=viewCount``)."""
    key = api_key or os.environ.get("YOUTUBE_API_KEY") or ""
    if not key:
        return [], {
            "platform": "youtube",
            "status": "error",
            "result_count": 0,
            "message": "YOUTUBE_API_KEY no esta definida.",
        }
    now = datetime.now(timezone.utc)
    published_after = (now - timedelta(days=14)).isoformat().replace("+00:00", "Z")
    try:
        search = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "type": "video",
                "order": "viewCount",
                "q": topic,
                "maxResults": max(1, limit),
                "regionCode": region_code,
                "publishedAfter": published_after,
                "key": key,
            },
            timeout=REQUEST_TIMEOUT,
        )
        search.raise_for_status()
        ids = [
            item.get("id", {}).get("videoId")
            for item in search.json().get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not ids:
            return [], {
                "platform": "youtube",
                "status": "no_results",
                "result_count": 0,
                "message": "La API no encontro videos coincidentes de los ultimos 14 dias.",
            }
        details = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,statistics", "id": ",".join(ids), "key": key},
            timeout=REQUEST_TIMEOUT,
        )
        details.raise_for_status()
    except requests.RequestException as error:
        # Nunca se imprime la excepcion completa: la URL puede contener la clave.
        message = f"La Data API de YouTube fallo: {error.__class__.__name__}"[:240]
        logger.warning(message)
        return [], {
            "platform": "youtube",
            "status": "error",
            "result_count": 0,
            "message": message,
        }

    sources: list[dict[str, Any]] = []
    for item in details.json().get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        published_at = snippet.get("publishedAt")
        try:
            published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
            age_hours = max((now - published).total_seconds() / 3600, 1 / 60)
            views = int(stats.get("viewCount", 0))
        except (AttributeError, TypeError, ValueError):
            continue
        sources.append(
            _source(
                snippet.get("title", ""),
                str(item.get("id", "")),
                snippet.get("channelTitle", ""),
                views,
                published_at,
            )
        )
        sources[-1]["views_per_hour"] = round(views / age_hours, 2)
    sources.sort(key=lambda item: item.get("views_per_hour") or 0, reverse=True)
    return sources[: max(1, limit)], {
        "platform": "youtube",
        "status": "metrics_available",
        "result_count": len(sources),
        "message": (
            "Ordenado por vistas por hora entre resultados coincidentes recientes; "
            "no representa un ranking global de viralidad."
        ),
    }


def search_viral_videos(
    topic: str,
    limit: int = DEFAULT_LIMIT,
    region_code: str | None = None,
    api_key: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Punto de entrada: usa la Data API si hay clave y el extractor sin clave si no.

    Devuelve ``(sources, platform_status)``. Si la Data API falla con clave presente se
    degrada al extractor sin clave; si ambos caminos fallan se devuelve el estado de
    error para que el worker siga adelante.
    """
    resolved_key = api_key if api_key is not None else os.environ.get("YOUTUBE_API_KEY")
    if resolved_key:
        sources, status = search_youtube_videos_api(
            topic,
            limit=limit,
            region_code=(region_code or os.environ.get("YOUTUBE_REGION_CODE") or "VE").upper(),
            api_key=resolved_key,
        )
        if sources:
            return sources, status
        logger.warning(
            "La Data API de YouTube no devolvio resultados; se usa el extractor sin clave."
        )
    return scrape_youtube_results(topic, limit=limit)


def search_platform_snippets(
    topic: str, platform: str, limit: int = 2
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Busca fragmentos publicos de una plataforma con DuckDuckGo (sin API key).

    Solo devuelve los titulos y un resumen del indice: no hay metricas de visualizaciones.
    Es el equivalente al camino ``snippet_only`` del notebook.
    """
    domains = PLATFORM_DOMAINS.get(platform)
    if not domains:
        return [], {
            "platform": platform,
            "status": "error",
            "result_count": 0,
            "message": f"Plataforma de investigacion no admitida: {platform}",
        }
    query = f"site:{domains[0]} {topic}"
    try:
        from ddgs import DDGS

        snippets = list(DDGS(timeout=10).text(query, max_results=max(1, limit)))
    except Exception as error:  # noqa: BLE001 - DuckDuckGo puede fallar o limitarse
        message = f"DuckDuckGo no respondio: {type(error).__name__}: {error}"[:240]
        logger.warning(message)
        return [], {
            "platform": platform,
            "status": "error",
            "result_count": 0,
            "message": message,
        }

    sources: list[dict[str, Any]] = []
    for item in snippets:
        url = item.get("href", "")
        body = (item.get("body") or "").strip()
        if not url or not _matches_platform(url, platform) or len(body) < 40:
            continue
        sources.append(
            {
                "platform": platform,
                "source_type": "search_snippet",
                "title": (item.get("title") or "").strip(),
                "url": url,
                "view_count": None,
                "published_at": None,
                "channel": "",
                "text": body[:MAX_TEXT_CHARS],
            }
        )
        if len(sources) >= limit:
            break

    if not sources:
        return [], {
            "platform": platform,
            "status": "no_results",
            "result_count": 0,
            "message": "DuckDuckGo no devolvio resultados publicos para esta plataforma.",
        }
    return sources, {
        "platform": platform,
        "status": "snippet_only",
        "result_count": len(sources),
        "message": "Se usan solo fragmentos del indice; no se pudo leer el post completo.",
    }


def main() -> int:
    """Prueba manual: ``python -m apps.workers.viral_research "finanzas personales"``."""
    import argparse

    parser = argparse.ArgumentParser(description="Busca videos virales de YouTube sin API key.")
    parser.add_argument("--topic", required=True, help="Tema a buscar.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Numero de videos.")
    parser.add_argument("--region-code", default=None, help="Codigo de region para la Data API.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sources, status = search_viral_videos(
        args.topic, limit=args.limit, region_code=args.region_code
    )
    logger.info("Estado de la plataforma: %s", status)
    for index, item in enumerate(sources, start=1):
        logger.info(
            "%d. %s | %s vistas | canal: %s | %s",
            index,
            item["title"],
            item.get("view_count"),
            item.get("channel") or "desconocido",
            item.get("url"),
        )
    return 0 if sources else 1


if __name__ == "__main__":
    raise SystemExit(main())
