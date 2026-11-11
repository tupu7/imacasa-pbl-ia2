# IMACASA · PC12 Inyectado

Proyecto dividido en dos servicios: **mock de infraestructura** (el que se expone para la prueba del checkpoint) y **app de demostración** (UI + backend de inspección). No son el mismo servicio.

## 0. Requisitos

- Windows 10/11 con Docker Desktop instalado y abierto (WSL 2 habilitado).
- Docker Compose v2 (`docker compose`).
- `cloudflared` instalado en Windows para crear el túnel.

## 1. Configuración segura

Desde PowerShell, en la carpeta raíz `imacasa-pc12`:

```powershell
Copy-Item .env.example .env
notepad .env
```

Cambia todos los valores de ejemplo. Usa contraseñas distintas y un `APP_SECRET` largo y aleatorio. **No compartas ni subas `.env` a Git.**

## 2. Levantar el mock obligatorio

```powershell
docker compose up -d --build mock
docker compose ps
docker compose logs mock
```

Pruebas locales (reemplaza los valores por los de tu `.env`):

```powershell
curl.exe -i http://localhost:8000/health
curl.exe -i http://localhost:8000/info
curl.exe -i -u equipoXX:TU_API_PASS http://localhost:8000/info
curl.exe -i http://localhost:8000/docs
curl.exe -i http://localhost:8000/openapi.json
```

Esperado: `/health` devuelve 200; `/info` sin credenciales devuelve 401; `/info` con credenciales correctas devuelve 200 y JSON; `/docs` y `/openapi.json` devuelven 404.

## 3. Exponer SOLO el mock con Cloudflare Tunnel

Con el mock ya levantado, abre otra ventana de PowerShell y ejecuta:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Copia la URL `https://....trycloudflare.com` que aparece. Mantén esa terminal abierta durante la evaluación. La URL rápida puede cambiar si reinicias el túnel.

Prueba la URL pública:

```powershell
curl.exe -i https://TU-URL.trycloudflare.com/health
curl.exe -i https://TU-URL.trycloudflare.com/info
curl.exe -i -u equipoXX:TU_API_PASS https://TU-URL.trycloudflare.com/info
```

No expongas la app completa en el túnel para cumplir el punto 5: el documento pide el mock con `/health` e `/info`.

## 4. Levantar la aplicación UI

En otra terminal:

```powershell
docker compose up -d --build app
```

Abre `http://localhost:8080`. Inicia sesión con los usuarios y contraseñas que configuraste en `APP_USERS` dentro de `.env`.

La UI usa modo **demo** mientras no existan modelos entrenados. Los resultados demo no son predicciones de IA reales.

## 5. PatchCore (experimental, no validado con fotos reales)

Se necesitan imágenes reales de machetes **OK**, organizadas por zona:

```text
app/data/good/
├── mal_inyectado/
├── pollera_tapada/
├── mal_desbarbado/
└── oxido_hoja/
```

Para entrenar, instala PyTorch y torchvision compatibles con tu equipo desde el selector oficial de instalación de PyTorch. Luego, desde PowerShell:

```powershell
cd app
python -m pip install -r requirements.txt
python -m pip install torch torchvision
python train.py --roi mal_inyectado --good data/good/mal_inyectado
```

Repite para las otras tres zonas. Cada carpeta debe tener al menos dos imágenes OK para la prueba mínima; para un piloto real hacen falta muchas más y deben separarse por machete físico, no solo por archivo.

Los modelos se guardan en `app/data/models/`. Para que la app dentro de Docker use PatchCore, hay que añadir `torch` y `torchvision` a las dependencias de la imagen y reconstruirla. No se incluyen por defecto porque aumentan mucho el tamaño y todavía no se ha validado el pipeline con tus fotos.

## 6. Comandos útiles

```powershell
docker compose ps
docker compose logs -f mock
docker compose logs -f app
docker compose stop
docker compose down
```

## Limitaciones conocidas

- PatchCore requiere validación con imágenes reales y revisión de umbrales.
- Desface de cacha y largo/ancho necesitan un módulo de medición con OpenCV y calibración píxel→mm.
- Espesor debe medirse con instrumento; una vista superior no permite medirlo de forma fiable.
- PC08 y PC10 aparecen en la UI como parte de la arquitectura general, pero esta implementación de inspección está limitada a PC12.
- Este prototipo no está certificado para controlar decisiones industriales sin validación, iluminación/captura controladas y revisión humana.

## Medición (OpenCV): largo, ancho y desface de cacha
`POST /api/medir` (con token) recibe `imagen`, `mm_px` (calibrado con `medicion.calibrar_tablero`) y, opcionalmente, tolerancias
(`largo_nom`, `largo_tol`, `ancho_nom`, `ancho_tol`, `desface_max`). Sin tolerancias solo devuelve las medidas.
Supone vista cenital con retroiluminación y cámara perpendicular. Validado solo con imágenes sintéticas.
