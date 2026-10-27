"""Rutas, configuración y registro (log) compartidos."""
import json
import logging
import os
import shutil
from pathlib import Path

import yaml

BASE = Path(__file__).resolve().parent.parent
DATOS = BASE / "datos"
DATOS.mkdir(exist_ok=True)
CONFIG = BASE / "config.yaml"
NOTAS = BASE / "notas.md"

logging.basicConfig(
    filename=DATOS / "asistente.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("asistente")


def cargar_config() -> dict:
    if not CONFIG.exists():  # primera vez: parte de la configuración de ejemplo
        shutil.copy(BASE / "config.example.yaml", CONFIG)
    with open(CONFIG, encoding="utf-8-sig") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.setdefault("sitios", {})
    cfg.setdefault("apps", {})
    cfg.setdefault("carpetas", {})
    cfg["contactos"] = cfg.get("contactos") or {}
    cfg["carpetas"] = {k: os.path.expanduser(v) for k, v in (cfg["carpetas"] or {}).items()}
    return cfg


def leer_json(nombre: str, defecto):
    ruta = DATOS / nombre
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def guardar_json(nombre: str, valor) -> None:
    (DATOS / nombre).write_text(json.dumps(valor, ensure_ascii=False, indent=2), encoding="utf-8")


PALABRAS_NUMERO = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11,
    "doce": 12, "quince": 15, "veinte": 20, "veinticinco": 25, "treinta": 30,
    "cuarenta": 40, "cuarenta y cinco": 45, "cincuenta": 50, "sesenta": 60,
    "noventa": 90, "media": 0.5,
}


def a_numero(texto: str | None) -> float | None:
    if not texto:
        return None
    texto = texto.strip()
    try:
        return float(texto.replace(",", "."))
    except ValueError:
        return PALABRAS_NUMERO.get(texto)
