# Agent News

Noticiario local con imágenes, actualizado todos los días a las 08:30.

## Instalación desde GitHub

Requiere Python 3.10 o posterior. La tarea diaria se instala en Windows.

```powershell
git clone https://github.com/lpochettino-gis/agent-news-lp.git
cd agent-news-lp
python -m pip install Pillow
.\run_agent_news.cmd --no-open
```

Pillow es opcional: permite reducir y comprimir las fotos. Sin esa biblioteca, el agente utiliza solamente la biblioteca estándar de Python y conserva los formatos de imagen compatibles.

Para programarlo diariamente a las 08:30, ejecutar `instalar_agent_news.cmd`. Se necesita conexión para obtener noticias y fotografías; la PC debe estar encendida y con la sesión iniciada para abrir el noticiario automáticamente.

## Lectura

- Siete secciones: Argentina, Energía y Recursos, Drones y Topografía, Software e IA, Tech y Hardware, Agro y Zona · Pasteur y región. Hasta 8 noticias por sección, más Trends.
- Abre directamente en las noticias. No muestra resumen ejecutivo ni controles de audio; la ejecución diaria no genera guiones ni WAV.
- Cada noticia incluye título enlazado, fecha, fuente y una descripción breve cuando está disponible.
- Fotos de tamaño mediano (220 px de alto), sin recortar, con crédito al medio y enlace al artículo. En pantallas pequeñas se muestra una columna.
- Obtiene la foto de los metadatos de la nota y comprueba la coincidencia del título. Si falta una imagen, el medio bloquea el acceso o no coincide la nota, conserva la noticia sin foto.
- Guarda las imágenes en `output/images/` y sus referencias en `output/image_cache.json`. Las fotos guardadas se pueden ver sin conexión. La caché reutiliza resultados de hasta siete días y conserva un máximo de 400 referencias; los archivos descargados se conservan.
- Con Pillow disponible, reduce las fotos a un máximo de 800 × 500 y las comprime en JPEG. Sin Pillow conserva el formato original compatible. No requiere una API paga.

## Agro y zona

- Agro: agricultura, mercados, clima, ganadería, lechería, sanidad, insumos, maquinaria y agtech de Argentina. Últimas 24 horas.
- Zona: prioridad a Pasteur, Lincoln, General Villegas y Pehuajó. Amplía a localidades cercanas con una cobertura editorial aproximada de 250 km alrededor de Pasteur. Es una lista de localidades, no un filtro de distancia exacta ni de kilómetros por ruta.
- Las noticias locales pueden tener hasta 72 horas; se exige fecha y referencia territorial en el título o descripción. Los nombres ambiguos necesitan contexto local. El filtro textual puede omitir notas sin localidad explícita.
- Reserva representación de las localidades prioritarias y de los dos subtemas de agro cuando hay noticias disponibles. Los espacios pendientes no se cuentan como noticias.

## Privacidad

El perfil manual está en `interest_profile.json`. La ejecución consulta Google News, Trends, páginas públicas de los medios y sus imágenes. No escanea archivos ni historial y no envía archivos personales, cookies, contraseñas ni sesiones.

## Archivos

- `agent_news.py`: agente principal.
- `news_images.py`: resolución de notas, validación de imágenes y caché local.
- `run_agent_news.cmd`: ejecutor diario.
- `output/agent_news_latest.html`: noticiario actualizado.
- `output/images/`: fotos descargadas.
- `logs/agent_news.log`: registro de ejecuciones e imágenes no disponibles.

## Uso

Generar: `run_agent_news.cmd --no-open`.

Demostración sin conexión: `run_agent_news.cmd --offline-demo --no-open`.

Perfil: `run_agent_news.cmd --profile-only`; regenerar con `--refresh-profile`.

Pruebas: `python -B -m unittest discover -v`.

`--no-audio` se acepta por compatibilidad; el audio está desactivado siempre.

## Programación diaria

La tarea de Windows Agent News sigue ejecutando `run_agent_news.cmd` a las 08:30. Los cambios no modifican su horario. Para reinstalarla: `powershell -ExecutionPolicy Bypass -File .\install_agent_news_task.ps1`.
