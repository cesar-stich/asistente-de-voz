"""Convierte lo que dices en una acción: primero con frases conocidas (instantáneo),
y si no la reconoce, le pregunta a la IA local (Ollama)."""
import re
import unicodedata
from datetime import datetime

from .util import log


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos. Conserva la longitud para poder recortar el texto original."""
    salida = []
    for c in texto:
        base = "".join(x for x in unicodedata.normalize("NFD", c) if not unicodedata.combining(x))
        if len(base) != 1:
            base = c
        base = base.lower()
        salida.append(base if (base.isalnum() or base == ":") else " ")
    norm = "".join(salida)
    norm = re.sub(r"(?<!\d):|:(?!\d)", " ", norm)  # ":" solo se queda en horas (3:30)
    # Quita muletillas del inicio y del final ("oye", "por favor"...) sin mover posiciones.
    relleno = (r"oye|hey|ey|ok|okay|hola|asistente|claudio|claude|porfa|por favor|"
               r"puedes|podrias|me puedes|quiero que|necesito que|ayudame a")
    norm = re.sub(rf"^\s*(?:(?:{relleno})\s+)+", lambda m: " " * len(m.group(0)), norm)
    norm = re.sub(r"\s+(?:por favor|porfa|gracias)\s*$", lambda m: " " * len(m.group(0)), norm)
    return norm


def _compilar(patron: str) -> re.Pattern:
    patron = patron.replace(" ", r"\s+")
    patron = patron.replace("^", r"^\s*").replace("$", r"\s*$")
    return re.compile(patron)


UNIDADES = {"segundo": 1 / 60, "minuto": 1, "hora": 60}


def _minutos(n, unidad) -> float | None:
    from .util import a_numero
    partes = [a_numero(p) for p in re.split(r"\s+y\s+", n.strip())]
    if any(p is None for p in partes):
        return None
    total = sum(partes)
    return total * UNIDADES[unidad.rstrip("s")]


class Interprete:
    def __init__(self):
        self._orig = ""
        crudo = self._crudo
        R = []

        def regla(patron, constructor):
            R.append((_compilar(patron), constructor))

        # --- Asistente ---
        regla(r"^(que puedes hacer|ayuda|que comandos (hay|tienes)|comandos)$", lambda m: ("ayuda", {}))
        regla(r"^(cierra|apaga|sal del|salir del) (el )?asistente$", lambda m: ("salir", {}))

        # --- Recordatorios y temporizadores ---
        t_unidad = r"(?P<u>minutos?|horas?|segundos?)"
        t_num = r"(?P<n>\w+( y \w+)?)"
        regla(rf"^recuerdame en {t_num} {t_unidad}( que| a| de)? (?P<t>.+)$",
              lambda m: ("recordatorio", {"minutos": _minutos(m.group("n"), m.group("u")), "texto": crudo(m, "t")}))
        regla(rf"^recuerdame (que )?(?P<t>.+) en {t_num} {t_unidad}$",
              lambda m: ("recordatorio", {"minutos": _minutos(m.group("n"), m.group("u")), "texto": crudo(m, "t")}))
        regla(r"^recuerdame (a las|para las|a la) (?P<h>\d{1,2})(:(?P<mi>\d{2}))?( de la (?P<p>manana|tarde|noche))?( que| a| de)? (?P<t>.+)$",
              lambda m: ("recordatorio_hora", {"hora": int(m.group("h")), "minuto": int(m.group("mi") or 0),
                                               "periodo": m.group("p"), "texto": crudo(m, "t")}))
        regla(rf"(pon|crea|ponme|activa)( una| un)? (alarma|temporizador|timer)( de| en| para| por)? {t_num} {t_unidad}",
              lambda m: ("recordatorio", {"minutos": _minutos(m.group("n"), m.group("u")), "texto": "Se acabó el temporizador"}))

        # --- Notas ---
        regla(r"^(anota|apunta|toma nota|guarda (una|la) nota|anotame|apuntame|nota)( que| de que)? (?P<t>.+)$",
              lambda m: ("nota", {"texto": crudo(m, "t")}))
        regla(r"(lee|leeme|dime|muestra|abre|muestrame|ver)( mis| las)? notas", lambda m: ("notas_leer", {}))
        regla(r"(borra|limpia|elimina)( mis| las| todas las)? notas", lambda m: ("notas_borrar", {}))

        # --- Correo / calendario (Google) ---
        regla(r"^((escribele|mandale|enviale) |((manda|envia|escribe|redacta|mandar|enviar) (un |una )?(correo|mail|email|e mail)))",
              lambda m: ("correo_redactar", {"instruccion": self._orig}))
        regla(r"(correos|mails|emails) nuevos|(lee|leeme|revisa|ver|mira|dime) (mis |los )?(ultimos )?(correos|mails|emails|bandeja)|cuantos correos",
              lambda m: ("correo_leer", {}))
        regla(r"^(dime )?(que tengo|mi agenda|mis eventos|que hay en (mi|el) calendario|tengo algo)( para| en)?( el)?( (?P<dia>hoy|manana|esta semana|la semana))?",
              lambda m: ("agenda", {"dia": m.group("dia") or "hoy"}))
        regla(r"^((crea|agenda|agrega|anade|pon|programa|crear|agendar)( un| una| la| el)? (evento|reunion|cita)|(agenda|anota|pon|agrega)( en| al)? (mi|el) calendario)",
              lambda m: ("evento_crear", {"texto": self._orig}))

        # --- Pomodoro ---
        regla(r"(inicia|empieza|pon|arranca|comienza|activa|ponme|dale|iniciar|empezar)( el| un| otro)? pomodoro( de (?P<n>\w+)( minutos)?)?",
              lambda m: ("pomodoro", {"op": "iniciar", "minutos": m.group("n")}))
        regla(r"(pausa|pausar|pausale)( el)? pomodoro", lambda m: ("pomodoro", {"op": "pausar"}))
        regla(r"(reanuda|continua|sigue|retoma)( con)?( el)? pomodoro", lambda m: ("pomodoro", {"op": "reanudar"}))
        regla(r"(para|deten|detener|cancela|termina|quita|apaga|acaba|stop|parar)( el)? pomodoro", lambda m: ("pomodoro", {"op": "detener"}))
        regla(r"(cuanto|que tanto) (tiempo )?(falta|queda|me queda|me falta)|como va (el|mi) pomodoro",
              lambda m: ("pomodoro", {"op": "estado"}))
        regla(r"^(pon|inicia|empieza|toma|tomo|quiero|dame|ponme)( un| mi)? descanso( (?P<largo>largo))?",
              lambda m: ("pomodoro", {"op": "descanso", "largo": bool(m.group("largo"))}))
        regla(r"cuantos pomodoros", lambda m: ("pomodoro", {"op": "contar"}))

        # --- Texto copiado (IA local) ---
        regla(r"^(resume|resumeme|resumelo|resumir|haz un resumen|hazme un resumen)",
              lambda m: ("portapapeles", {"op": "resumir"}))
        regla(r"^traduc\w*( esto| lo que copie| el texto| lo copiado| lo)?( al| a)? (?P<i>ingles|espanol|portugues|frances|italiano|aleman|chino|japones|quechua)",
              lambda m: ("portapapeles", {"op": "traducir", "idioma": m.group("i")}))
        regla(r"^(corrige|corrigeme|corrigelo|mejora|mejorame|mejoralo|arregla|arreglame)",
              lambda m: ("portapapeles", {"op": "corregir"}))
        regla(r"^(explica|explicame|explicalo) (esto|lo que copie|el texto|lo copiado)",
              lambda m: ("portapapeles", {"op": "explicar"}))

        # --- Dictado ---
        regla(r"^(escribe|escribeme|dicta|teclea)( esto| lo siguiente)? (?P<t>.+)$",
              lambda m: ("dictar", {"texto": self._orig[m.start("t"):m.end("t")].strip()}))

        # --- YouTube ---
        regla(r"^(busca|pon|reproduce|abre|ponme)( en)? youtube (?P<q>.+)$",
              lambda m: ("youtube", {"consulta": m.group("q").strip()}))
        regla(r"^((pon|ponme|busca|buscame|reproduce|abre|quiero ver|muestrame|mira) )?(?P<q>.+) en youtube$",
              lambda m: ("youtube", {"consulta": m.group("q").strip()}))

        # --- Spotify ---
        regla(r"^((pon|ponme|reproduce|toca|busca|dale) )?(?P<q>.+) en spotify$",
              lambda m: ("spotify", {"consulta": crudo(m, "q"), "tipo": None}))
        regla(r"^(pon|ponme|reproduce|toca) (la de|la cancion|la cancion de|el tema|el tema de) (?P<q>.+)$",
              lambda m: ("spotify", {"consulta": crudo(m, "q"), "tipo": "cancion"}))
        regla(r"^(pon|ponme|reproduce|toca)( mi| la| una)? (playlist|lista)( de reproduccion)?( de)? (?P<q>.+)$",
              lambda m: ("spotify", {"consulta": m.group("q").strip(), "tipo": "playlist"}))
        regla(r"^(pon|ponme|reproduce|toca|quiero escuchar|quiero oir)( algo| musica| canciones| temas| la musica)( de| del) (?P<q>.+)$",
              lambda m: ("spotify", {"consulta": m.group("q").strip(), "tipo": "artista"}))
        regla(r"que (cancion|tema|musica) (es esta|es|suena|esta sonando|estoy escuchando)|como se llama (esta|la) cancion",
              lambda m: ("cancion_actual", {}))
        regla(r"(me gusta|guarda|dale like|dale me gusta|agrega a favoritos)( a)?( esta)? (cancion|tema)|^me gusta$",
              lambda m: ("me_gusta", {}))
        regla(r"(activa|pon)( el)? (aleatorio|shuffle|modo aleatorio)", lambda m: ("aleatorio", {"activar": True}))
        regla(r"(quita|desactiva|apaga)( el)? (aleatorio|shuffle|modo aleatorio)", lambda m: ("aleatorio", {"activar": False}))

        # --- Controles de música / video (Spotify, YouTube o lo que suene) ---
        regla(r"(pausa|pausar|pausale|deten|detener|para|apaga|quita|calla|stop|parar)( la| el| esta)? (musica|cancion|video|spotify|youtube|reproduccion|tema)",
              lambda m: ("media", {"op": "pausa"}))
        regla(r"^(pausa|pausalo|pausala|stop|para|detente|pausar)$", lambda m: ("media", {"op": "pausa"}))
        regla(r"^((pon|ponme|reproduce|dale|activa)( la| algo de)? musica|dale play|play|reanuda|reanudalo|reanudala|continua|sigue|quita la pausa|despausa|reproduce)( la musica| el video| la cancion)?$",
              lambda m: ("media", {"op": "play"}))
        regla(r"^((pon )?(la )?siguiente|pasa|salta|cambia|adelanta|next)( la| de| esta)?( cancion| tema| video)?$",
              lambda m: ("media", {"op": "siguiente"}))
        regla(r"^((pon )?(la )?anterior|regresa|vuelve|atras)( la| a la)?( cancion| tema| video)?( anterior)?$",
              lambda m: ("media", {"op": "anterior"}))
        regla(r"volumen (al|a|en) (?P<n>\d+)", lambda m: ("volumen", {"op": "fijar", "nivel": int(m.group("n"))}))
        regla(r"(sube|subele|aumenta|mas|subir)( el| al)? volumen|^subele$|mas fuerte|sube la musica",
              lambda m: ("volumen", {"op": "subir"}))
        regla(r"(baja|bajale|disminuye|menos|bajar)( el| al)? volumen|^bajale$|mas bajo|mas despacio|baja la musica",
              lambda m: ("volumen", {"op": "bajar"}))
        regla(r"^(silencio|silencia|mutea|mute|quita el sonido|sin sonido|activa el sonido|quita el silencio)( la pc| todo)?$",
              lambda m: ("volumen", {"op": "silencio"}))

        # --- Sistema ---
        regla(r"(toma|haz|saca|tomame|hazme)( una)? (captura|screenshot|foto de (la )?pantalla)|captura de pantalla",
              lambda m: ("captura", {}))
        regla(r"bloquea( la)? (pc|computadora|compu|laptop|pantalla|sesion)", lambda m: ("bloquear", {}))
        regla(rf"(apaga|apagar)( la)? (pc|computadora|compu|laptop|maquina)( en {t_num} (?P<u>minutos?|horas?))?",
              lambda m: ("apagar", {"minutos": _minutos(m.group("n"), m.group("u")) if m.group("n") else None}))
        regla(r"(cancela|anula)( el)? apagado|no apagues", lambda m: ("cancelar_apagado", {}))
        regla(r"que hora es|dime la hora", lambda m: ("hora", {}))
        regla(r"que (dia|fecha) es( hoy)?|a cuanto estamos|que dia estamos", lambda m: ("fecha", {}))
        regla(r"bateria", lambda m: ("bateria", {}))

        # --- Google ---
        regla(r"^(busca|buscame|googlea|investiga|buscar)( en google)? (?P<q>.+?)( en google)?$",
              lambda m: ("google", {"consulta": crudo(m, "q")}))

        # --- Abrir / cerrar ---
        regla(r"^(abre|abreme|entra a|entra en|entra al|ve a|vamos a|abrir|pon la pagina de|abre la pagina de|ir a|llevame a|abre la app|inicia)( la pagina de| la pagina| la carpeta| la app| el programa| la aplicacion)?( de)?( el| la| los| las| mi| mis)? (?P<o>.+)$",
              lambda m: ("abrir", {"objetivo": m.group("o").strip()}))
        regla(r"^(cierra|cerrar|cierrame)( el| la)?( programa| app| aplicacion| pestana de)? (?P<o>.+)$",
              lambda m: ("cerrar", {"objetivo": m.group("o").strip()}))

        # "pon <algo>" sin decir dónde: decide la IA (o el servicio por defecto)
        regla(r"^(pon|ponme|reproduce|toca) (?P<q>.+)$", lambda m: ("pon_algo", {"consulta": m.group("q").strip()}))

        self._reglas = R

    def _crudo(self, m: re.Match, grupo: str) -> str:
        """Devuelve el texto original (con tildes y mayúsculas) de un grupo capturado."""
        a, b = m.span(grupo)
        return self._orig[a:b].strip(" ,.;:¡!¿?")

    def interpretar(self, texto: str):
        self._orig = texto
        norm = normalizar(texto)
        if not norm.strip():
            return None
        for patron, constructor in self._reglas:
            m = patron.search(norm)
            if m:
                accion, args = constructor(m)
                log.info("Regla -> %s %s", accion, args)
                return accion, args
        return None


SISTEMA_IA = """Eres el intérprete de un asistente de voz en una PC con Windows (Perú). \
Convierte la orden del usuario en UNA acción JSON. Acciones posibles:
- spotify {consulta, tipo: cancion|artista|playlist}: ESCUCHAR música. Ambientes o géneros ("algo tranqui", "música para estudiar", "reggaetón") son tipo playlist.
- youtube {consulta}: VER videos (partidos, resúmenes, tutoriales, trailers).
- google {consulta}: buscar información o noticias actuales en internet.
- abrir {objetivo}: abrir una página, app o carpeta por su NOMBRE corto ("bcp", "word"). Nunca pongas una URL.
- cerrar {objetivo}: cerrar una app.
- media {op: play|pausa|siguiente|anterior}: controlar lo que está sonando. Dejar de escuchar = pausa.
- volumen {op: subir|bajar|silencio|fijar, nivel}
- pomodoro {op: iniciar|pausar|reanudar|detener|estado|descanso, minutos}
- recordatorio {minutos, texto}
- nota {texto}
- responder {texto}: cálculos, conversiones, significados de palabras, traducciones cortas y charla. Responde tú mismo en español, breve (máx. 2 oraciones).
IMPORTANTE: para hechos, deportes, personas, fechas, historia o noticias usa google: no inventes datos.

Ejemplos:
"ponme algo chill para relajarme" -> {"accion":"spotify","consulta":"chill relajante","tipo":"playlist"}
"quiero escuchar a karol g" -> {"accion":"spotify","consulta":"Karol G","tipo":"artista"}
"ponme la de tusa" -> {"accion":"spotify","consulta":"Tusa","tipo":"cancion"}
"ya no quiero oír música" -> {"accion":"media","op":"pausa"}
"esa no me gusta, otra" -> {"accion":"media","op":"siguiente"}
"está muy fuerte" -> {"accion":"volumen","op":"bajar"}
"pon los goles de la U" -> {"accion":"youtube","consulta":"goles Universitario"}
"cómo se hace una tabla dinámica" -> {"accion":"youtube","consulta":"cómo hacer tabla dinámica Excel"}
"llévame a la página de interbank" -> {"accion":"abrir","objetivo":"interbank"}
"qué pasó hoy con el dólar" -> {"accion":"google","consulta":"precio del dólar hoy Perú"}
"ponme la de vivir mi vida de marc anthony" -> {"accion":"spotify","consulta":"Vivir Mi Vida de Marc Anthony","tipo":"cancion"}
"cuánto es 15 por 12" -> {"accion":"responder","texto":"15 por 12 es 180."}
"cómo se dice ventana en inglés" -> {"accion":"responder","texto":"Se dice window."}
"quién ganó la copa américa 2021" -> {"accion":"google","consulta":"ganador Copa América 2021"}
Responde SOLO con el JSON."""

ACCIONES_IA = {"spotify", "youtube", "google", "abrir", "cerrar", "media", "volumen",
               "pomodoro", "recordatorio", "nota", "responder"}


def interpretar_con_ia(ia, texto: str):
    hoy = datetime.now().strftime("%A %d/%m/%Y %H:%M")
    datos = ia.chat_json(SISTEMA_IA, f"(Ahora: {hoy})\nOrden: {texto}")
    accion = datos.pop("accion", None)
    if accion not in ACCIONES_IA:
        return None
    for campo in ("consulta", "objetivo", "texto"):
        if campo in datos and not re.search(r"\w", str(datos[campo] or "")):
            return None  # la IA respondió algo vacío ("...")
    log.info("IA -> %s %s", accion, datos)
    return accion, datos
