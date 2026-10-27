"""Cliente de Ollama (IA local y gratis)."""
import json
import re

import requests

from .util import log


class IA:
    def __init__(self, cfg: dict):
        c = cfg.get("ia", {})
        self.activa = bool(c.get("activa", True))
        self.modelo = c.get("modelo", "gemma2")
        # 127.0.0.1 y no "localhost": en Windows "localhost" prueba IPv6 primero y pierde ~2 s.
        self.url = c.get("url", "http://127.0.0.1:11434").replace("localhost", "127.0.0.1").rstrip("/")

    def disponible(self) -> bool:
        if not self.activa:
            return False
        try:
            return requests.get(f"{self.url}/api/tags", timeout=2).ok
        except requests.RequestException:
            return False

    def precalentar(self) -> None:
        """Carga el modelo en memoria para que la primera orden sea rápida."""
        try:
            requests.post(f"{self.url}/api/generate",
                          json={"model": self.modelo, "keep_alive": "30m"}, timeout=120)
        except requests.RequestException:
            pass

    def chat(self, sistema: str, usuario: str, como_json: bool = False, temperatura: float = 0.3) -> str:
        cuerpo = {
            "model": self.modelo,
            "messages": [{"role": "system", "content": sistema},
                         {"role": "user", "content": usuario}],
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": temperatura},
        }
        if como_json:
            cuerpo["format"] = "json"
        r = requests.post(f"{self.url}/api/chat", json=cuerpo, timeout=180)
        r.raise_for_status()
        return r.json()["message"]["content"].strip()

    def chat_json(self, sistema: str, usuario: str) -> dict:
        texto = self.chat(sistema, usuario, como_json=True, temperatura=0.1)
        try:
            return json.loads(texto)
        except ValueError:
            m = re.search(r"\{.*\}", texto, re.S)
            if m:
                return json.loads(m.group(0))
            log.warning("La IA no devolvió JSON: %s", texto)
            return {}
