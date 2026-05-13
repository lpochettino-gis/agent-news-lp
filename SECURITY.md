# Security Notes

This repository intentionally excludes local runtime data:

- generated HTML reports in `output/`
- execution logs in `logs/`
- `interest_profile.json`
- compiled executables and ZIP packages

The agent uses public Google News RSS queries built from the fixed topic list.
Do not commit personal reports, local logs, credentials, tokens, cookies, or browser data.
