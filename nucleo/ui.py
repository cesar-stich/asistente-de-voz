"""Ventanitas del asistente (todo corre en el hilo principal de Tk)."""
import ctypes
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext

FONDO, TEXTO, ACENTO = "#1f1f24", "#f2f2f2", "#d97757"
FUENTE = ("Segoe UI", 11)

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW, WS_EX_TOPMOST = 0x08000000, 0x00000080, 0x00000008


class UI:
    def __init__(self, al_enviar_texto):
        self.root = tk.Tk()
        self.root.withdraw()
        self._pendientes: queue.Queue = queue.Queue()
        self._al_enviar_texto = al_enviar_texto
        self._ocultar_id = None
        self._giro_id = None
        self._texto_giro = None
        self._paso = 0
        self._crear_aviso()
        self.root.after(50, self._atender)

    # --- puente entre hilos ---
    def _atender(self):
        while not self._pendientes.empty():
            fn, resultado, listo = self._pendientes.get()
            try:
                resultado.append(fn())
            except Exception as e:  # noqa: BLE001
                resultado.append(e)
            listo.set()
        self.root.after(50, self._atender)

    def llamar(self, fn, esperar=True):
        """Ejecuta fn en el hilo de la interfaz. Si esperar=True, devuelve su resultado."""
        resultado, listo = [], threading.Event()
        self._pendientes.put((fn, resultado, listo))
        if not esperar:
            return None
        listo.wait()
        r = resultado[0]
        if isinstance(r, Exception):
            raise r
        return r

    def bucle(self):
        self.root.mainloop()

    def salir(self):
        self.llamar(self.root.quit, esperar=False)

    # --- aviso flotante (no roba el foco de la ventana donde estás) ---
    def _crear_aviso(self):
        w = self.aviso = tk.Toplevel(self.root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.attributes("-alpha", 0.94)
        w.configure(bg=FONDO)
        self._etiqueta = tk.Label(w, text="", bg=FONDO, fg=TEXTO, font=("Segoe UI", 12),
                                  padx=18, pady=10, wraplength=520, justify="left")
        self._etiqueta.pack()
        w.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(w.winfo_id()) or w.winfo_id()
        estilo = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                            estilo | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
        w.geometry("+-3000+-3000")

    GIRO = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def _girar(self):
        if self._texto_giro is None:
            return
        self._paso = (self._paso + 1) % len(self.GIRO)
        self._etiqueta.config(text=f"{self.GIRO[self._paso]}  {self._texto_giro}")
        self._giro_id = self.root.after(90, self._girar)

    def avisar(self, texto: str, segundos: float | None = 4, girando: bool = False):
        """Muestra un aviso abajo al centro. girando=True: animación de 'trabajando…' hasta el siguiente aviso."""
        def _mostrar():
            if getattr(self, "_giro_id", None):
                self.root.after_cancel(self._giro_id)
                self._giro_id = None
            self._texto_giro, self._paso = (texto, 0) if girando else (None, 0)
            self._etiqueta.config(text=f"{self.GIRO[0]}  {texto}" if girando else texto)
            if girando:
                self._giro_id = self.root.after(90, self._girar)
            self.aviso.update_idletasks()
            ancho, alto = self.aviso.winfo_reqwidth(), self.aviso.winfo_reqheight()
            x = (self.root.winfo_screenwidth() - ancho) // 2
            y = self.root.winfo_screenheight() - alto - 90
            self.aviso.geometry(f"+{x}+{y}")
            self.aviso.lift()
            if self._ocultar_id:
                self.root.after_cancel(self._ocultar_id)
                self._ocultar_id = None
            if segundos:
                self._ocultar_id = self.root.after(int(segundos * 1000), self._esconder)
        self.llamar(_mostrar, esperar=False)

    def _esconder(self):
        self._ocultar_id = None
        self._texto_giro = None
        self.aviso.geometry("+-3000+-3000")

    # --- cajita para escribir una orden ---
    def pedir_texto(self):
        def _abrir():
            w = tk.Toplevel(self.root)
            w.title("Asistente")
            w.configure(bg=FONDO)
            w.attributes("-topmost", True)
            w.resizable(False, False)
            tk.Label(w, text="¿Qué hago?", bg=FONDO, fg=TEXTO, font=FUENTE).pack(anchor="w", padx=14, pady=(12, 4))
            e = tk.Entry(w, width=52, font=("Segoe UI", 12), bg="#2b2b31", fg=TEXTO,
                         insertbackground=TEXTO, relief="flat")
            e.pack(padx=14, pady=(0, 14), ipady=6)

            def enviar(_=None):
                texto = e.get().strip()
                w.destroy()
                if texto:
                    self._al_enviar_texto(texto)

            e.bind("<Return>", enviar)
            w.bind("<Escape>", lambda _: w.destroy())
            w.update_idletasks()
            x = (w.winfo_screenwidth() - w.winfo_reqwidth()) // 2
            w.geometry(f"+{x}+{w.winfo_screenheight() // 3}")
            w.lift()
            w.focus_force()
            e.focus_set()
        self.llamar(_abrir, esperar=False)

    # --- confirmar un correo antes de enviarlo ---
    def confirmar_correo(self, para: str, asunto: str, cuerpo: str):
        """Muestra el borrador editable. Devuelve (para, asunto, cuerpo) o None si cancelas."""
        respuesta, listo = [], threading.Event()

        def _abrir():
            w = tk.Toplevel(self.root)
            w.title("Revisa el correo antes de enviarlo")
            w.configure(bg=FONDO, padx=14, pady=12)
            w.attributes("-topmost", True)
            campos = {}
            for fila, (nombre, valor) in enumerate((("Para", para), ("Asunto", asunto))):
                tk.Label(w, text=nombre, bg=FONDO, fg=TEXTO, font=FUENTE).grid(row=fila, column=0, sticky="w", pady=3)
                e = tk.Entry(w, width=60, font=FUENTE, bg="#2b2b31", fg=TEXTO, insertbackground=TEXTO, relief="flat")
                e.insert(0, valor)
                e.grid(row=fila, column=1, sticky="we", pady=3, ipady=4)
                campos[nombre] = e
            t = scrolledtext.ScrolledText(w, width=70, height=12, font=FUENTE, bg="#2b2b31", fg=TEXTO,
                                          insertbackground=TEXTO, relief="flat", wrap="word")
            t.insert("1.0", cuerpo)
            t.grid(row=2, column=0, columnspan=2, pady=8)
            botones = tk.Frame(w, bg=FONDO)
            botones.grid(row=3, column=0, columnspan=2, sticky="e")

            def cerrar(valor):
                respuesta.append(valor)
                w.destroy()
                listo.set()

            tk.Button(botones, text="Cancelar", font=FUENTE, relief="flat", padx=12,
                      command=lambda: cerrar(None)).pack(side="left", padx=6)
            tk.Button(botones, text="Enviar", font=FUENTE, relief="flat", padx=16, bg=ACENTO, fg="white",
                      command=lambda: cerrar((campos["Para"].get().strip(), campos["Asunto"].get().strip(),
                                              t.get("1.0", "end").strip()))).pack(side="left")
            w.protocol("WM_DELETE_WINDOW", lambda: cerrar(None))
            w.lift()
            w.focus_force()

        self.llamar(_abrir, esperar=False)
        listo.wait()
        return respuesta[0]

    # --- mostrar un texto largo (resúmenes, traducciones) ---
    def mostrar_texto(self, titulo: str, texto: str):
        def _abrir():
            w = tk.Toplevel(self.root)
            w.title(titulo)
            w.configure(bg=FONDO, padx=12, pady=12)
            w.attributes("-topmost", True)
            t = scrolledtext.ScrolledText(w, width=80, height=18, font=FUENTE, bg="#2b2b31", fg=TEXTO,
                                          insertbackground=TEXTO, relief="flat", wrap="word")
            t.insert("1.0", texto)
            t.pack(fill="both", expand=True)
            tk.Label(w, text="(También está copiado: pégalo con Ctrl+V)", bg=FONDO, fg="#a0a0a8",
                     font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))
            w.lift()
            w.focus_force()
        self.llamar(_abrir, esperar=False)
