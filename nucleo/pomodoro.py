"""Temporizador pomodoro con avisos por voz y conteo diario."""
import threading
import time
import winsound
from datetime import date

from .util import a_numero, guardar_json, leer_json


def _mmss(segundos: float) -> str:
    s = max(0, int(segundos))
    return f"{s // 60}:{s % 60:02d}"


def _hablado(segundos: float) -> str:
    s = max(0, int(segundos))
    m, s = divmod(s, 60)
    if m and s:
        return f"{m} minutos y {s} segundos"
    return f"{m} minutos" if m else f"{s} segundos"


class Pomodoro:
    def __init__(self, ctx):
        self.ctx = ctx
        self.fase = None          # None / "enfoque" / "descanso"
        self.fin = 0.0
        self.pausado_restante = None
        self.ciclos = 0
        self._lock = threading.Lock()
        threading.Thread(target=self._bucle, daemon=True, name="pomodoro").start()

    @property
    def cfg(self):
        return self.ctx.cfg.get("pomodoro", {})

    def restante(self) -> float:
        if self.pausado_restante is not None:
            return self.pausado_restante
        return self.fin - time.time()

    def estado_corto(self) -> str:
        if not self.fase:
            return ""
        icono = "🍅" if self.fase == "enfoque" else "☕"
        pausa = " (pausa)" if self.pausado_restante is not None else ""
        return f"{icono} {_mmss(self.restante())}{pausa}"

    # --- órdenes ---
    def ejecutar(self, op: str, minutos=None, largo=False):
        if op == "iniciar":
            n = (a_numero(str(minutos)) if minutos else None) or self.cfg.get("enfoque", 25)
            self._iniciar("enfoque", n)
            if self.cfg.get("musica_al_iniciar") and self.cfg.get("playlist_enfoque"):
                self.ctx.ejecutar("spotify", {"consulta": self.cfg["playlist_enfoque"], "tipo": "playlist"}, callado=True)
            return f"Pomodoro de {_hablado(float(n) * 60)} iniciado. ¡A concentrarse!"
        if op == "descanso":
            n = self.cfg.get("descanso_largo", 15) if largo else self.cfg.get("descanso", 5)
            self._iniciar("descanso", n)
            return f"Descanso de {n} minutos."
        if not self.fase:
            if op == "contar":
                return f"Hoy hiciste {self.hoy()} pomodoros."
            return "No hay ningún pomodoro activo. Di: pon el pomodoro."
        if op == "pausar":
            with self._lock:
                if self.pausado_restante is None:
                    self.pausado_restante = self.fin - time.time()
            return f"Pomodoro en pausa. Quedan {_hablado(self.restante())}."
        if op == "reanudar":
            with self._lock:
                if self.pausado_restante is not None:
                    self.fin = time.time() + self.pausado_restante
                    self.pausado_restante = None
            return "Pomodoro reanudado."
        if op == "detener":
            self.fase, self.pausado_restante = None, None
            return "Pomodoro detenido."
        if op == "estado":
            que = "de enfoque" if self.fase == "enfoque" else "de descanso"
            return f"Quedan {_hablado(self.restante())} {que}."
        if op == "contar":
            return f"Hoy hiciste {self.hoy()} pomodoros."
        return "No entendí qué hacer con el pomodoro."

    def hoy(self) -> int:
        return leer_json("pomodoros.json", {}).get(date.today().isoformat(), 0)

    def _iniciar(self, fase: str, minutos: float):
        with self._lock:
            self.fase = fase
            self.fin = time.time() + float(minutos) * 60
            self.pausado_restante = None

    def _bucle(self):
        while True:
            time.sleep(1)
            self.ctx.actualizar_bandeja(self.estado_corto())
            if not self.fase or self.pausado_restante is not None or time.time() < self.fin:
                continue
            if self.fase == "enfoque":
                datos = leer_json("pomodoros.json", {})
                hoy = date.today().isoformat()
                datos[hoy] = datos.get(hoy, 0) + 1
                guardar_json("pomodoros.json", datos)
                self.ciclos += 1
                largo = self.ciclos % int(self.cfg.get("ciclos_para_largo", 4)) == 0
                minutos = self.cfg.get("descanso_largo", 15) if largo else self.cfg.get("descanso", 5)
                self._iniciar("descanso", minutos)
                self._sonar()
                self.ctx.decir(f"🍅 ¡Pomodoro terminado! Llevas {datos[hoy]} hoy. "
                               f"Descanso{' largo' if largo else ''} de {minutos} minutos.", 15, importante=True)
            else:
                self.fase = None
                self._sonar()
                self.ctx.decir("☕ Se acabó el descanso. Cuando quieras: «pon el pomodoro».", 15, importante=True)

    @staticmethod
    def _sonar():
        for f in (880, 1175, 1568):
            winsound.Beep(f, 180)
