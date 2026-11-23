# AGENTS.md — DealPoller

A Telegram channel mirror poller (Python, standard library only).
Reads a public channel's preview page and reposts new posts to a target
channel via the Bot API. No user account, no session file.

## Working in this repo
- Run tests: `python3 -m unittest discover -s tests`
- Dry run: `POLLER_DRY_RUN=1 POLLER_ONCE=1 python3 poller.py`
- The user-facing skill lives in `skill/SKILL.md` — read it before
  changing send or state behaviour.

## House rules
- **Token discipline:** the bot token is read from `TELEGRAM_BOT_TOKEN`
  only. Never accept, print, log or commit a token value.
- `config.json`, `state.json`, `*.log` and `*.session` never enter git.
- The watermark advances only after a successful send; a failure stops
  the cycle. Do not "fix" this into skip-on-error.
- No third-party dependencies — in particular, do not add a Telethon /
  user-session mode to this repo. The no-login design is the product.
