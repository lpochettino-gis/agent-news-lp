# Agent News

Agente local para generar un resumen diario de noticias a las 08:30.

## Que hace

- Usa una lista fija de tematicas propias: Argentina, Petroleo, Gas, Litio, Drones, Equipamiento Topografico, Software SAAS, Inteligencia artificial, Novedades Tech, Ultimos Gadgets y Robots.
- Busca noticias publicas del dia por RSS de Google News usando esas tematicas.
- Selecciona 4 noticias por tematica, 44 noticias diarias en total.
- Resume cada tema en hasta 300 caracteres.
- Genera un unico HTML actualizado en `agent_news/output/agent_news_latest.html`.
- Abre automaticamente el HTML al terminar.
- Usa un perfil manual fijo, sin leer archivos, historial, cookies, passwords ni sesiones.

## Privacidad

El perfil es manual y queda guardado en `interest_profile.json`. No escanea la PC ni el historial del navegador.

Al buscar noticias, envia a Google News consultas construidas con las tematicas configuradas. No envia archivos, historial, cookies ni sesiones.

## Archivos

- `agent_news.py`: agente principal.
- `run_agent_news.cmd`: ejecutor diario.
- `install_agent_news_task.ps1`: registra la tarea programada de Windows `Agent News`.
- `uninstall_agent_news_task.ps1`: elimina la tarea programada.
- `output/agent_news_latest.html`: resumen unico actualizado.
- `logs/agent_news.log`: registro de ejecuciones.

## Uso manual

Generar un reporte de prueba sin internet:

```powershell
.\run_agent_news.cmd --offline-demo --no-open
```

Generar el reporte real sin abrirlo:

```powershell
.\run_agent_news.cmd --no-open
```

Ver o regenerar el perfil configurado:

```powershell
.\run_agent_news.cmd --profile-only
.\run_agent_news.cmd --profile-only --refresh-profile
```

## Programacion diaria

Registrar la tarea:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_agent_news_task.ps1
```

Eliminarla:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_agent_news_task.ps1
```
