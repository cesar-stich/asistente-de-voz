# 🎙️ Asistente de voz para Windows

Asistente de voz **local y gratuito** para Windows. Mantienes un atajo de teclado, hablas, sueltas, y lo hace: pone música en Spotify, abre videos en YouTube, maneja tu pomodoro, recordatorios, páginas, apps y más.

- **Sin costo por uso:** la voz y la IA corren en tu propia PC. No usa APIs de pago ni tokens.
- **Rápido:** unos 0,4 s para entender la voz (en GPU) y menos de 0,5 s para interpretar frases libres.
- **Sin voz de respuesta:** muestra un aviso flotante con el progreso (`⠋ Buscando en Spotify…`) y el resultado (`✅ Poniendo…`).

> Guía de uso con todos los comandos: [LEEME.md](LEEME.md)

---

## ✨ Funciones

| Área | Ejemplos de lo que puedes decir |
|---|---|
| 🍅 **Pomodoro** | "pon el pomodoro", "pon un pomodoro de 50", "¿cuánto falta?", "pausa el pomodoro", "pon un descanso largo", "¿cuántos pomodoros hice?" |
| 🎵 **Spotify Premium** | "pon *Despacito* de Luis Fonsi en Spotify", "ponme algo de Bad Bunny", "pon mi playlist de estudio", "ponme algo tranqui para estudiar", "me gusta esta canción", "activa el aleatorio" |
| ⏯️ **Controles de música** (Spotify, YouTube o lo que suene) | "pausa", "dale play", "siguiente", "la anterior", "sube el volumen", "volumen al 40", "silencio", "¿qué canción es esta?" |
| 📺 **YouTube** | "pon el resumen de Perú vs Ecuador en YouTube": busca el video y lo reproduce en Chrome |
| 🌐 **Web, apps y carpetas** | "abre Depor", "busca recetas de pollo", "abre Word", "cierra Spotify", "abre la carpeta descargas" |
| ⏰ **Recordatorios y notas** | "recuérdame en 20 minutos sacar la ropa", "recuérdame a las 3:30 de la tarde…", "pon una alarma de 10 minutos", "anota: comprar pan", "lee mis notas" |
| 🧠 **Texto copiado (IA local)** | copias un texto y dices "resume esto", "tradúcelo al inglés", "corrige esto", "explícame esto" |
| ⌨️ **Dictado** | "escribe hola, ¿cómo estás?": lo escribe donde está el cursor |
| 💻 **Sistema** | "toma una captura", "bloquea la PC", "apaga la PC en 30 minutos", "¿qué hora es?", "¿cuánta batería tengo?" |
| 📅 **Google** (opcional) | "¿qué tengo hoy?", "agenda una reunión mañana a las 3", "¿tengo correos nuevos?", "escríbele a Juan que llego tarde" (siempre muestra el borrador antes de enviar) |
| 💬 **Frases libres** | Si una frase no coincide con un comando fijo, la IA local la interpreta: "ya no quiero escuchar nada" → pausa; "quiero ver un tutorial de Excel" → YouTube |

---

## 🧩 Cómo funciona

```
 Atajo (mantener Ctrl+Alt+Espacio)
        │
        ▼
 🎙️ Micrófono ──► Whisper large-v3-turbo (GPU, local)  ──► texto
                                                            │
                         ┌──────────────────────────────────┤
                         ▼                                  ▼
            Reglas fijas en español (instantáneo)   ¿No coincide? → IA local (Ollama, qwen2.5:3b) → acción JSON
                         │                                  │
                         └───────────────┬──────────────────┘
                                         ▼
                Acciones: Spotify API · YouTube · Chrome · pomodoro · recordatorios ·
                          controles multimedia de Windows · volumen · Google Calendar/Gmail · …
                                         │
                                         ▼
                       Aviso flotante en pantalla (⠋ progreso → ✅ resultado)
```

### Estructura

```
asistente.py            Programa principal: atajos, bandeja, cola de órdenes, avisos
nucleo/
  voz.py                Grabación (mantener o tocar) + Whisper (GPU con respaldo en CPU)
  router.py             Reglas en español + interpretación con IA (ejemplos few-shot)
  acciones.py           Todo lo que sabe hacer (música, web, sistema, notas, IA, Google…)
  ia.py                 Cliente de Ollama
  spotify_ctl.py        Spotify Web API (PKCE, sin client secret) + búsqueda difusa de canciones
  google_ctl.py         Google Calendar y Gmail (OAuth de escritorio)
  pomodoro.py           Temporizador pomodoro con conteo diario
  ui.py                 Aviso flotante (sin robar el foco), cajita de texto, confirmación de correos
  habla.py              Voz de Windows (opcional, desactivada por defecto)
  util.py               Configuración, rutas y registro
config.example.yaml     Configuración de ejemplo (se copia a config.yaml la primera vez)
LEEME.md                Guía de uso completa y cómo conectar Spotify / Google
```

### Tecnologías

| Pieza | Tecnología |
|---|---|
| Voz a texto | [faster-whisper](https://github.com/SYSTRAN/faster-whisper), modelo `large-v3-turbo`, en CUDA (int8_float16); respaldo en CPU con `small` |
| IA local | [Ollama](https://ollama.com) con `qwen2.5:3b`, respuesta en formato JSON |
| Atajos globales | `keyboard` |
| Música | `spotipy` (Spotify Web API, flujo PKCE) |
| Control multimedia | Windows Media Session (`winrt`) y teclas multimedia |
| Volumen | `pycaw` |
| Google | `google-api-python-client`, `google-auth-oauthlib` |
| Interfaz | `tkinter` (aviso flotante) y `pystray` (ícono de bandeja) |

---

## 🛠️ Instalación

**Requisitos:** Windows 10/11, Python 3.13, [Ollama](https://ollama.com), micrófono. Recomendado: GPU NVIDIA con 6 GB o más (sin GPU funciona en CPU, más lento).

```bash
git clone https://github.com/cesar-stich/asistente-de-voz.git
```

```bash
ollama pull qwen2.5:3b
```

Luego:
1. Doble clic en **`instalar.bat`**: crea el entorno e instala dependencias.
2. Doble clic en **`iniciar.bat`**: aparece un ícono naranja junto al reloj. La primera vez descarga Whisper, unos 1,6 GB.
3. Opcional: **`inicio_automatico.bat`** para que arranque al prender la PC.
4. Edita **`config.yaml`** (se crea solo) con tus páginas, apps, carpetas y contactos.
5. Para conectar Spotify Premium y Google, sigue los pasos de [LEEME.md](LEEME.md#-conectar-spotify-premium-una-sola-vez-unos-5-minutos).

### Privacidad
Todo corre en tu PC. `config.yaml`, las claves de Spotify y Google, el registro y tus notas están en `.gitignore` y nunca se suben al repositorio.

---

## 🗺️ Hoja de ruta (próximas mejoras)

- [x] Pomodoro con avisos y conteo diario
- [x] Recordatorios por tiempo y por hora
- [x] Spotify Premium por voz
- [x] YouTube con reproducción automática
- [x] Reconocimiento en GPU y modo "mantener para hablar"
- [ ] **Conectar Gmail y Google Calendar** (el código ya existe en `google_ctl.py`: falta crear las credenciales y probarlo de punta a punta)
- [ ] **Control de configuración de Windows** (Wi-Fi, Bluetooth, modo avión, brillo, firewall…), siempre con confirmación en pantalla antes de cualquier cambio de seguridad
- [ ] **Modo "haz casi cualquier cosa"**: delegar órdenes complejas ("hazme un informe en Word con este PDF") a un asistente más potente
- [ ] **Integración con Gemini + Wispr Flow**: abrir Gemini y dictarle con Wispr Flow para preguntas generales
- [ ] Clima ("¿va a llover hoy en Lima?") con una API gratuita
- [ ] "Modo estudio": cerrar redes sociales durante el pomodoro
- [ ] Resumen al prender la PC: agenda, correos y clima
- [ ] Palabra de activación ("Oye asistente…") sin tener que usar el atajo
