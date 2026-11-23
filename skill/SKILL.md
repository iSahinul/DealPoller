---
name: dealpoller
description: Use when setting up or operating DealPoller — mirroring a public Telegram channel into another channel with a bot. Enforces the safety rules: the bot token lives only in an environment variable, the first run seeds state without posting, and a failed send stops the cycle instead of skipping.
---

# DealPoller

Polls a public channel's preview page (`https://t.me/s/<channel>`) and
reposts new posts to a target channel via the Bot API. One file
(`poller.py`), Python standard library only. No user account, no login,
no session file — that is the point of the design.

## Safety rules (never break these)

- **The bot token comes from the `TELEGRAM_BOT_TOKEN` environment
  variable only.** Never write it into config.json, code, a log, or this
  chat. Never ask the user to paste it into the conversation — tell them
  to export it in their own terminal.
- **config.json, state.json and logs stay out of git.** They are in
  `.gitignore`; keep them there.
- **First run seeds silently.** With no state file, the poller records
  the newest existing post and mirrors nothing. Never delete state.json
  to "start over" without warning the user that old posts will be
  treated as already seen only if state is seeded again — and never
  force a re-post of history.
- **A failed send stops the cycle.** The watermark advances only after a
  successful send. Do not skip a failed post to "keep things moving";
  a gap is better than a silent hole, and the next cycle retries it.

## Setup

1. The user creates a bot via @BotFather and adds it as admin of the
   target channel. (Only the user can do this.)
2. Copy `config.example.json` to `config.json`; set `channel` (target)
   and `source` (`https://t.me/s/<source-name>`). Source must be a
   PUBLIC channel — preview pages do not exist for private ones.
3. Dry run first, always:
   `POLLER_DRY_RUN=1 POLLER_ONCE=1 python3 poller.py`
   Show the user what was parsed before any real run.
4. Real run: `python3 poller.py` (loops every `poll_seconds`), or
   `POLLER_ONCE=1` under cron.

## Operating notes

- `state.json` holds `last_msg_id` — the dedupe watermark.
- Photos: if Telegram refuses the preview-CDN URL, the poller downloads
  and re-uploads automatically; a dead image degrades to text-only
  rather than blocking the queue. This is expected behaviour, not an
  error to fix.
- Captions longer than `caption_limit` are truncated at a line break
  and the post's first link is re-attached so it is never lost.
- Poll politely: 90 seconds is the default and is plenty. Do not lower
  it aggressively.
