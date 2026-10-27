"""Grabación del micrófono y transcripción con Whisper (local, gratis)."""
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

from .util import BASE, log

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


def _habilitar_cuda():
    """Hace visibles las librerías de NVIDIA instaladas con pip (cuBLAS, cuDNN)."""
    nvidia = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for sub in ("cublas", "cudnn", "cuda_runtime"):
        carpeta = nvidia / sub / "bin"
        if carpeta.exists():
            os.add_dll_directory(str(carpeta))
            os.environ["PATH"] = str(carpeta) + os.pathsep + os.environ.get("PATH", "")


_habilitar_cuda()

TASA = 16000
BLOQUE = 0.03  # segundos por bloque de audio

PISTA = ("Órdenes para un asistente en Perú: pon, pausa, siguiente, Spotify, YouTube, Google, "
         "pomodoro, abre, busca, recuérdame, anota, volumen.")


class Oido:
    def __init__(self, cfg: dict):
        self.cfg = cfg.get("voz", {})
        self._modelo = None
        self.dispositivo = None
        self._listo = threading.Event()
        threading.Thread(target=self._cargar, daemon=True, name="whisper").start()

    def _cargar(self):
        from faster_whisper import WhisperModel
        nombre = self.cfg.get("modelo_whisper", "large-v3-turbo")
        raiz = str(BASE / "modelos")
        intentos = []
        if self.cfg.get("dispositivo", "auto") in ("auto", "cuda", "gpu"):
            intentos.append((nombre, "cuda", "int8_float16"))
        intentos += [(nombre, "cpu", "int8"), ("small", "cpu", "int8")]
        for modelo, disp, tipo in intentos:
            try:
                self._modelo = WhisperModel(modelo, device=disp, compute_type=tipo, download_root=raiz)
                # Precalienta con un segundo de silencio para que la primera orden sea rápida.
                list(self._modelo.transcribe(np.zeros(TASA, dtype=np.float32), language="es")[0])
                self.dispositivo = disp
                log.info("Whisper '%s' cargado en %s", modelo, disp)
                break
            except Exception:
                log.exception("No se pudo cargar Whisper %s en %s", modelo, disp)
        self._listo.set()

    @property
    def listo(self) -> bool:
        return self._listo.is_set()

    def grabar(self, parar: threading.Event, mantenido: threading.Event) -> np.ndarray | None:
        """Graba hasta que:
        - sueltas el atajo (si lo mantienes presionado mientras hablas), o
        - dejas de hablar / vuelves a presionar el atajo (si solo lo tocaste)."""
        silencio_fin = float(self.cfg.get("silencio_fin", 1.0))
        try:
            tasa = TASA
            sd.check_input_settings(samplerate=tasa, channels=1)
        except Exception:
            tasa = int(sd.query_devices(kind="input")["default_samplerate"])
        n = int(tasa * BLOQUE)
        partes, ruido, hablo, silencio = [], [], False, 0.0
        inicio = time.time()
        with sd.InputStream(samplerate=tasa, channels=1, dtype="float32", blocksize=n) as flujo:
            while not parar.is_set():
                bloque, _ = flujo.read(n)
                bloque = bloque[:, 0].copy()
                partes.append(bloque)
                nivel = float(np.sqrt(np.mean(bloque ** 2)))
                transcurrido = time.time() - inicio
                if transcurrido < 0.25:
                    ruido.append(nivel)
                    continue
                umbral = max(0.012, 3 * (np.median(ruido) if ruido else 0.004))
                if nivel > umbral:
                    hablo, silencio = True, 0.0
                else:
                    silencio += BLOQUE
                if mantenido.is_set():
                    if transcurrido >= 30:  # tope de seguridad
                        break
                    continue  # mientras mantengas el atajo, no se corta por pausas
                if hablo and silencio >= silencio_fin:
                    break
                if not hablo and transcurrido > 6:
                    return None  # no se dijo nada
                if transcurrido >= float(self.cfg.get("max_segundos", 15)):
                    break
        audio = np.concatenate(partes) if partes else np.zeros(0, dtype=np.float32)
        if tasa != TASA and len(audio):
            x = np.linspace(0, len(audio), int(len(audio) * TASA / tasa), endpoint=False)
            audio = np.interp(x, np.arange(len(audio)), audio).astype(np.float32)
        return audio if hablo else None

    def transcribir(self, audio: np.ndarray) -> str:
        self._listo.wait()
        segmentos, _ = self._modelo.transcribe(
            audio, language=self.cfg.get("idioma", "es"), beam_size=5,
            vad_filter=True, initial_prompt=PISTA, condition_on_previous_text=False)
        texto = " ".join(s.text.strip() for s in segmentos).strip()
        log.info("Escuché: %s", texto)
        return texto
