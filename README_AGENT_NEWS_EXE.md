# Agent News portable para Windows

Esta guía corresponde a un paquete compilado con `build_exe.ps1`. El repositorio contiene el código fuente; no incluye un ejecutable actualizado.

## Preparar el paquete

Con Python, PyInstaller y, opcionalmente, Pillow instalados, ejecutar:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

El script genera la carpeta hermana `agent_news_dist` y reemplaza su contenido anterior. El ejecutable incluye el módulo `news_images.py`; Pillow permite comprimir las imágenes.

## Instalar y ejecutar

1. Copiar la carpeta completa `agent_news_dist` a la PC destino.
2. Ejecutar `instalar_agent_news.cmd` para registrar la tarea diaria a las 08:30.
3. Ejecutar `AgentNews.exe` para generar y abrir el noticiario, o `AgentNews.exe --no-open` para generarlo sin abrir el navegador.

La PC debe estar encendida, con sesión iniciada e Internet para buscar noticias nuevas. `AgentNews.exe --offline-demo --no-open` permite probar el diseño sin conexión.

## Contenido

Siete secciones: Argentina, Energía y Recursos, Drones y Topografía, Software e IA, Tech y Hardware, Agro y Zona · Pasteur y región; más Trends. Hasta 56 noticias, con imágenes medianas del medio cuando están disponibles. La zona prioriza Pasteur, Lincoln, General Villegas y Pehuajó, con una cobertura editorial aproximada de 250 km.

La portada abre directamente en las noticias. No genera audio ni resumen ejecutivo. Los medios sin foto accesible se muestran con texto y enlace.

## Archivos locales

- `output/agent_news_latest.html`: noticiario.
- `output/images/`: imágenes descargadas.
- `output/image_cache.json`: referencias de las fotos.
- `interest_profile.json`: perfil manual de temas.
- `logs/agent_news.log`: registro de ejecución.

Si la carpeta del ejecutable no permite escritura, utiliza `%LOCALAPPDATA%\Agent News`. La ejecución no escanea archivos personales ni historial del navegador. Consulta fuentes públicas sin utilizar cookies, contraseñas o sesiones del navegador.

Para desinstalar la tarea programada, ejecutar `desinstalar_agent_news.cmd`.
