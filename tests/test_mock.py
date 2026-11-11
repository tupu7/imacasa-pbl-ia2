"""Pruebas del servicio mock (GET /health, GET /info, endpoints desactivados).

Ejecutar desde la raíz del proyecto:
    .venv\\Scripts\\python.exe -m pytest tests/test_mock.py -v
"""
import base64

import pytest
from httpx import ASGITransport, AsyncClient

# Configurar las variables de entorno ANTES de importar el módulo
import os
os.environ.setdefault("API_USER", "testuser")
os.environ.setdefault("API_PASS", "testpass")
os.environ.setdefault("TEAM", "Equipo Test")

# Importar después de configurar el entorno
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mock"))
from mock.main import app

VALID_CREDS = base64.b64encode(b"testuser:testpass").decode()
INVALID_CREDS = base64.b64encode(b"wrong:wrong").decode()


@pytest.fixture
def client():
    """Cliente HTTP de pruebas para el mock (síncrono vía transport ASGI)."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ── GET /health ───────────────────────────────────────────────
@pytest.mark.anyio
async def test_health_returns_200(client):
    """GET /health debe responder HTTP 200 sin autenticación."""
    r = await client.get("/health")
    assert r.status_code == 200


@pytest.mark.anyio
async def test_health_json_structure(client):
    """GET /health debe devolver {"status": "ok"}."""
    r = await client.get("/health")
    data = r.json()
    assert data == {"status": "ok"}


# ── GET /info ─────────────────────────────────────────────────
@pytest.mark.anyio
async def test_info_without_credentials_returns_401(client):
    """GET /info sin credenciales debe responder HTTP 401."""
    r = await client.get("/info")
    assert r.status_code == 401


@pytest.mark.anyio
async def test_info_with_wrong_credentials_returns_401(client):
    """GET /info con credenciales incorrectas debe responder HTTP 401."""
    r = await client.get("/info", headers={"Authorization": f"Basic {INVALID_CREDS}"})
    assert r.status_code == 401


@pytest.mark.anyio
async def test_info_with_valid_credentials_returns_200(client):
    """GET /info con credenciales válidas debe responder HTTP 200."""
    r = await client.get("/info", headers={"Authorization": f"Basic {VALID_CREDS}"})
    assert r.status_code == 200


@pytest.mark.anyio
async def test_info_json_structure(client):
    """GET /info debe incluir equipo, estacion, version y timestamp."""
    r = await client.get("/info", headers={"Authorization": f"Basic {VALID_CREDS}"})
    data = r.json()
    assert "equipo" in data
    assert "estacion" in data
    assert data["estacion"] == "PC12 Inyectado"
    assert "version" in data
    assert "timestamp" in data


# ── Endpoints desactivados ────────────────────────────────────
@pytest.mark.anyio
async def test_docs_returns_404(client):
    """GET /docs debe responder HTTP 404 (desactivado)."""
    r = await client.get("/docs")
    assert r.status_code == 404


@pytest.mark.anyio
async def test_openapi_json_returns_404(client):
    """GET /openapi.json debe responder HTTP 404 (desactivado)."""
    r = await client.get("/openapi.json")
    assert r.status_code == 404

