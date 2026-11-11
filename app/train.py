"""Entrena un detector PatchCore por zona usando solo imágenes OK.
Ejemplo: python train.py --roi mal_inyectado --good data/good/mal_inyectado
"""
import argparse
import glob
import os
from patchcore import PatchCore

parser = argparse.ArgumentParser()
parser.add_argument("--roi", required=True)
parser.add_argument("--good", required=True)
parser.add_argument("--ratio", type=float, default=0.1)
args = parser.parse_args()

files = sorted(
    path for path in glob.glob(os.path.join(args.good, "*"))
    if os.path.isfile(path) and path.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp"))
)
if len(files) < 2:
    raise SystemExit(
        f"Se necesitan al menos 2 imágenes OK en {args.good}: "
        f"una para entrenamiento y otra para calibración. Encontradas: {len(files)}"
    )

split = max(1, min(len(files) - 1, int(len(files) * 0.8)))
train_files, calibration_files = files[:split], files[split:]

detector = PatchCore()
detector.fit(train_files, calibration_files, ratio=args.ratio)
os.makedirs("data/models", exist_ok=True)
output = f"data/models/{args.roi}.pt"
detector.save(output)
print(f"{args.roi}: {len(train_files)} train, {len(calibration_files)} calibración, "
      f"umbral={detector.thr:.3f}, archivo={output}")
print("IMPORTANTE: separar por machete físico antes del entrenamiento para evitar fuga de datos.")
