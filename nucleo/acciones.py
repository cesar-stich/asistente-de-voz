"""Todo lo que el asistente sabe hacer. Cada acción recibe (ctx, args) y devuelve lo que dirá."""
import asyncio
import ctypes
import os
import re
import subprocess
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

import pyperclip
import requests

from .router import normalizar
from .util import NOTAS, a_numero, log

# ---------------------------------------------------------------- utilidades


def abrir_url(ctx, url: str) -> None:
    chrome = ctx.cfg.get("chrome")
    if chrome and Path(chrome).exists():
        subprocess.Popen([chrome, url])
    else:
        os.startfile(url)


def _buscar_en(diccionario: dict, objetivo: str):
    """Busca 'objetivo' en las claves del diccionario, sin importar tildes ni mayúsculas."""
    obj = normalizar(objetivo).strip()
    obj = re.sub(r"\s+", " ", obj)
    claves = {re.sub(r"\s+", " ", normalizar(k).strip()): k for k in diccionario}
    if obj in claves:
        return diccionario[claves[obj]]
    for k_norm, k in claves.items():  # "la pagina de depor" -> depor
        if re.search(rf"\b{re.escape(k_norm)}\b", obj):
            return diccionario[k]
    return None


# ------------------------------------------------------------ música/video

VK = {"play": 0xB3, "pausa": 0xB3, "siguiente": 0xB0, "anterior": 0xB1,
      "subir": 0xAF, "bajar": 0xAE, "silencio": 0xAD}


def tecla_multimedia(nombre: str, veces: int = 1) -> None:
    for _ in range(veces):
        ctypes.windll.user32.keybd_event(VK[nombre], 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK[nombre], 0, 2, 0)


def _sesion_media():
    """Lo que está sonando en Windows (Spotify, YouTube en Chrome, etc.)."""
    try:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
    except ImportError:
        return None

    async def obtener():
        m = await M.request_async()
        return m.get_current_session()
    return asyncio.run(obtener())


def _media_windows(op: str) -> bool:
    s = _sesion_media()
    if not s:
        return False
    sonando = s.get_playback_info().playback_status == 4  # PLAYING

    async def hacer():
        if op == "pausa" and sonando:
            await s.try_pause_async()
        elif op == "play" and not sonando:
            await s.try_play_async()
        elif op == "siguiente":
            await s.try_skip_next_async()
        elif op == "anterior":
            await s.try_skip_previous_async()
    asyncio.run(hacer())
    return True


def media(ctx, a):
    op = a.get("op", "pausa")
    if not _media_windows(op):
        if ctx.spotify.conectado and op == "play":
            try:
                if not ctx.spotify.control("play"):
                    ctx.spotify.sp.start_playback(device_id=ctx.spotify._dispositivo())
                return "Dale play."
            except Exception:
                log.exception("Spotify play")
        if op in ("pausa", "siguiente", "anterior"):
            tecla_multimedia(op)
        else:
            os.startfile("spotify:")
            time.sleep(4)
            tecla_multimedia("play")
    return {"pausa": "Pausado.", "play": "Dale play.", "siguiente": "Siguiente.", "anterior": "Anterior."}.get(op)


def _volumen_ep():
    from pycaw.pycaw import AudioUtilities
    altavoces = AudioUtilities.GetSpeakers()
    if hasattr(altavoces, "EndpointVolume"):
        return altavoces.EndpointVolume
    from ctypes import POINTER, cast
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioEndpointVolume
    interfaz = altavoces.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(interfaz, POINTER(IAudioEndpointVolume))


def volumen(ctx, a):
    op = a.get("op")
    try:
        ep = _volumen_ep()
        actual = round(ep.GetMasterVolumeLevelScalar() * 100)
        if op == "silencio":
            mudo = not ep.GetMute()
            ep.SetMute(mudo, None)
            return None if mudo else "Sonido activado."
        nuevo = {"subir": actual + 15, "bajar": actual - 15}.get(op, a.get("nivel", actual))
        nuevo = max(0, min(100, int(nuevo)))
        ep.SetMute(False, None)
        ep.SetMasterVolumeLevelScalar(nuevo / 100, None)
        return f"Volumen al {nuevo}."
    except Exception:
        log.exception("pycaw")
        tecla_multimedia(op if op in VK else "subir", 1 if op == "silencio" else 5)
        return None


def youtube(ctx, a):
    consulta = a.get("consulta", "")
    try:
        r = requests.get("https://www.youtube.com/results", params={"search_query": consulta},
                         headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "es-PE,es;q=0.9"},
                         cookies={"CONSENT": "YES+"}, timeout=8)
        m = re.search(r'"videoRenderer":\{"videoId":"([\w-]{11})"', r.text) or \
            re.search(r'"videoId":"([\w-]{11})"', r.text)
    except requests.RequestException:
        m = None
    if m:
        abrir_url(ctx, f"https://www.youtube.com/watch?v={m.group(1)}")
        return f"Poniendo {consulta} en YouTube."
    abrir_url(ctx, "https://www.youtube.com/results?search_query=" + urllib.parse.quote(consulta))
    return f"Te dejo los resultados de {consulta} en YouTube."


def spotify(ctx, a):
    return ctx.spotify.reproducir(a.get("consulta", ""), a.get("tipo"))


def pon_algo(ctx, a):
    """'pon <algo>' sin decir dónde: la IA decide si es música o video."""
    consulta = a["consulta"]
    if ctx.ia.disponible():
        from .router import interpretar_con_ia
        r = interpretar_con_ia(ctx.ia, "pon " + consulta)
        if r and r[0] in ("spotify", "youtube"):
            return ACCIONES[r[0]](ctx, r[1])
    if ctx.cfg.get("musica_por_defecto", "spotify") == "youtube":
        return youtube(ctx, {"consulta": consulta})
    return spotify(ctx, {"consulta": consulta, "tipo": None})


def cancion_actual(ctx, a):
    if ctx.spotify.conectado:
        try:
            r = ctx.spotify.actual()
            if r:
                return r
        except Exception:
            log.exception("spotify actual")
    s = _sesion_media()
    if s:
        async def props():
            return await s.try_get_media_properties_async()
        p = asyncio.run(props())
        if p and p.title:
            return f"Suena {p.title}" + (f" de {p.artist}." if p.artist else ".")
    return "No está sonando nada."


def me_gusta(ctx, a):
    if not ctx.spotify.conectado:
        return "Para eso conecta tu cuenta de Spotify (mira el LEEME)."
    return ctx.spotify.me_gusta()


def aleatorio(ctx, a):
    if not ctx.spotify.conectado:
        return "Para eso conecta tu cuenta de Spotify (mira el LEEME)."
    return ctx.spotify.aleatorio(a.get("activar", True))


# ------------------------------------------------------------ web y apps

def google(ctx, a):
    abrir_url(ctx, "https://www.google.com/search?q=" + urllib.parse.quote(a.get("consulta", "")))
    return f"Buscando {a.get('consulta', '')}."


def abrir(ctx, a):
    objetivo = a.get("objetivo", "").strip()
    url = _buscar_en(ctx.cfg["sitios"], objetivo)
    if url:
        abrir_url(ctx, url)
        return f"Abriendo {objetivo}."
    app = _buscar_en(ctx.cfg["apps"], objetivo)
    if app:
        comando = app["abrir"] if isinstance(app, dict) else app
        try:
            os.startfile(comando)
        except OSError:
            subprocess.Popen(comando, shell=True)
        return f"Abriendo {objetivo}."
    carpeta = _buscar_en(ctx.cfg["carpetas"], objetivo.replace("carpeta", ""))
    if carpeta:
        os.startfile(carpeta)
        return f"Abriendo la carpeta {objetivo}."
    if re.match(r"^[\w-]+(\.[\w-]+)+$", objetivo.replace(" punto ", ".").replace(" ", "")):
        abrir_url(ctx, "https://" + objetivo.replace(" punto ", ".").replace(" ", ""))
        return f"Abriendo {objetivo}."
    # Página desconocida: abre el primer resultado (búsqueda "voy a tener suerte" de DuckDuckGo).
    abrir_url(ctx, "https://duckduckgo.com/?q=" + urllib.parse.quote("! " + objetivo))
    return f"Abriendo {objetivo}."


def cerrar(ctx, a):
    objetivo = a.get("objetivo", "").strip()
    app = _buscar_en(ctx.cfg["apps"], objetivo)
    proceso = app.get("proceso") if isinstance(app, dict) else None
    if not proceso:
        proceso = re.sub(r"\s+", "", normalizar(objetivo).strip()) + ".exe"
    r = subprocess.run(["taskkill", "/IM", proceso], capture_output=True, text=True)
    if r.returncode != 0:
        r = subprocess.run(["taskkill", "/IM", proceso, "/F"], capture_output=True, text=True)
    return f"Cerré {objetivo}." if r.returncode == 0 else f"No encontré {objetivo} abierto."


# ------------------------------------------------------------ sistema

def captura(ctx, a):
    from PIL import ImageGrab
    carpeta = Path.home() / "Pictures" / "Capturas del asistente"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / datetime.now().strftime("captura_%Y-%m-%d_%H-%M-%S.png")
    ctx.ui.avisar("📸", 0.1)
    time.sleep(0.3)
    ImageGrab.grab(all_screens=True).save(ruta)
    return "Captura guardada en Imágenes, Capturas del asistente."


def bloquear(ctx, a):
    ctypes.windll.user32.LockWorkStation()


def apagar(ctx, a):
    minutos = a.get("minutos") or 1
    subprocess.run(["shutdown", "/s", "/t", str(int(minutos * 60))])
    return f"La PC se apagará en {int(minutos)} minuto{'s' if minutos != 1 else ''}. Si te arrepientes, di: cancela el apagado."


def cancelar_apagado(ctx, a):
    r = subprocess.run(["shutdown", "/a"], capture_output=True)
    return "Apagado cancelado." if r.returncode == 0 else "No había ningún apagado programado."


DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def hora(ctx, a):
    return f"Son las {datetime.now().strftime('%H:%M')}."


def fecha(ctx, a):
    h = datetime.now()
    return f"Hoy es {DIAS[h.weekday()]} {h.day} de {MESES[h.month - 1]}."


def bateria(ctx, a):
    import psutil
    b = psutil.sensors_battery()
    if not b:
        return "No encuentro la batería."
    return f"Batería al {round(b.percent)} por ciento{', cargando' if b.power_plugged else ''}."


# ------------------------------------------------------------ recordatorios y notas

def recordatorio(ctx, a):
    minutos = a_numero(str(a.get("minutos"))) if a.get("minutos") is not None else None
    if not minutos:
        return "No entendí en cuánto tiempo te lo recuerdo."
    texto = a.get("texto") or "Tu recordatorio"
    cuando = datetime.now() + timedelta(minutes=minutos)
    ctx.recordatorios.agregar(cuando, texto)
    if minutos < 1:
        return f"Te aviso en {round(minutos * 60)} segundos."
    if minutos >= 60:
        h, m = divmod(round(minutos), 60)
        return f"Te lo recuerdo en {h} hora{'s' if h > 1 else ''}{f' y {m} minutos' if m else ''}."
    return f"Te lo recuerdo en {round(minutos)} minuto{'s' if round(minutos) != 1 else ''}."


def recordatorio_hora(ctx, a):
    ahora = datetime.now()
    h, m = a["hora"], a.get("minuto", 0)
    if a.get("periodo") in ("tarde", "noche") and h < 12:
        h += 12
    cuando = ahora.replace(hour=h % 24, minute=m, second=0, microsecond=0)
    if cuando <= ahora and not a.get("periodo") and h < 12:
        cuando += timedelta(hours=12)  # "a las 3" ya pasó en la mañana -> 3 de la tarde
    if cuando <= ahora:
        cuando += timedelta(days=1)
    ctx.recordatorios.agregar(cuando, a.get("texto") or "Tu recordatorio")
    return f"Listo, te lo recuerdo a las {cuando.strftime('%H:%M')}."


def nota(ctx, a):
    texto = a.get("texto", "").strip()
    if not texto:
        return "¿Qué anoto?"
    nuevo = not NOTAS.exists()
    with open(NOTAS, "a", encoding="utf-8") as f:
        if nuevo:
            f.write("# Mis notas\n\n")
        f.write(f"- [{datetime.now().strftime('%d/%m %H:%M')}] {texto}\n")
    return "Anotado."


def notas_leer(ctx, a):
    if not NOTAS.exists():
        return "No tienes notas todavía."
    lineas = [l[2:] for l in NOTAS.read_text(encoding="utf-8").splitlines() if l.startswith("- ")]
    if not lineas:
        return "No tienes notas todavía."
    os.startfile(NOTAS)
    ultimas = [re.sub(r"^\[[^\]]+\]\s*", "", l) for l in lineas[-5:]]
    return f"Tienes {len(lineas)} notas. Las últimas: " + "; ".join(ultimas) + "."


def notas_borrar(ctx, a):
    if NOTAS.exists():
        archivo = NOTAS.with_name(f"notas_archivadas_{datetime.now():%Y-%m-%d_%H-%M}.md")
        NOTAS.rename(archivo)
    return "Listo, empecé una lista de notas nueva. Las anteriores quedaron archivadas en la carpeta."


# ------------------------------------------------------------ texto e IA local

def dictar(ctx, a):
    import keyboard
    anterior = pyperclip.paste()
    pyperclip.copy(a.get("texto", ""))
    time.sleep(0.1)
    keyboard.send("ctrl+v")
    time.sleep(0.4)
    pyperclip.copy(anterior)


INSTRUCCIONES_TEXTO = {
    "resumir": "Resume el siguiente texto en español, claro y breve, con viñetas si ayuda.",
    "corregir": "Corrige la ortografía, gramática y redacción del texto, manteniendo su idioma y tono. Devuelve solo el texto corregido.",
    "explicar": "Explica el siguiente texto en español de forma sencilla, como a un estudiante.",
}


def portapapeles(ctx, a):
    texto = (pyperclip.paste() or "").strip()
    if not texto:
        return "Primero copia un texto con Ctrl+C y luego pídemelo."
    if not ctx.ia.disponible():
        return "La IA local (Ollama) no está encendida."
    op = a.get("op")
    if op == "traducir":
        sistema = f"Traduce el texto al {a.get('idioma', 'ingles')}. Devuelve solo la traducción."
    else:
        sistema = INSTRUCCIONES_TEXTO[op]
    resultado = ctx.ia.chat(sistema, texto[:12000])
    pyperclip.copy(resultado)
    ctx.ui.mostrar_texto({"resumir": "Resumen", "traducir": "Traducción", "corregir": "Texto corregido",
                          "explicar": "Explicación"}[op], resultado)
    return "Listo, te lo dejé copiado."


def responder(ctx, a):
    return a.get("texto") or "No sé qué responder a eso."


# ------------------------------------------------------------ Google

def _google(ctx):
    error = ctx.google.listo()
    if error:
        raise AvisoUsuario(error)
    return ctx.google


class AvisoUsuario(Exception):
    """Error que se le dice tal cual al usuario."""


def agenda(ctx, a):
    return _google(ctx).agenda(a.get("dia", "hoy"))


def correo_leer(ctx, a):
    return _google(ctx).correos_no_leidos()


def evento_crear(ctx, a):
    g = _google(ctx)
    if not ctx.ia.disponible():
        return "Necesito la IA local (Ollama) encendida para entender la fecha."
    hoy = datetime.now()
    datos = ctx.ia.chat_json(
        "Extrae un evento de calendario de la orden. Responde JSON: "
        '{"titulo": "...", "fecha": "YYYY-MM-DD", "hora": "HH:MM o null", "duracion_min": 60}. '
        f"Hoy es {DIAS[hoy.weekday()]} {hoy:%Y-%m-%d} y son las {hoy:%H:%M}. "
        "'mañana' es el día siguiente; 'el viernes' es el próximo viernes; '3 de la tarde' es 15:00.",
        a.get("texto", ""))
    if not datos.get("fecha") or not datos.get("titulo"):
        return "No entendí bien la fecha o el nombre del evento."
    hora_ev = datos.get("hora") if datos.get("hora") not in (None, "null", "") else None
    return g.crear_evento(datos["titulo"], datos["fecha"], hora_ev, int(datos.get("duracion_min") or 60))


def correo_redactar(ctx, a):
    g = _google(ctx)
    if not ctx.ia.disponible():
        return "Necesito la IA local (Ollama) encendida para redactar el correo."
    firma = ctx.cfg.get("nombre") or ""
    datos = ctx.ia.chat_json(
        "Redacta un correo a partir de la orden del usuario (en español, tono natural y educado"
        + (f", firmado como '{firma}'" if firma else ", sin firma") + "). Responde JSON: "
        '{"para": "nombre o correo del destinatario", "asunto": "...", "cuerpo": "..."}',
        a.get("instruccion", ""))
    para = (datos.get("para") or "").strip()
    if "@" not in para:
        para = _buscar_en(ctx.cfg["contactos"], para) or para
    ctx.ui.avisar("📧 Revisa el correo y dale Enviar si está bien.", 5)
    final = ctx.ui.confirmar_correo(para, datos.get("asunto", ""), datos.get("cuerpo", ""))
    if not final:
        return "Correo cancelado."
    para, asunto, cuerpo = final
    if "@" not in para:
        return "Ese destinatario no es un correo válido. Agrégalo en contactos del config.yaml."
    return g.enviar(para, asunto, cuerpo)


# ------------------------------------------------------------ asistente

def ayuda(ctx, a):
    from .util import BASE
    os.startfile(BASE / "LEEME.md")
    return ("Puedo poner música en Spotify o YouTube, pausar, cambiar canción y volumen; "
            "manejar tu pomodoro; abrir páginas y apps; buscar en Google; recordatorios y notas; "
            "resumir o traducir lo que copies; y revisar tu calendario y correo. Te abrí la lista completa.")


def pomodoro(ctx, a):
    return ctx.pomodoro.ejecutar(a.get("op", "iniciar"), a.get("minutos"), a.get("largo", False))


def salir(ctx, a):
    ctx.salir()


PROGRESO = {
    "spotify": lambda a: f"🎵 Buscando en Spotify: {a.get('consulta', '')}",
    "pon_algo": lambda a: f"🔎 Buscando: {a.get('consulta', '')}",
    "youtube": lambda a: f"📺 Buscando en YouTube: {a.get('consulta', '')}",
    "google": lambda a: f"🌐 Buscando en Google: {a.get('consulta', '')}",
    "abrir": lambda a: f"🚀 Abriendo {a.get('objetivo', '')}",
    "cerrar": lambda a: f"✖️ Cerrando {a.get('objetivo', '')}",
    "media": lambda a: "⏯️ Controlando la música",
    "cancion_actual": lambda a: "🎵 Viendo qué suena",
    "portapapeles": lambda a: "🧠 Procesando el texto copiado",
    "agenda": lambda a: "📅 Revisando tu calendario",
    "evento_crear": lambda a: "📅 Agendando",
    "correo_leer": lambda a: "📧 Revisando tu correo",
    "correo_redactar": lambda a: "✍️ Redactando el correo",
    "captura": lambda a: "📸 Capturando",
}


def progreso(accion: str, args: dict) -> str:
    return PROGRESO.get(accion, lambda a: "Haciéndolo…")(args)


ACCIONES = {
    "media": media, "volumen": volumen, "youtube": youtube, "spotify": spotify, "pon_algo": pon_algo,
    "cancion_actual": cancion_actual, "me_gusta": me_gusta, "aleatorio": aleatorio,
    "google": google, "abrir": abrir, "cerrar": cerrar,
    "captura": captura, "bloquear": bloquear, "apagar": apagar, "cancelar_apagado": cancelar_apagado,
    "hora": hora, "fecha": fecha, "bateria": bateria,
    "recordatorio": recordatorio, "recordatorio_hora": recordatorio_hora,
    "nota": nota, "notas_leer": notas_leer, "notas_borrar": notas_borrar,
    "dictar": dictar, "portapapeles": portapapeles, "responder": responder,
    "agenda": agenda, "correo_leer": correo_leer, "evento_crear": evento_crear, "correo_redactar": correo_redactar,
    "ayuda": ayuda, "pomodoro": pomodoro, "salir": salir,
}
