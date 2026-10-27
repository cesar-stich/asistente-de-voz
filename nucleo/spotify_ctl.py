"""Control de Spotify Premium por la API oficial (conexión única con tu cuenta)."""
import difflib
import os
import re
import time
import unicodedata
import urllib.parse

from .util import DATOS, log

def _simple(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\(.*?\)|\[.*?\]|- .*$", " ", texto)  # quita "(Remastered)", "- En Vivo"...
    return " ".join(re.sub(r"[^\w\s]", "", texto).split())


def _limpiar(consulta: str) -> str:
    """Quita muletillas que se cuelan al hablar: "y qué pasó…", "la canción…"."""
    c = consulta.strip(" ¿?¡!.,")
    c = re.sub(r"^(?:y|e|la canci[oó]n|el tema|la de|una canci[oó]n|canci[oó]n)\s+", "", c, flags=re.I)
    return c.strip()


def _parecido(a: str, b: str, parcial: bool = False) -> float:
    if not a or not b:
        return 0.0
    base = difflib.SequenceMatcher(None, a, b).ratio()
    palabras_b = set(b.split())
    cubiertas = len(palabras_b & set(a.split())) / max(1, len(palabras_b))
    return max(base, cubiertas) if parcial else (base + cubiertas) / 2


PERMISOS = ("user-read-playback-state user-modify-playback-state user-read-currently-playing "
            "playlist-read-private playlist-read-collaborative user-library-modify")


class Spotify:
    def __init__(self, cfg: dict):
        c = cfg.get("spotify") or {}
        self.client_id = (c.get("client_id") or "").strip()
        self.redirect = c.get("redirect_uri", "http://127.0.0.1:8888/callback")
        self._sp = None

    @property
    def conectado(self) -> bool:
        return bool(self.client_id)

    @property
    def sp(self):
        if self._sp is None:
            import spotipy
            from spotipy.oauth2 import SpotifyPKCE
            auth = SpotifyPKCE(client_id=self.client_id, redirect_uri=self.redirect, scope=PERMISOS,
                               cache_path=str(DATOS / ".spotify_token"), open_browser=True)
            self._sp = spotipy.Spotify(auth_manager=auth, requests_timeout=10)
        return self._sp

    # --- dispositivo ---
    def _dispositivo(self) -> str | None:
        """Devuelve el id de un dispositivo; si Spotify está cerrado, lo abre y espera."""
        disp = self.sp.devices().get("devices", [])
        if any(d.get("is_active") for d in disp):
            return None  # usa el activo
        if not disp:
            os.startfile("spotify:")
            for _ in range(20):
                time.sleep(1)
                disp = self.sp.devices().get("devices", [])
                if disp:
                    break
        if not disp:
            raise RuntimeError("No encuentro Spotify abierto en ningún dispositivo.")
        pc = [d for d in disp if d.get("type") == "Computer"]
        return (pc or disp)[0]["id"]

    # --- reproducir ---
    def reproducir(self, consulta: str, tipo: str | None = None) -> str:
        if not self.conectado:
            os.startfile("spotify:search:" + urllib.parse.quote(consulta))
            return f"Abrí Spotify buscando {consulta}. Para que suene solo, conecta tu cuenta (mira el LEEME)."
        texto = consulta.lower()
        if tipo is None:
            for palabra in ("playlist ", "lista ", "mi playlist ", "la playlist "):
                if texto.startswith(palabra):
                    tipo, consulta = "playlist", consulta[len(palabra):]
            if texto.startswith(("algo de ", "musica de ", "canciones de ")):
                tipo, consulta = "artista", consulta.split(" de ", 1)[1]
        tipo = tipo or "cancion"
        dispositivo = self._dispositivo()

        if tipo == "playlist":
            uri, nombre = self._buscar_playlist(consulta)
            if not uri:
                return f"No encontré la playlist {consulta}."
            self.sp.start_playback(device_id=dispositivo, context_uri=uri)
            return f"Poniendo la playlist {nombre}."

        if tipo == "artista":
            r = self.sp.search(q=consulta, type="artist", limit=1)["artists"]["items"]
            if not r:
                return f"No encontré al artista {consulta}."
            self.sp.shuffle(True, device_id=dispositivo)
            self.sp.start_playback(device_id=dispositivo, context_uri=r[0]["uri"])
            return f"Poniendo música de {r[0]['name']}."

        pista = self._buscar_cancion(consulta)
        if not pista:
            return f"No encontré la canción {consulta}."
        # La canción y después sigue con su álbum, para que no se quede en silencio.
        try:
            self.sp.start_playback(device_id=dispositivo, context_uri=pista["album"]["uri"],
                                   offset={"uri": pista["uri"]})
        except Exception:
            self.sp.start_playback(device_id=dispositivo, uris=[pista["uri"]])
        return f"Poniendo {pista['name']} de {pista['artists'][0]['name']}."

    def _buscar_cancion(self, consulta: str):
        """Busca de varias formas y se queda con el resultado que más se parece a lo que dijiste."""
        consulta = _limpiar(consulta)
        cancion, artista = consulta, ""
        if " de " in consulta:  # "qué pasó de pedro ambrosio"
            cancion, artista = consulta.rsplit(" de ", 1)
        busquedas = [consulta]
        if artista:
            busquedas = [f"track:{cancion} artist:{artista}", f"{cancion} {artista}", consulta]
        candidatos = {}
        for q in busquedas:
            try:
                for t in self.sp.search(q=q, type="track", limit=10, market="PE")["tracks"]["items"]:
                    if t:
                        candidatos[t["id"]] = t
            except Exception:
                log.exception("Búsqueda Spotify %s", q)
        if not candidatos:
            return None

        def puntaje(t):
            nombre = _simple(t["name"])
            artistas = " ".join(_simple(a["name"]) for a in t.get("artists", []))
            if artista:
                p = 0.6 * _parecido(nombre, _simple(cancion)) + 0.4 * _parecido(artistas, _simple(artista))
            else:
                p = _parecido(f"{nombre} {artistas}", _simple(consulta), parcial=True)
            return p + t.get("popularity", 0) / 1000
        mejor = max(candidatos.values(), key=puntaje)
        log.info("Spotify eligió %s - %s (%.2f)", mejor["name"], mejor["artists"][0]["name"], puntaje(mejor))
        return mejor

    def _buscar_playlist(self, consulta: str):
        buscado = consulta.lower().strip()
        resultados = self.sp.current_user_playlists(limit=50)
        while resultados:
            for p in resultados["items"]:
                if p and buscado in (p.get("name") or "").lower():
                    return p["uri"], p["name"]
            resultados = self.sp.next(resultados) if resultados.get("next") else None
        r = self.sp.search(q=consulta, type="playlist", limit=5)["playlists"]["items"]
        r = [p for p in r if p]
        return (r[0]["uri"], r[0]["name"]) if r else (None, None)

    # --- controles ---
    def control(self, op: str) -> bool:
        """Pausa/play/siguiente/anterior. Devuelve False si Spotify no está sonando en ningún lado."""
        actual = self.sp.current_playback()
        if not actual:
            return False
        if op == "pausa":
            if actual.get("is_playing"):
                self.sp.pause_playback()
        elif op == "play":
            if not actual.get("is_playing"):
                self.sp.start_playback()
        elif op == "siguiente":
            self.sp.next_track()
        elif op == "anterior":
            self.sp.previous_track()
        return True

    def actual(self) -> str | None:
        a = self.sp.current_playback()
        if not a or not a.get("item"):
            return None
        it = a["item"]
        artistas = ", ".join(x["name"] for x in it.get("artists", []))
        return f"Suena {it['name']} de {artistas}."

    def me_gusta(self) -> str:
        a = self.sp.current_playback()
        if not a or not a.get("item"):
            return "No está sonando nada en Spotify."
        self.sp.current_user_saved_tracks_add([a["item"]["id"]])
        return f"Guardé {a['item']['name']} en tus me gusta."

    def aleatorio(self, activar: bool) -> str:
        self.sp.shuffle(activar)
        return "Aleatorio activado." if activar else "Aleatorio desactivado."

    def probar(self) -> str:
        yo = self.sp.current_user()
        log.info("Spotify conectado como %s", yo.get("display_name"))
        return yo.get("display_name") or yo.get("id")
