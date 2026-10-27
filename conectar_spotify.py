"""Conecta tu cuenta de Spotify una sola vez (abre Chrome para que des permiso)."""
from nucleo.spotify_ctl import Spotify
from nucleo.util import cargar_config

sp = Spotify(cargar_config())
print("CONECTADO COMO:", sp.probar(), flush=True)
print("DISPOSITIVOS:", [(d["name"], d["type"], d["is_active"]) for d in sp.sp.devices()["devices"]], flush=True)
