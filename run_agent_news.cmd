@echo off
setlocal
cd /d "%~dp0"

rem Avoid inherited dead local proxies causing every RSS feed to fail.
for %%V in (HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy GIT_HTTP_PROXY GIT_HTTPS_PROXY git_http_proxy git_https_proxy) do set "%%V="

where python >nul 2>nul
if %errorlevel%==0 (
  python -B "%~dp0agent_news.py" %*
) else (
  py -3 -B "%~dp0agent_news.py" %*
)

endlocal
