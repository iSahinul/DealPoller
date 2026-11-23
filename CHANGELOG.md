# Changelog

All notable changes to DealPoller are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions use
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-23

First public release.

- Preview-page polling of any public channel (t.me/s/<channel>) - no login, no session
- Bot API reposting with photo support and a download/re-upload fallback for CDN-refused images
- Watermark dedupe in state.json; first run seeds without posting
- Telegram-safe HTML cleaning, caption truncation that never loses the post's link
- Depth-safe parser (a plain <br> cannot silently eat a message)
- Agent Skill (`skill/SKILL.md`) and `AGENTS.md` included
