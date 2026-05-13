# Agent News para otra PC

Esta carpeta contiene el ejecutable portable de Agent News.

## Instalar

1. Copiar la carpeta completa `agent_news_dist` a la PC destino.
2. Ejecutar `instalar_agent_news.cmd`.
3. Windows registra la tarea programada `Agent News` para todos los dias a las 08:30.

El resumen se abre automaticamente al terminar, siempre que la PC este encendida, con sesion iniciada e internet disponible.

## Uso manual

Ejecutar:

```powershell
.\AgentNews.exe
```

Probar sin abrir navegador:

```powershell
.\AgentNews.exe --no-open
```

Regenerar perfil configurado:

```powershell
.\AgentNews.exe --refresh-profile
```

## Tematicas configuradas

Agent News usa una lista fija de tematicas propias:

- Argentina
- Petroleo
- Gas
- Litio
- Drones
- Equipamiento Topografico
- Software SAAS
- Inteligencia artificial
- Novedades Tech
- Ultimos Gadgets
- Robots

Busca 4 noticias por tematica, 44 noticias diarias en total.

No escanea archivos, historial, cookies, passwords, tokens ni sesiones. El perfil queda guardado localmente en `interest_profile.json` junto al ejecutable. Si esa carpeta no permite escritura, usa `%LOCALAPPDATA%\Agent News`.

Al buscar noticias, envia a Google News consultas construidas con las tematicas configuradas. No envia archivos, historial, cookies ni sesiones.

## Archivos generados

- `output/agent_news_latest.html`: resumen unico actualizado.
- `logs/agent_news.log`: registro de ejecuciones.
- `interest_profile.json`: tematicas configuradas.

## Desinstalar

Ejecutar:

```powershell
.\desinstalar_agent_news.cmd
```
