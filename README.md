# IMACASA · PC12 Inyectado — Sistema de Inspección Visual

Sistema de inspección de calidad asistido por visión por computadora e inteligencia artificial para la estación **PC12 (Inyectado)** en la línea de producción de machetes de IMACASA.

Arquitectura desacoplada en dos servicios independientes:
1. **Mock de infraestructura (`mock/`)**: Servicio minimalista que expone únicamente `GET /health` y `GET /info` bajo HTTP Basic Auth para la evaluación en vivo del Checkpoint 1 vía Cloudflare Tunnel.
2. **Aplicación principal (`app/`)**: Dashboard web, autenticación de operadores, motor de inferencia de anomalías (PatchCore en modo demo/offline), módulo de metrología 2D con OpenCV e historial de inspecciones.

---

## 0. Requisitos del Sistema

- **Python 3.12 o 3.13** (para ejecución y pruebas locales en `.venv`).
- **Windows 10/11 con WSL 2 habilitado**.
- **Docker Desktop** (opcional para desarrollo local, requerido para contenedorización de producción).
- **`cloudflared`** (para crear el túnel seguro hacia el mock en la evaluación en vivo).

---

## 1. Configuración de Variables de Entorno

Desde PowerShell, en el directorio del proyecto (`imacasa-pc12-v2\imacasa-pc12-v2`):

```powershell
Copy-Item .env.example .env
```

Edita `.env` y configura credenciales seguras. Si `APP_SECRET` o `APP_USERS` están ausentes o tienen valores de ejemplo, la aplicación se detiene inmediatamente por seguridad.

---

## 2. Ejecución Local con Entorno Virtual (Sin Docker)

Permite ejecutar el proyecto y correr pruebas sin depender de la instalación previa de Docker:

```powershell
# 1. Crear entorno virtual
python -m venv .venv

# 2. Activar entorno virtual
.\.venv\Scripts\Activate.ps1

# 3. Instalar dependencias de producción y desarrollo
pip install -r app/requirements.txt -r requirements-dev.txt

# 4. Ejecutar la suite completa de pruebas automatizadas (48 pruebas)
pytest -v

# 5. Ejecutar el servicio Mock localmente (puerto 8000)
python -m uvicorn mock.main:app --host 0.0.0.0 --port 8000

# 6. O ejecutar la aplicación principal localmente (puerto 8080)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

---

## 3. Pruebas Automatizadas

La suite incluye 48 casos de prueba automatizados con `pytest` y `httpx`:
- **Mock (`tests/test_mock.py`)**:
  - `GET /health`: HTTP 200 sin credenciales (`{"status": "ok"}`).
  - `GET /info`: HTTP 401 sin credenciales.
  - `GET /info`: HTTP 401 con credenciales incorrectas.
  - `GET /info`: HTTP 200 con credenciales correctas (valida estructura JSON: equipo, estación, versión, timestamp).
  - `/docs` y `/openapi.json`: HTTP 404 (bloqueados explícitamente).
- **App (`tests/test_app.py`)**:
  - Login válido, usuario inexistente y clave incorrecta.
  - Protección de endpoints con token Bearer firmado (rechazo de token falso o expirado).
  - Validación de carga de imágenes (rechazo de archivos vacíos, formatos inválidos, ROIs inexistentes).
  - Comportamiento determinista del modo DEMO cuando no hay modelos entrenados.
  - Módulo de medición geométrica `/api/medir` con imágenes sintéticas.
  - Filtros de historial por estación y defecto.

Comando para ejecutar las pruebas:
```powershell
pytest -v
```

---

## 4. Despliegue con Docker Compose

Una vez iniciado Docker Desktop:

```powershell
# Construir y levantar ambos servicios en segundo plano
docker compose up -d --build

# Ver el estado de los contenedores
docker compose ps

# Ver registros en tiempo real
docker compose logs -f mock
docker compose logs -f app
```

---

## 5. Exposición Pública del Mock con Cloudflare Tunnel

Durante la clase, solo se expone el servicio mock (puerto 8000):

```powershell
cloudflared tunnel --url http://localhost:8000
```

Copia la URL `https://xxxx.trycloudflare.com` y manten la consola abierta.

Comprobación desde PowerShell:
```powershell
curl.exe -i https://TU-URL.trycloudflare.com/health
curl.exe -i https://TU-URL.trycloudflare.com/info
curl.exe -i -u usuario:clave https://TU-URL.trycloudflare.com/info
```

---

## 6. Módulo de Visión Artificial e Inferencia

### A. Metrología 2D con OpenCV (`medicion.py`)
- Mide dimensiones físicas (largo de hoja, ancho máximo y desface de cacha).
- Requiere calibración previa px $\to$ mm (`medicion.calibrar_tablero`) con patrón de ajedrez.
- Supone vista cenital, retroiluminación difusa (fondo claro, pieza opaca) y cámara perpendicular.
- No emite veredicto de tolerancia si las tolerancias no han sido proporcionadas por IMACASA.

### B. Detección de Anomalías con PatchCore (`patchcore.py`)
- Modelo no supervisado basado en WideResNet-50 entrenado únicamente con piezas sanas (**OK**).
- Se asigna un detector independiente por cada zona de interés (ROI):
  1. `mal_inyectado`
  2. `pollera_tapada`
  3. `mal_desbarbado`
  4. `oxido_hoja`
- **Estado actual**: Implementación simplificada con coreset por proyección aleatoria. En ausencia de pesos entrenados y fotografías reales de planta, opera en **modo DEMO** explícito para fines académicos.

---

## 7. Limitaciones Técnicas y Criterios Industriales

1. **Espesor**: No es medible mediante cámara cenital 2D de forma fiable; requiere micrómetro/calibrador pie de rey o perfilometría láser 3D.
2. **Validación**: Los resultados con imágenes sintéticas validan la lógica del pipeline, pero no certifican precisión submilimétrica en planta.
3. **Tolerancias**: Las tolerancias de largo, ancho y desface están pendientes de confirmación formal con el equipo de ingeniería de IMACASA.
