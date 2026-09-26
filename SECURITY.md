# Security Notes

This repository intentionally excludes local runtime data:

- generated HTML reports in `output/`
- execution logs in `logs/`
- `interest_profile.json`
- compiled executables and ZIP packages
- backups, downloaded publisher images, audio archives and local environment files

The daily workflow uses public Google News RSS queries built from the fixed topic list, public Trends feeds, publisher article pages and their images. Publisher image fetching rejects non-public addresses, limits response sizes and timeouts, and checks that the article title matches before using its metadata. It does not use authenticated browser sessions.
Do not commit personal reports, local logs, credentials, tokens, cookies, or browser data.
