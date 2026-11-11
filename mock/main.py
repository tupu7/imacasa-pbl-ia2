import os, secrets
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

# Solo 2 endpoints: se desactivan /docs, /redoc y /openapi.json
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
security = HTTPBasic()
USER = os.getenv("API_USER", "equipo")
PASSWORD = os.getenv("API_PASS", "cambiar")

def auth(c: HTTPBasicCredentials = Depends(security)):
    ok = secrets.compare_digest(c.username.encode(), USER.encode()) & \
         secrets.compare_digest(c.password.encode(), PASSWORD.encode())
    if not ok:
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Basic"})

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/info", dependencies=[Depends(auth)])
def info():
    return {"equipo": os.getenv("TEAM", "Equipo ##"), "estacion": "PC12 Inyectado",
            "version": "0.1.0", "timestamp": datetime.now(timezone.utc).isoformat()}
