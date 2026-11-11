"""Pruebas del extractor de videos virales de YouTube.

Reproducen los defectos medidos contra YouTube real:

- **E2E-08**: el extractor solo entendia el layout ``videoRenderer``. Cuando YouTube
  sirve el layout ``lockupViewModel`` (titulo en ``metadata...title.content``) el
  regex no encontraba ningun titulo y el worker devolvia ``no_results``.
- **E2E-09**: ``parse_view_count`` multiplicaba por un millon ``"8.6 M"`` en vez de
  8,6 millones: devolvia 86.000.000. Ademas ignoraba el separador decimal.
- **E2E-10**: ``_parse_relative_time`` reventaba con ``TypeError`` al usar
  ``timedelta(months=...)`` y no entendia las abreviaturas que usa YouTube en
  espanol (``"hace 10 a"`` = 10 anos, ``"hace 3 m"`` = 3 meses).

Los fixtures de ``tests/fixtures`` son recortes reales de ``ytInitialData``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.workers import viral_research

FIXTURES = Path(__file__).parent / "fixtures"


def cargar_fixture(nombre: str) -> dict:
    return json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# E2E-08: los dos layouts de resultados de YouTube
# --------------------------------------------------------------------------


def test_extrae_videos_del_layout_video_renderer() -> None:
    """El layout clasico (title.runs) debe producir una fuente por video."""
    fixture = cargar_fixture("youtube_layout_video_renderer.json")

    sources = viral_research.extract_sources_from_initial_data(fixture)

    assert len(sources) == 6
    assert sources[0]["title"]
    assert sources[0]["url"].startswith("https://www.youtube.com/watch?v=")
    assert sources[0]["view_count"] is not None


def test_extrae_videos_del_layout_lockup_viewmodel() -> None:
    """El layout alternativo (metadata...title.content) tambien debe extraerse.

    Este es el layout que hacia fallar al worker con ``no_results``.
    """
    fixture = cargar_fixture("youtube_layout_lockup_viewmodel.json")

    sources = viral_research.extract_sources_from_initial_data(fixture)

    # El fixture tiene 6 entradas pero solo 5 videos distintos: YouTube repite
    # QThz1B8SHmc con el titulo traducido al ingles.
    assert len(sources) == 5
    assert sources[0]["title"]
    assert sources[0]["url"].startswith("https://www.youtube.com/watch?v=")


def test_el_extractor_descarta_videos_repetidos() -> None:
    """Un video con dos titulos (traducido y original) cuenta una sola vez."""
    fixture = cargar_fixture("youtube_layout_lockup_viewmodel.json")

    sources = viral_research.extract_sources_from_initial_data(fixture)

    identificadores = [source["url"].rsplit("=", 1)[-1] for source in sources]
    assert len(identificadores) == len(set(identificadores))


def test_el_layout_alternativo_expone_vistas_y_canal() -> None:
    """Las vistas y el canal del lockup se sacan de la fila de metadatos."""
    fixture = cargar_fixture("youtube_layout_lockup_viewmodel.json")

    sources = viral_research.extract_sources_from_initial_data(fixture)

    assert all(source["view_count"] is not None for source in sources)
    assert all(source["view_count"] > 0 for source in sources)
    assert any(source["channel"] for source in sources)


def test_el_extractor_no_inventa_titulos_vacios() -> None:
    """Un resultado sin titulo no debe generar una fuente inutil."""
    fixture = {
        "results": [
            {"lockupViewModel": {"contentId": "abc12345678", "metadata": {}}},
        ]
    }

    assert viral_research.extract_sources_from_initial_data(fixture) == []


def test_el_extractor_acepta_ambas_formas_de_fixture() -> None:
    """La funcion de alto nivel acepta un dict de datos o un JSON ya parseado."""
    fixture = cargar_fixture("youtube_layout_video_renderer.json")

    desde_dict = viral_research.extract_sources_from_initial_data(fixture)
    desde_json = viral_research.extract_sources_from_initial_data(
        json.dumps(fixture, ensure_ascii=False)
    )

    # ``published_at`` se calcula contra la hora actual, asi que se comparan los
    # campos estables y se comprueba que la fecha tambien esta.
    assert len(desde_dict) == len(desde_json)
    for uno, otro in zip(desde_dict, desde_json):
        comparable = dict(uno)
        otro_comparable = dict(otro)
        comparable.pop("published_at")
        otro_comparable.pop("published_at")
        assert comparable == otro_comparable
        assert uno["published_at"] is not None


# --------------------------------------------------------------------------
# E2E-09: conteo de vistas
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("8,259,754 vistas", 8_259_754),
        ("8.259.754 vistas", 8_259_754),
        ("8,6 M", 8_600_000),
        ("8.6 M", 8_600_000),
        ("2 M", 2_000_000),
        ("3 M", 3_000_000),
        ("12K views", 12_000),
        ("1.5 K", 1_500),
        ("701 mil vistas", 701_000),
        ("9,5 mil", 9_500),
        ("4,4 millones de vistas", 4_400_000),
        ("2,1 billions views", 2_100_000_000),
    ],
)
def test_parse_view_count_interpreta_separadores_y_abreviaturas(
    texto: str, esperado: int
) -> None:
    assert viral_research.parse_view_count(texto) == esperado


def test_parse_view_count_devuelve_none_sin_numeros() -> None:
    assert viral_research.parse_view_count("sin numero") is None
    assert viral_research.parse_view_count(None) is None


# --------------------------------------------------------------------------
# E2E-11: el filtro de popularidad se enviaba doblemente codificado
# --------------------------------------------------------------------------


def test_el_filtro_de_popularidad_no_se_doble_codifica() -> None:
    """``sp`` debe viajar como ``CAM%3D``, no como ``CAM%253D``.

    Con ``CAM%253D`` YouTube ignora el filtro y ordena por relevancia en vez de
    por numero de vistas. Medido contra YouTube real: con el filtro correcto la
    respuesta viene ordenada de mas a menos vistas; con el doble escapado no.
    """
    import requests

    url = requests.Request(
        "GET",
        viral_research.YOUTUBE_RESULTS_URL,
        params={"search_query": "finanzas", "sp": viral_research.POPULARITY_FILTER},
    ).prepare().url

    assert "sp=CAM%3D" in url
    assert "sp=CAM%253D" not in url


def test_la_constante_de_popularidad_no_esta_pre_codificada() -> None:
    """La constante guarda el valor en claro, no su forma escapada."""
    assert viral_research.POPULARITY_FILTER == "CAM="
    assert "%" not in viral_research.POPULARITY_FILTER


# --------------------------------------------------------------------------
# E2E-10: fechas relativas
# --------------------------------------------------------------------------


def test_parse_relative_time_no_reventa_con_meses() -> None:
    """``timedelta`` no admite ``months``: hay que convertir a dias."""
    resultado = viral_research._parse_relative_time("hace 3 meses")

    assert resultado is not None
    assert resultado.endswith("Z")


def test_parse_relative_time_entiende_anos_en_español() -> None:
    """YouTube abrevia los anos como ``a`` en espanol."""
    resultado = viral_research._parse_relative_time("hace 10 a")

    assert resultado is not None
    # "hace 10 a" son 10 anos: mas de 3000 dias.
    assert _dias_desde(resultado) > 3000


def test_parse_relative_time_entiende_meses_por_abreviatura() -> None:
    """``hace 3 m`` son 3 meses (~90 dias), no minutos."""
    resultado = viral_research._parse_relative_time("hace 3 m")

    assert resultado is not None
    dias = _dias_desde(resultado)
    assert 80 <= dias <= 100


def test_parse_relative_time_entiende_semanas() -> None:
    resultado = viral_research._parse_relative_time("hace 2 sem.")

    assert resultado is not None
    dias = _dias_desde(resultado)
    assert 12 <= dias <= 16


def test_parse_relative_time_entiende_dias_completos() -> None:
    resultado = viral_research._parse_relative_time("hace 4 días")

    assert resultado is not None
    dias = _dias_desde(resultado)
    assert 3 <= dias <= 5


def test_parse_relative_time_ignora_texto_sin_fecha() -> None:
    assert viral_research._parse_relative_time("hace un rato") is None
    assert viral_research._parse_relative_time(None) is None


def _dias_desde(iso: str) -> float:
    """Dias transcurridos desde la marca ISO devuelta por el parser."""
    from datetime import datetime, timezone

    momento = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - momento).total_seconds() / 86400
