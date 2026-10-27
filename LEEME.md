# 🎙️ Asistente de voz

**Mantén Ctrl + Alt + Espacio mientras hablas y suelta**: lo hace al instante. No gasta tokens de Claude: la voz (Whisper large-v3-turbo, en tu tarjeta gráfica) y la IA (Ollama qwen2.5) corren gratis en tu PC.

- **Mantener Ctrl + Alt + Espacio**: habla mientras lo mantienes; al soltar, lo ejecuta. Puedes hacer pausas sin que te corte.
- **Tocar Ctrl + Alt + Espacio** (sin mantener): habla y se detiene sola cuando te callas, o tócalo otra vez.
- No te responde con voz: abajo de la pantalla ves lo que está haciendo (⠋ Buscando en Spotify…) y luego el resultado (✅). Si prefieres que también hable, pon `responder_con_voz: true` en `config.yaml`.
- **Ctrl + Alt + T**: escribir la orden en una cajita, en vez de hablar.
- Icono naranja junto al reloj: clic derecho para ver el menú (configuración, notas, salir).
- Puedes empezar con "oye…". No hace falta decir las frases exactas: si no reconoce la frase, la IA local la interpreta.

## Cómo iniciarlo

| Archivo | Para qué |
|---|---|
| `iniciar.bat` | Abre el asistente (doble clic). |
| `inicio_automatico.bat` | Hace que arranque solo al prender la PC. |
| `instalar.bat` | Reinstala todo si mueves la carpeta o algo se rompe. |
| `config.yaml` | Tus páginas, apps, carpetas, contactos, atajos y tiempos del pomodoro. |

---

## Lo que puedes decir

### 🍅 Pomodoro
- "Pon el pomodoro" / "pon un pomodoro de 50 minutos"
- "Pausa el pomodoro" / "reanuda el pomodoro" / "para el pomodoro"
- "¿Cuánto falta?"
- "Pon un descanso" / "pon un descanso largo"
- "¿Cuántos pomodoros hice?"
- Al terminar, suena, te avisa y arranca el descanso solo. Cada 4 pomodoros el descanso es largo.
- Pasa el mouse por el icono de la bandeja para ver el tiempo que queda.

### 🎵 Música (Spotify)
- "Pon *Despacito* en Spotify" / "pon *Bohemian Rhapsody* de Queen en Spotify"
- "Ponme algo de Bad Bunny"
- "Pon mi playlist de estudio"
- "Ponme algo tranqui para estudiar" (lo decide la IA)
- "¿Qué canción es esta?" / "me gusta esta canción"
- "Activa el aleatorio" / "quita el aleatorio"

### ⏯️ Controles (sirven para Spotify, YouTube o lo que esté sonando)
- "Pausa" / "apaga la música" / "pausa el video"
- "Dale play" / "pon música" / "continúa"
- "Siguiente" / "la anterior"
- "Sube el volumen" / "baja el volumen" / "volumen al 40" / "silencio"

### 📺 YouTube (se abre y se reproduce en Chrome)
- "Pon el resumen de Perú vs Ecuador en YouTube"
- "Busca en YouTube lofi para estudiar"
- "Quiero ver un tutorial de Excel" (lo decide la IA)

### 🌐 Páginas, apps y carpetas
- "Abre Google" / "entra a Depor" / "abre WhatsApp" / "abre Gmail"
- "YouTube" (solo el nombre también funciona)
- "Busca recetas de pollo" / "busca noticias de Alianza Lima en Google"
- "Abre Word" / "abre Excel" / "abre la calculadora" / "cierra Spotify"
- "Abre la carpeta descargas"
- Si una página no está en tu lista, abre el primer resultado de búsqueda.
- Agrega tus páginas, apps y carpetas en `config.yaml`.

### ⏰ Recordatorios y notas
- "Recuérdame en 20 minutos sacar la ropa"
- "Recuérdame que tengo clase en media hora"
- "Recuérdame a las 3:30 de la tarde llamar a mi mamá"
- "Pon una alarma de 10 minutos"
- "Anota: comprar pan" / "lee mis notas" / "borra mis notas" (las anteriores se archivan, no se pierden)

### 🧠 Texto copiado (con la IA local)
Primero copia un texto con **Ctrl + C** y luego di:
- "Resume esto" / "tradúcelo al inglés" / "corrige esto" / "explícame esto"

El resultado aparece en una ventana y queda copiado para pegarlo con Ctrl + V.

### ⌨️ Dictado
- "Escribe hola, ¿cómo estás?": lo escribe donde tengas el cursor.

### 💻 PC
- "Toma una captura de pantalla" (se guarda en Imágenes › Capturas del asistente)
- "Bloquea la PC"
- "Apaga la PC en 30 minutos" / "cancela el apagado"
- "¿Qué hora es?" / "¿qué día es hoy?" / "¿cuánta batería tengo?"

### 💬 Preguntas
- "¿Cuánto es el 18 % de 350?" / "¿Cómo se dice ventana en inglés?"
- Responde la IA local. No tiene internet, así que no sabe noticias de hoy.

### 📅 Google (requiere conectarlo, mira más abajo)
- "¿Qué tengo hoy?" / "¿qué tengo mañana?" / "¿qué tengo esta semana?"
- "Agenda una reunión mañana a las 3 con el grupo"
- "¿Tengo correos nuevos?"
- "Escríbele a Juan que llego tarde": la IA redacta el correo y **te lo muestra para que lo revises; solo se envía si presionas Enviar**.

---

## 🔌 Conectar Spotify Premium (una sola vez, unos 5 minutos)

1. Entra a https://developer.spotify.com/dashboard e inicia sesión con tu cuenta de Spotify.
2. Clic en **Create app**:
   - App name: `Asistente de voz`
   - App description: `Control por voz`
   - Redirect URI: `http://127.0.0.1:8888/callback` (escríbela exactamente así y presiona **Add**)
   - Marca **Web API** y acepta los términos. Guarda.
3. Copia el **Client ID** que aparece en la app.
4. Abre `config.yaml` y pégalo en `client_id: "..."`, dentro de `spotify:`.
5. Clic derecho en el icono → **Recargar configuración**.
6. Di "pon *alguna canción* en Spotify". La primera vez se abre Chrome para que des permiso. Después ya no vuelve a pedirlo.

> Spotify tiene que estar abierto (en la PC o en el celular) para reproducir. Si está cerrado, el asistente abre la app de la PC.

## 🔌 Conectar Google: Calendar y Gmail (una sola vez, unos 10 minutos)

1. Entra a https://console.cloud.google.com/ y crea un proyecto: **Asistente de voz**.
2. En **APIs y servicios › Biblioteca**, activa **Google Calendar API** y **Gmail API**.
3. En **APIs y servicios › Pantalla de consentimiento de OAuth** (o "Google Auth Platform"):
   - Tipo **Externo**, nombre `Asistente de voz` y tu correo.
   - En **Usuarios de prueba** (Audience › Test users), agrega tu propio correo de Gmail.
4. En **Credenciales › Crear credenciales › ID de cliente de OAuth**, elige el tipo **App de escritorio**.
5. Descarga el JSON, renómbralo a `google_credentials.json` y ponlo en esta carpeta.
6. En `config.yaml`, cambia `activo: false` a `activo: true` dentro de `google:`. Agrega tus contactos en `contactos:` y tu nombre en `nombre:`.
7. Recarga la configuración y di "¿qué tengo hoy?". La primera vez Google te pide permiso en Chrome. Como la app es tuya y está en modo prueba, saldrá un aviso de "app no verificada": dale **Continuar**.

Las claves se guardan solo en esta carpeta (`datos/`). Nadie más las ve.

---

## Problemas comunes
- **No me escucha:** revisa que el micrófono predeterminado de Windows sea el correcto (Configuración › Sonido › Entrada).
- **Entiende mal:** mantén el atajo mientras hablas, y habla cerca del micrófono.
- **Va lento o la PC no tiene tarjeta NVIDIA:** en `config.yaml` pon `modelo_whisper: small`.
- **La IA tarda:** el asistente tarda unos 20 segundos en estar listo después de iniciar. Luego responde en menos de un segundo.
- **La IA se equivoca mucho:** en `config.yaml` puedes poner `modelo: gemma2`. Es más lista, pero más lenta y ocupa casi toda la tarjeta gráfica.
- **El atajo choca con otro programa:** cámbialo en `atajo_voz` del `config.yaml`.
- **Algo falla:** mira el archivo `datos/asistente.log`.
