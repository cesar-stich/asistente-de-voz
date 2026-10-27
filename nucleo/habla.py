"""Voz del asistente (texto a voz de Windows, sin internet)."""
import queue
import threading

import pythoncom
import win32com.client

from .util import log

ASYNC_Y_CORTAR = 1 | 2  # SVSFlagsAsync | SVSFPurgeBeforeSpeak


class Habla:
    def __init__(self):
        self._cola: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._bucle, daemon=True, name="habla").start()

    def decir(self, texto: str) -> None:
        self._cola.put(texto)

    def callar(self) -> None:
        self._cola.put("")

    def _bucle(self):
        pythoncom.CoInitialize()
        voz = win32com.client.Dispatch("SAPI.SpVoice")
        for v in voz.GetVoices():
            nombre = v.GetDescription()
            if "Spanish" in nombre or "Sabina" in nombre or "Helena" in nombre:
                voz.Voice = v
                break
        voz.Rate = 1
        while True:
            texto = self._cola.get()
            try:
                voz.Speak(texto, ASYNC_Y_CORTAR)
            except Exception:
                log.exception("Error al hablar")
