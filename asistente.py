"""Asistente de voz para Windows: presiona el atajo, habla, y lo hace.

Ejecuta con:  iniciar.bat   (o  .venv\\Scripts\\pythonw.exe asistente.py)
"""
import os
import queue
import sys
import threading
import time
import winsound
from datetime import datetime

import keyboard
import pystray
from PIL import Image, ImageDraw

from nucleo import acciones
from nucleo.google_ctl import Google
from nucleo.habla import Habla
from nucleo.ia import IA
from nucleo.pomodoro import Pomodoro
from nucleo.router import Interprete, interpretar_con_ia, normalizar
from nucleo.spotify_ctl import Spotify
from nucleo.ui import UI
from nucleo.util import BASE, CONFIG, NOTAS, cargar_config, guardar_json, leer_json, log
from nucleo.voz import Oido


class Recordatorios:
    def __init__(self, ctx):
        self.ctx = ctx
        self._lista = leer_json("recordatorios.json", [])
        self._lock = threading.Lock()
        threading.Thread(target=self._bucle, daemon=True, name="recordatorios").start()

    def agregar(self, cuando: datetime, texto: str):
        with self._lock:
            self._lista.append({"cuando": cuando.isoformat(), "texto": texto})
            guardar_json("recordatorios.json", self._lista)

    def _bucle(self):
        while True:
            time.sleep(2)
            ahora = datetime.now()
            with self._lock:
                vencidos = [r for r in self._lista if datetime.fromisoformat(r["cuando"]) <= ahora]
                if not vencidos:
                    continue
                self._lista = [r for r in self._lista if r not in vencidos]
                guardar_json("recordatorios.json", self._lista)
            for r in vencidos:
                for f in (988, 1319):
                    winsound.Beep(f, 200)
                self.ctx.decir(f"⏰ Recordatorio: {r['texto']}", segundos=15, importante=True)


class Asistente:
    def __init__(self):
        self.cfg = cargar_config()
        self._icono = None
        self._titulo_bandeja = ""
        self.habla = Habla()
        self.ui = UI(al_enviar_texto=lambda t: self._cola.put(("texto", t)))
        self.ia = IA(self.cfg)
        self.spotify = Spotify(self.cfg)
        self.google = Google(self.cfg)
        self.interprete = Interprete()
        self.oido = Oido(self.cfg)
        self.pomodoro = Pomodoro(self)
        self.recordatorios = Recordatorios(self)
        self._cola: queue.Queue = queue.Queue()
        self._escuchando = threading.Event()
        self._parar_grabacion = threading.Event()
        self._mantenido = threading.Event()  # el atajo sigue presionado
        self._ocupado = threading.Event()    # hay una orden de voz en curso
        self._se_solto = True
        self._inicio_atajo = 0.0
        threading.Thread(target=self._trabajador, daemon=True, name="trabajador").start()
        threading.Thread(target=self.ia.precalentar, daemon=True).start()

    # --- avisar ---
    def decir(self, texto: str, segundos: float = 4, importante: bool = False):
        """Muestra el resultado en pantalla. importante=True además deja una notificación de Windows."""
        if not texto:
            return
        log.info("Respuesta: %s", texto)
        self.ui.avisar(texto, segundos)
        if importante and self._icono:
            try:
                self._icono.notify(texto, "Asistente")
            except Exception:
                pass
        if self.cfg.get("responder_con_voz", False):
            self.habla.decir(texto.replace("⏰", "").replace("🍅", "").replace("✅", "").replace("⚠️", ""))

    def actualizar_bandeja(self, estado: str):
        titulo = "Asistente de voz" + (f" — {estado}" if estado else "")
        if self._icono and titulo != self._titulo_bandeja:
            self._titulo_bandeja = titulo
            self._icono.title = titulo

    # --- atajos ---
    def al_atajo_voz(self, desde_menu: bool = False):
        """Al presionar el atajo (Windows lo repite mientras lo mantienes, por eso se filtra)."""
        if self._ocupado.is_set():
            if self._escuchando.is_set() and self._se_solto:
                self._parar_grabacion.set()  # segundo toque = ya terminé de hablar
            return
        self._ocupado.set()
        self._parar_grabacion.clear()
        self._inicio_atajo = time.time()
        self._se_solto = desde_menu
        if desde_menu:
            self._mantenido.clear()
        else:
            self._mantenido.set()
        self._cola.put(("voz", None))

    def _al_soltar_atajo(self, _evento=None):
        if not self._ocupado.is_set() or self._se_solto:
            return
        self._se_solto = True
        self._mantenido.clear()
        if time.time() - self._inicio_atajo > 0.45:
            self._parar_grabacion.set()  # lo mantuviste mientras hablabas: soltar = terminé

    def registrar_atajos(self):
        for atajo in getattr(self, "_atajos", []):
            keyboard.remove_hotkey(atajo)
        if getattr(self, "_gancho_soltar", None):
            keyboard.unhook(self._gancho_soltar)
        atajo_voz = self.cfg.get("atajo_voz", "ctrl+alt+space")
        self._atajos = [
            keyboard.add_hotkey(atajo_voz, self.al_atajo_voz, suppress=True),
            keyboard.add_hotkey(self.cfg.get("atajo_texto", "ctrl+alt+t"), self.ui.pedir_texto,
                                suppress=True, trigger_on_release=True),
        ]
        self._gancho_soltar = keyboard.on_release_key(atajo_voz.split("+")[-1].strip(), self._al_soltar_atajo)

    # --- bucle de órdenes ---
    def _trabajador(self):
        import pythoncom
        pythoncom.CoInitialize()
        while True:
            tipo, texto = self._cola.get()
            try:
                if tipo == "voz":
                    texto = self._escuchar()
                    if not texto:
                        continue
                self.procesar(texto)
            except Exception:
                log.exception("Error procesando orden")
                self.decir("⚠️ Algo falló. Revisa datos/asistente.log.")
            finally:
                if tipo == "voz":
                    self._ocupado.clear()

    def _escuchar(self) -> str | None:
        self.habla.callar()
        self._escuchando.set()
        winsound.Beep(1046, 60)
        self.ui.avisar("🎙️ Te escucho…  (suelta el atajo al terminar)", None)
        try:
            audio = self.oido.grabar(self._parar_grabacion, self._mantenido)
        finally:
            self._escuchando.clear()
            self._mantenido.clear()
        winsound.Beep(784, 50)
        if audio is None:
            self.ui.avisar("No escuché nada.", 1.5)
            return None
        self.ui.avisar("Entendiendo…", None, girando=True)
        texto = self.oido.transcribir(audio)
        if not texto:
            self.ui.avisar("No te entendí, intenta de nuevo.", 2.5)
            return None
        return texto

    def procesar(self, texto: str):
        self._texto_actual = texto
        r = self.interprete.interpretar(texto)
        if r is None:
            r = self._solo_nombre(texto)
        if r is None:
            if self.ia.disponible():
                self.ui.avisar(f"Pensando…\n“{texto}”", None, girando=True)
                r = interpretar_con_ia(self.ia, texto)
            if r is None:
                self.decir(f"🤔 No entendí “{texto}”", 3.5)
                return
        self.ejecutar(*r)

    def _solo_nombre(self, texto: str):
        """Si solo dijiste el nombre de una página o app ("YouTube"), la abre."""
        nombre = " ".join(normalizar(texto).split())
        for grupo in ("sitios", "apps", "carpetas"):
            if nombre in {" ".join(normalizar(k).split()) for k in self.cfg[grupo]}:
                return "abrir", {"objetivo": nombre}
        return None

    def ejecutar(self, accion: str, args: dict, callado: bool = False):
        fn = acciones.ACCIONES.get(accion)
        if not fn:
            return
        args = args or {}
        if not callado:
            paso = acciones.progreso(accion, args)
            texto = getattr(self, "_texto_actual", "")
            self.ui.avisar(f"{paso}\n“{texto}”" if texto else paso, None, girando=True)
        try:
            respuesta = fn(self, args)
            if respuesta and respuesta.startswith("No "):
                respuesta = "⚠️ " + respuesta
            elif respuesta:
                respuesta = "✅ " + respuesta
        except acciones.AvisoUsuario as e:
            respuesta = f"⚠️ {e}"
        except Exception as e:
            log.exception("Acción %s falló", accion)
            respuesta = f"⚠️ No pude hacerlo: {e}"
        self._texto_actual = ""
        if callado:
            return
        if respuesta:
            self.decir(respuesta, segundos=9 if len(respuesta) > 90 else 3.5)
        else:
            self.ui.avisar("✅ Listo", 1.5)

    # --- bandeja ---
    def _crear_icono(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse((2, 2, 62, 62), fill=(217, 119, 87))
        d.rounded_rectangle((24, 12, 40, 38), radius=8, fill="white")
        d.arc((17, 22, 47, 46), 0, 180, fill="white", width=4)
        d.line((32, 46, 32, 53), fill="white", width=4)
        menu = pystray.Menu(
            pystray.MenuItem(f"Hablar ({self.cfg.get('atajo_voz')})", lambda: self.al_atajo_voz(desde_menu=True),
                             default=True),
            pystray.MenuItem(f"Escribir orden ({self.cfg.get('atajo_texto')})", lambda: self.ui.pedir_texto()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Ver lo que sé hacer", lambda: os.startfile(BASE / "LEEME.md")),
            pystray.MenuItem("Abrir mis notas", lambda: os.startfile(NOTAS) if NOTAS.exists() else None),
            pystray.MenuItem("Editar configuración", lambda: os.startfile(CONFIG)),
            pystray.MenuItem("Recargar configuración", lambda: self.recargar()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", lambda: self.salir()),
        )
        self._icono = pystray.Icon("asistente", img, "Asistente de voz", menu)
        self._icono.run_detached()

    def recargar(self):
        self.cfg = cargar_config()
        self.ia = IA(self.cfg)
        self.spotify = Spotify(self.cfg)
        self.google = Google(self.cfg)
        self.registrar_atajos()
        self.decir("Configuración recargada.")

    def salir(self):
        self.habla.callar()
        if self._icono:
            self._icono.stop()
        keyboard.unhook_all()
        self.ui.salir()

    def iniciar(self):
        self._crear_icono()
        self.registrar_atajos()
        self.ui.avisar(f"✅ Asistente listo. Presiona {self.cfg.get('atajo_voz')} y habla.", 5)
        log.info("Asistente iniciado")
        self.ui.bucle()


def ya_esta_abierto() -> bool:
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, "AsistenteDeVozLocal")
    return ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    os.chdir(BASE)
    if ya_esta_abierto():
        sys.exit(0)
    Asistente().iniciar()
