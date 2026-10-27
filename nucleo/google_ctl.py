"""Google Calendar y Gmail con tu cuenta (conexión única, las claves quedan en tu PC)."""
import base64
from datetime import datetime, timedelta
from email.mime.text import MIMEText

from .util import BASE, DATOS, log

PERMISOS = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
CREDENCIALES = BASE / "google_credentials.json"
TOKEN = DATOS / ".google_token.json"


class Google:
    def __init__(self, cfg: dict):
        self.activo = bool((cfg.get("google") or {}).get("activo"))
        self._cred = None

    def listo(self) -> str | None:
        """Devuelve un mensaje de error si falta configurar algo."""
        if not self.activo:
            return "Google no está activado. Mira el LEEME, sección Conectar Google."
        if not CREDENCIALES.exists():
            return "Falta el archivo google_credentials.json en la carpeta del asistente."
        return None

    def _credenciales(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        cred = self._cred
        if cred is None and TOKEN.exists():
            cred = Credentials.from_authorized_user_file(str(TOKEN), PERMISOS)
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        if not cred or not cred.valid:
            flujo = InstalledAppFlow.from_client_secrets_file(str(CREDENCIALES), PERMISOS)
            cred = flujo.run_local_server(port=0, open_browser=True)
        TOKEN.write_text(cred.to_json(), encoding="utf-8")
        self._cred = cred
        return cred

    def _servicio(self, nombre, version):
        from googleapiclient.discovery import build
        return build(nombre, version, credentials=self._credenciales(), cache_discovery=False)

    # --- Calendario ---
    def agenda(self, dia: str) -> str:
        ahora = datetime.now().astimezone()
        inicio = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
        if dia == "manana":
            inicio += timedelta(days=1)
            fin, nombre = inicio + timedelta(days=1), "mañana"
        elif "semana" in dia:
            fin, nombre = inicio + timedelta(days=7), "esta semana"
        else:
            inicio, fin, nombre = ahora, inicio + timedelta(days=1), "hoy"
        r = self._servicio("calendar", "v3").events().list(
            calendarId="primary", timeMin=inicio.isoformat(), timeMax=fin.isoformat(),
            singleEvents=True, orderBy="startTime", maxResults=10).execute()
        eventos = r.get("items", [])
        if not eventos:
            return f"No tienes nada {nombre}."
        partes = []
        for e in eventos:
            cuando = e["start"].get("dateTime")
            if cuando:
                t = datetime.fromisoformat(cuando)
                hora = t.strftime("%H:%M")
                if "semana" in dia:
                    hora = t.strftime("%d/%m ") + hora
            else:
                hora = "todo el día"
            partes.append(f"{hora}, {e.get('summary', 'sin título')}")
        return f"{nombre.capitalize()} tienes {len(eventos)}: " + "; ".join(partes) + "."

    def crear_evento(self, titulo: str, fecha: str, hora: str | None, duracion_min: int = 60) -> str:
        cal = self._servicio("calendar", "v3")
        if hora:
            inicio = datetime.fromisoformat(f"{fecha}T{hora}").astimezone()
            fin = inicio + timedelta(minutes=duracion_min or 60)
            cuerpo = {"summary": titulo, "start": {"dateTime": inicio.isoformat()},
                      "end": {"dateTime": fin.isoformat()}}
            cuando = inicio.strftime("%d/%m a las %H:%M")
        else:
            d = datetime.fromisoformat(fecha).date()
            cuerpo = {"summary": titulo, "start": {"date": d.isoformat()},
                      "end": {"date": (d + timedelta(days=1)).isoformat()}}
            cuando = d.strftime("%d/%m")
        cal.events().insert(calendarId="primary", body=cuerpo).execute()
        return f"Listo, agendé {titulo} el {cuando}."

    # --- Gmail ---
    def correos_no_leidos(self, maximo: int = 5) -> str:
        g = self._servicio("gmail", "v1")
        r = g.users().messages().list(userId="me", q="is:unread in:inbox", maxResults=maximo).execute()
        total = r.get("resultSizeEstimate", 0)
        mensajes = r.get("messages", [])
        if not mensajes:
            return "No tienes correos sin leer."
        partes = []
        for m in mensajes[:3]:
            d = g.users().messages().get(userId="me", id=m["id"], format="metadata",
                                         metadataHeaders=["From", "Subject"]).execute()
            h = {x["name"]: x["value"] for x in d["payload"]["headers"]}
            de = h.get("From", "").split("<")[0].strip().strip('"') or h.get("From", "")
            partes.append(f"de {de}: {h.get('Subject', 'sin asunto')}")
        return f"Tienes unos {total} sin leer. Los últimos: " + "; ".join(partes) + "."

    def enviar(self, para: str, asunto: str, cuerpo: str) -> str:
        msg = MIMEText(cuerpo, "plain", "utf-8")
        msg["to"], msg["subject"] = para, asunto
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        self._servicio("gmail", "v1").users().messages().send(userId="me", body={"raw": raw}).execute()
        log.info("Correo enviado a %s: %s", para, asunto)
        return f"Correo enviado a {para}."
