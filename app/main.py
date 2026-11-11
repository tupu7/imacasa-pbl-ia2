import base64, hashlib, hmac, io, json, os, sqlite3, time
from datetime import datetime, timezone
import numpy as np
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from PIL import Image, UnidentifiedImageError

SECRET = os.getenv("APP_SECRET", "cambia-este-secreto").encode()
# APP_USERS="usuario:clave:rol,..."  (roles: operador | calidad | admin)
USERS = {u: (p, r) for u, p, r in (x.split(":") for x in
         os.getenv("APP_USERS", "operador:operador123:operador,calidad:calidad123:calidad").split(","))}
STATIONS = {"PC08": ("Enderezado", False), "PC10": ("Montaje", False), "PC12": ("Inyectado", True)}
# Un detector PatchCore por zona (ROI) -> cada uno responde una sola pregunta
ROIS = {"mal_inyectado": "Mal inyectado", "pollera_tapada": "Pollera tapada",
        "mal_desbarbado": "Mal desbarbado", "oxido_hoja": "Óxido en hoja"}
DEFECTS = [("desface_cacha", "Desface de cacha", ["PC10", "PC12"]),
           ("dimension_largo", "Largo fuera de especificación", ["PC12"]),
           ("dimension_ancho", "Ancho fuera de especificación", ["PC12"])] + \
          [(k, v, ["PC12"]) for k, v in ROIS.items()]
os.makedirs("data/images", exist_ok=True)
db = sqlite3.connect("data/app.db", check_same_thread=False); db.row_factory = sqlite3.Row
db.execute("""CREATE TABLE IF NOT EXISTS insp(id INTEGER PRIMARY KEY, ts TEXT, station TEXT, machete TEXT,
 verdict TEXT, defect TEXT, confidence REAL, score REAL, modo TEXT, image TEXT)""")
if not db.execute("SELECT 1 FROM insp").fetchone():  # filas de demostracion, marcadas modo='demo'
    for i, (st, d, v) in enumerate([("PC10", "desface_cacha", "Defecto"), ("PC12", "desface_cacha", "Defecto"),
            ("PC12", None, "OK"), ("PC12", "oxido_hoja", "Defecto"), ("PC08", "torcido", "Defecto"), ("PC10", None, "OK")]):
        db.execute("INSERT INTO insp(ts,station,machete,verdict,defect,confidence,score,modo) VALUES(?,?,?,?,?,?,?,?)",
                   (datetime.now(timezone.utc).isoformat(timespec="seconds"), st, f"M-{100+i}", v, d, .9, 0, "demo"))
    db.commit()

_models = {}
def detector(roi):
    p = f"data/models/{roi}.pt"
    if roi not in _models:
        if os.path.exists(p):
            from patchcore import PatchCore
            _models[roi] = PatchCore().load(p)
        else:
            _models[roi] = None   # sin modelo entrenado -> modo demo
    return _models[roi]

def infer(roi, img, raw):
    pc = detector(roi)
    if pc is None:  # DEMO: resultado determinista por hash, NO es un modelo real
        h = int(hashlib.sha1(raw).hexdigest()[:4], 16) % 100
        return h < 30, .6 + (h % 40) / 100, float(h), None, "demo"
    s, amap = pc.score(img)
    conf = .5 + .5 * np.tanh(2 * abs(s - pc.thr) / pc.thr)
    a = (amap - amap.min()) / (np.ptp(amap) + 1e-9)
    heat = np.zeros((*a.shape, 4), np.uint8); heat[..., 0] = 255; heat[..., 3] = (a * 170).astype(np.uint8)
    buf = io.BytesIO(); Image.fromarray(heat).save(buf, "PNG")
    return s > pc.thr, float(conf), s, base64.b64encode(buf.getvalue()).decode(), "patchcore"

def token(u, r):
    b = base64.urlsafe_b64encode(json.dumps({"u": u, "r": r, "exp": time.time() + 8 * 3600}).encode()).decode()
    return b + "." + hmac.new(SECRET, b.encode(), hashlib.sha256).hexdigest()

def user(authorization: str = Header(None)):
    try:
        scheme, credentials = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise ValueError("Unsupported authorization scheme")
        b, sig = credentials.split(".", 1)
        expected = hmac.new(SECRET, b.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("Invalid signature")
        d = json.loads(base64.urlsafe_b64decode(b.encode()))
        if not isinstance(d, dict) or not isinstance(d.get("exp"), (int, float)) or d["exp"] <= time.time():
            raise ValueError("Expired or malformed token")
        if not isinstance(d.get("u"), str) or not isinstance(d.get("r"), str):
            raise ValueError("Malformed token claims")
        return d
    except Exception:
        raise HTTPException(401, "Sesión inválida o vencida. Inicia sesión de nuevo.",
                            headers={"WWW-Authenticate": "Bearer"})

app = FastAPI(title="Inspección machetes", docs_url=None, redoc_url=None, openapi_url=None)
class Login(BaseModel): usuario: str; clave: str

@app.post("/api/login")
def login(b: Login):
    u = USERS.get(b.usuario)
    if not u or not hmac.compare_digest(u[0], b.clave): raise HTTPException(401, "Usuario o contraseña incorrectos.")
    return {"token": token(b.usuario, u[1]), "rol": u[1]}

@app.get("/api/catalogo")
def catalogo(_=Depends(user)):
    return {"estaciones": [{"id": k, "nombre": v[0], "implementada": v[1]} for k, v in STATIONS.items()],
            "defectos": [{"id": a, "nombre": b, "estaciones": c} for a, b, c in DEFECTS], "rois": ROIS}

@app.get("/api/resumen")
def resumen(_=Depends(user)):
    return {r["station"]: {"total": r["n"], "defectos": r["d"], "ultima": r["u"]} for r in db.execute(
        "SELECT station, COUNT(*) n, SUM(verdict='Defecto') d, MAX(ts) u FROM insp GROUP BY station")}

@app.post("/api/inspeccionar")
async def inspeccionar(imagen: UploadFile = File(...), roi: str = Form(...), station: str = Form("PC12"),
                       machete: str = Form("sin-id"), u=Depends(user)):
    if station != "PC12" or roi not in ROIS: raise HTTPException(400, "Solo PC12 y zonas: " + ", ".join(ROIS))
    raw = await imagen.read()
    if not raw:
        raise HTTPException(400, "El archivo de imagen está vacío.")
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "El archivo enviado no es una imagen válida.")
    t0 = time.time(); bad, conf, score, heat, modo = infer(roi, img, raw)
    path = f"data/images/{int(t0*1000)}.jpg"; img.save(path)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    db.execute("INSERT INTO insp(ts,station,machete,verdict,defect,confidence,score,modo,image) VALUES(?,?,?,?,?,?,?,?,?)",
               (ts, station, machete, "Defecto" if bad else "OK", roi if bad else None, conf, score, modo, path)); db.commit()
    return {"estacion": station, "veredicto": "Defecto" if bad else "OK", "defecto": ROIS[roi] if bad else None,
            "confianza": round(conf, 3), "puntaje": round(score, 3), "modo": modo, "mapa": heat,
            "latencia_ms": round((time.time() - t0) * 1000), "timestamp": ts}

@app.get("/api/historial")
def historial(station: str = "", defect: str = "", desde: str = "", hasta: str = "", _=Depends(user)):
    q, a = "SELECT * FROM insp WHERE 1=1", []
    for c, v, op in (("station", station, "="), ("defect", defect, "="), ("ts", desde, ">="), ("ts", hasta and hasta + "~", "<=")):
        if v: q += f" AND {c} {op} ?"; a.append(v)
    return [dict(r) for r in db.execute(q + " ORDER BY id DESC LIMIT 200", a)]

@app.post("/api/medir")
async def medir_ep(imagen: UploadFile = File(...), mm_px: float = Form(...), mango: str = Form("derecha"),
                   mango_mm: float = Form(130.0), largo_nom: float = Form(None), largo_tol: float = Form(None),
                   ancho_nom: float = Form(None), ancho_tol: float = Form(None), desface_max: float = Form(None),
                   _=Depends(user)):
    """Mide largo, ancho y desface. Sin tolerancias (pendientes de IMACASA) devuelve solo las medidas."""
    import cv2, medicion
    if mm_px <= 0 or mango not in ("derecha", "izquierda"): raise HTTPException(400, "mm_px > 0 y mango derecha|izquierda.")
    img = cv2.imdecode(np.frombuffer(await imagen.read(), np.uint8), cv2.IMREAD_COLOR)
    if img is None: raise HTTPException(400, "El archivo enviado no es una imagen válida.")
    try: med = medicion.medir(img, mm_px, mango, mango_mm)
    except ValueError as e: raise HTTPException(422, str(e))
    spec = {"largo_mm": (largo_nom, largo_tol) if largo_nom is not None and largo_tol is not None else None,
            "ancho_max_mm": (ancho_nom, ancho_tol) if ancho_nom is not None and ancho_tol is not None else None,
            "desface_mm": desface_max}
    return {"medidas": med, "dentro_de_tolerancia": medicion.veredicto(med, spec)}

@app.get("/")
def index(): return FileResponse("static/index.html")
