"""Pruebas de la aplicación principal (login, inspección, medición, historial).

Ejecutar desde la raíz del proyecto:
    .venv\\Scripts\\python.exe -m pytest tests/test_app.py -v
"""
import io
import os
import sys
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

# Configurar variables de entorno ANTES de importar la app
os.environ["APP_SECRET"] = "test-secret-con-al-menos-32-caracteres-para-pruebas"
os.environ["APP_USERS"] = "testop:testpass123:operador,testqa:qapass456:calidad"

# Asegurar que el directorio app/ esté en el path para importar medicion
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

# Necesitamos un directorio temporal para data/ durante pruebas
_tmpdir = tempfile.mkdtemp(prefix="imacasa_test_")
os.environ.setdefault("IMACASA_DATA_DIR", _tmpdir)

from app.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def get_token(client) -> str:
    """Helper: hace login y devuelve el token Bearer."""
    r = await client.post("/api/login", json={"usuario": "testop", "clave": "testpass123"})
    assert r.status_code == 200, f"Login falló: {r.text}"
    return r.json()["token"]


def make_test_image(width=100, height=300, color=(200, 200, 200)) -> bytes:
    """Genera una imagen sintética en memoria (JPEG)."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    buf.seek(0)
    return buf.getvalue()


def make_machete_silhouette(width=600, height=200) -> bytes:
    """Genera una silueta tipo machete (objeto oscuro sobre fondo claro) para medición."""
    import numpy as np
    img = Image.new("RGB", (width, height), (240, 240, 240))  # fondo claro
    pixels = img.load()
    # Dibujar un rectángulo oscuro que simule la silueta
    for x in range(50, width - 50):
        for y in range(60, height - 60):
            pixels[x, y] = (30, 30, 30)
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    buf.seek(0)
    return buf.getvalue()


# ── Login ─────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_login_valid(client):
    """POST /api/login con credenciales válidas devuelve token y rol."""
    r = await client.post("/api/login", json={"usuario": "testop", "clave": "testpass123"})
    assert r.status_code == 200
    data = r.json()
    assert "token" in data
    assert data["rol"] == "operador"


@pytest.mark.anyio
async def test_login_invalid_user(client):
    """POST /api/login con usuario inexistente devuelve 401."""
    r = await client.post("/api/login", json={"usuario": "noexiste", "clave": "loquesea"})
    assert r.status_code == 401


@pytest.mark.anyio
async def test_login_invalid_password(client):
    """POST /api/login con contraseña incorrecta devuelve 401."""
    r = await client.post("/api/login", json={"usuario": "testop", "clave": "wrongpass"})
    assert r.status_code == 401


# ── Autenticación por token ───────────────────────────────────
@pytest.mark.anyio
async def test_catalogo_without_token_returns_401(client):
    """GET /api/catalogo sin token devuelve 401."""
    r = await client.get("/api/catalogo")
    assert r.status_code == 401


@pytest.mark.anyio
async def test_catalogo_with_fake_token_returns_401(client):
    """GET /api/catalogo con token falso devuelve 401."""
    r = await client.get("/api/catalogo", headers={"Authorization": "Bearer token-falso.firma-falsa"})
    assert r.status_code == 401


@pytest.mark.anyio
async def test_catalogo_with_valid_token(client):
    """GET /api/catalogo con token válido devuelve estructura correcta."""
    token = await get_token(client)
    r = await client.get("/api/catalogo", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "estaciones" in data
    assert "defectos" in data
    assert "rois" in data
    station_ids = [s["id"] for s in data["estaciones"]]
    assert "PC08" in station_ids
    assert "PC10" in station_ids
    assert "PC12" in station_ids


# ── Inspección ────────────────────────────────────────────────
@pytest.mark.anyio
async def test_inspeccionar_empty_file_returns_400(client):
    """POST /api/inspeccionar con archivo vacío devuelve 400."""
    token = await get_token(client)
    r = await client.post(
        "/api/inspeccionar",
        headers={"Authorization": f"Bearer {token}"},
        data={"roi": "mal_inyectado", "station": "PC12", "machete": "M-TEST"},
        files={"imagen": ("empty.jpg", b"", "image/jpeg")},
    )
    assert r.status_code == 400


@pytest.mark.anyio
async def test_inspeccionar_invalid_file_returns_400(client):
    """POST /api/inspeccionar con archivo no-imagen devuelve 400."""
    token = await get_token(client)
    r = await client.post(
        "/api/inspeccionar",
        headers={"Authorization": f"Bearer {token}"},
        data={"roi": "mal_inyectado", "station": "PC12"},
        files={"imagen": ("fake.jpg", b"esto no es una imagen", "image/jpeg")},
    )
    assert r.status_code == 400


@pytest.mark.anyio
async def test_inspeccionar_invalid_roi_returns_400(client):
    """POST /api/inspeccionar con ROI inexistente devuelve 400."""
    token = await get_token(client)
    img = make_test_image()
    r = await client.post(
        "/api/inspeccionar",
        headers={"Authorization": f"Bearer {token}"},
        data={"roi": "zona_inexistente", "station": "PC12"},
        files={"imagen": ("test.jpg", img, "image/jpeg")},
    )
    assert r.status_code == 400


@pytest.mark.anyio
async def test_inspeccionar_valid_image_demo_mode(client):
    """POST /api/inspeccionar con imagen válida devuelve resultado en modo demo."""
    token = await get_token(client)
    img = make_test_image()
    r = await client.post(
        "/api/inspeccionar",
        headers={"Authorization": f"Bearer {token}"},
        data={"roi": "mal_inyectado", "station": "PC12", "machete": "M-TEST"},
        files={"imagen": ("test.jpg", img, "image/jpeg")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["modo"] == "demo", "Sin modelos entrenados debe funcionar en modo demo"
    assert data["veredicto"] in ("OK", "Defecto")
    assert "confianza" in data
    assert "timestamp" in data


# ── Medición ──────────────────────────────────────────────────
@pytest.mark.anyio
async def test_medir_invalid_mm_px_returns_400(client):
    """POST /api/medir con mm_px <= 0 devuelve 400."""
    token = await get_token(client)
    img = make_test_image()
    r = await client.post(
        "/api/medir",
        headers={"Authorization": f"Bearer {token}"},
        data={"mm_px": "0", "mango": "derecha"},
        files={"imagen": ("test.jpg", img, "image/jpeg")},
    )
    assert r.status_code == 400


@pytest.mark.anyio
async def test_medir_invalid_mango_returns_400(client):
    """POST /api/medir con mango inválido devuelve 400."""
    token = await get_token(client)
    img = make_test_image()
    r = await client.post(
        "/api/medir",
        headers={"Authorization": f"Bearer {token}"},
        data={"mm_px": "0.29", "mango": "arriba"},
        files={"imagen": ("test.jpg", img, "image/jpeg")},
    )
    assert r.status_code == 400


@pytest.mark.anyio
async def test_medir_synthetic_returns_measurements(client):
    """POST /api/medir con imagen sintética devuelve medidas numéricas."""
    token = await get_token(client)
    img = make_machete_silhouette()
    r = await client.post(
        "/api/medir",
        headers={"Authorization": f"Bearer {token}"},
        data={"mm_px": "0.29", "mango": "derecha", "mango_mm": "130"},
        files={"imagen": ("machete.jpg", img, "image/jpeg")},
    )
    assert r.status_code == 200
    data = r.json()
    assert "medidas" in data
    medidas = data["medidas"]
    assert "largo_mm" in medidas
    assert "ancho_max_mm" in medidas
    assert "desface_mm" in medidas
    # Todas deben ser números positivos
    assert medidas["largo_mm"] > 0
    assert medidas["ancho_max_mm"] > 0
    assert medidas["desface_mm"] >= 0


@pytest.mark.anyio
async def test_medir_without_tolerances_no_verdict(client):
    """POST /api/medir sin tolerancias no emite veredicto de aceptación."""
    token = await get_token(client)
    img = make_machete_silhouette()
    r = await client.post(
        "/api/medir",
        headers={"Authorization": f"Bearer {token}"},
        data={"mm_px": "0.29", "mango": "derecha"},
        files={"imagen": ("machete.jpg", img, "image/jpeg")},
    )
    assert r.status_code == 200
    data = r.json()
    # Sin tolerancias, dentro_de_tolerancia debe estar vacío
    assert data["dentro_de_tolerancia"] == {}


# ── Historial ─────────────────────────────────────────────────
@pytest.mark.anyio
async def test_historial_returns_list(client):
    """GET /api/historial devuelve una lista de registros."""
    token = await get_token(client)
    r = await client.get("/api/historial", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)


@pytest.mark.anyio
async def test_historial_filter_by_station(client):
    """GET /api/historial?station=PC12 filtra correctamente."""
    token = await get_token(client)
    r = await client.get("/api/historial?station=PC12", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    for row in data:
        assert row["station"] == "PC12"

