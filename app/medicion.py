"""Medicion con OpenCV: calibracion px->mm, largo, ancho y desface de cacha.
Supone vista cenital con retroiluminacion (machete oscuro sobre fondo claro) y camara perpendicular."""
import cv2, numpy as np

def calibrar_tablero(img_bgr, patron=(9, 6), cuadro_mm=10.0):
    """mm por pixel a partir de un tablero de ajedrez impreso (esquinas internas = patron)."""
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    ok, c = cv2.findChessboardCorners(g, patron)
    if not ok: raise ValueError("No se detecto el tablero de calibracion.")
    c = c.reshape(patron[1], patron[0], 2)
    paso = np.mean(np.linalg.norm(np.diff(c, axis=1), axis=2))   # px entre esquinas contiguas
    return cuadro_mm / float(paso)

def medir(img_bgr, mm_px, mango="derecha", mango_mm=130.0):
    g = cv2.GaussianBlur(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    _, m = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs: raise ValueError("No se encontro la silueta del machete.")
    cnt = max(cs, key=cv2.contourArea)
    (cx, cy), (w, h), ang = cv2.minAreaRect(cnt)
    if w < h: ang += 90                      # alinear el eje largo con X
    R = cv2.getRotationMatrix2D((cx, cy), ang, 1.0)
    sil = np.zeros_like(m); cv2.drawContours(sil, [cnt], -1, 255, -1)
    sil = cv2.warpAffine(sil, R, sil.shape[::-1], flags=cv2.INTER_NEAREST) > 0
    cols = np.where(sil.any(0))[0]; x0, x1 = cols[0], cols[-1]
    sil = sil[:, x0:x1 + 1]
    if mango == "izquierda": sil = sil[:, ::-1]
    L = sil.shape[1]; k = int(mango_mm / mm_px)
    ancho = sil[:, :L - k].sum(0)            # perfil de ancho de la hoja
    def eje(a, b):                           # linea central (fila media) en un tramo
        y = [np.mean(np.where(sil[:, i])[0]) for i in range(a, b) if sil[:, i].any()]
        return float(np.median(y))
    marg = int(10 / mm_px)                   # se ignoran 10 mm junto a la union
    desface = abs(eje(L - k + marg, L) - eje(0, L - k - marg)) * mm_px
    return {"largo_mm": round(L * mm_px, 2), "ancho_max_mm": round(float(ancho.max()) * mm_px, 2),
            "desface_mm": round(desface, 2)}

def veredicto(med, spec):
    """spec = {"largo_mm": (nominal, tol), "ancho_max_mm": (...), "desface_mm": max}. Sin spec -> sin veredicto."""
    out = {}
    for k, v in spec.items():
        if v is None: continue
        val = med[k]
        out[k] = (abs(val - v[0]) <= v[1]) if isinstance(v, tuple) else val <= v
    return out
