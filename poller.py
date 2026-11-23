#!/usr/bin/env python3
"""
Telegram channel mirror poller.

Polls the PUBLIC preview page of a Telegram channel
(https://t.me/s/<channel>) every N seconds, detects new posts, and
reposts each one to your own channel via the Bot HTTP API
(photo + caption).

No user account, no login, no session file: the preview page is public,
and the only credential is your bot token, read from the environment.
Your Telegram account is never touched.

Dedupe: state.json stores the highest source message id already posted.
First run seeds the state WITHOUT posting (no blast of old posts).

Config: config.json (copy config.example.json)
    {
      "channel": "@your-channel",
      "source": "https://t.me/s/source-channel",
      "poll_seconds": 90,
      "caption_limit": 1000
    }

Auth: TELEGRAM_BOT_TOKEN environment variable. The token is never
written to any file or log by this program.

Env:
    POLLER_DRY_RUN=1   parse + compose, do not send (testing)
    POLLER_ONCE=1      run a single poll cycle then exit (cron mode)

Limits
- The preview page shows ~20 latest posts; a burst of more than 20 new
  posts inside one poll interval would skip the oldest. At 90s polling
  this is unlikely.
- You can only mirror as fast as the source posts.
"""
import html as htmlmod
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parent
CONFIG_FILE = Path(os.environ.get("POLLER_CONFIG", BASE / "config.json"))
STATE_FILE = BASE / "state.json"
LOG_FILE = BASE / "poller.log"

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "ChannelPoller/1.0 (contact: channel admin)"}
DRY_RUN = os.environ.get("POLLER_DRY_RUN") == "1"
ONCE = os.environ.get("POLLER_ONCE") == "1"


def now_str():
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def log(msg):
    line = f"[{now_str()}] {msg}"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass
    if sys.stdout.isatty():
        print(line, flush=True)


def load_config():
    cfg = json.loads(CONFIG_FILE.read_text())
    channel = cfg.get("channel", "")
    if not channel or channel == "@PASTE_CHANNEL_HERE":
        sys.exit("channel not configured (config.json -> channel)")
    if not cfg.get("source"):
        sys.exit("source not configured (config.json -> source)")
    return channel, cfg


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (OSError, ValueError):
            pass
    return {"last_msg_id": 0}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state))


# Void elements never get an end tag in HTML, so they must not move the
# depth counter - a plain <br> (not <br/>) inside a caption would
# otherwise drift the depth and silently eat the whole message.
VOID_TAGS = {"br", "img", "hr", "meta", "link", "input", "source", "wbr"}


class PreviewPageParser(HTMLParser):
    """Extracts (msg_id, caption_html, photo_url) from a t.me/s/ page."""

    def __init__(self):
        super().__init__()
        self.messages = []
        self._cur = None
        self._depth = 0
        self._msg_depth = None
        self._text_depth = None
        self._text_parts = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID_TAGS:
            self._depth += 1
        attrs = dict(attrs)
        cls = attrs.get("class", "")
        if tag == "div" and "tgme_widget_message" in cls and "data-post" in attrs:
            m = re.search(r"/(\d+)$", attrs["data-post"])
            if m:
                self._cur = {"id": int(m.group(1)), "html": "", "photo": None}
                self._msg_depth = self._depth
        if self._cur is not None:
            if tag == "div" and "tgme_widget_message_text" in cls:
                self._text_depth = self._depth
                self._text_parts = []
            elif self._text_depth is not None:
                self._text_parts.append(self.get_starttag_text())
            if tag == "a" and "tgme_widget_message_photo_wrap" in cls:
                style = attrs.get("style", "")
                m = re.search(r"url\('([^']+)'\)", style)
                if m:
                    self._cur["photo"] = m.group(1)

    def handle_endtag(self, tag):
        if self._text_depth is not None:
            if tag == "div" and self._depth == self._text_depth:
                self._cur["html"] = "".join(self._text_parts)
                self._text_depth = None
            else:
                self._text_parts.append(f"</{tag}>")
        if self._cur is not None and tag == "div" and self._depth == self._msg_depth:
            self.messages.append(self._cur)
            self._cur = None
            self._msg_depth = None
        if tag not in VOID_TAGS:
            self._depth -= 1

    def handle_data(self, data):
        if self._text_depth is not None:
            self._text_parts.append(data)


ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "s", "strike", "del",
                "code", "pre", "a"}


def to_telegram_html(raw):
    """Convert t.me message HTML to the Telegram Bot API HTML subset."""
    raw = htmlmod.unescape(raw)
    raw = raw.replace("<strong", "<b").replace("</strong>", "</b>")
    raw = raw.replace("<em", "<i").replace("</em>", "</i>")
    raw = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)

    out = []
    i = 0
    for m in re.finditer(r"<[^>]+>", raw):
        out.append(htmlmod.escape(raw[i:m.start()]))
        tag = m.group(0)
        tm = re.match(r"</?([a-zA-Z0-9]+)", tag)
        name = tm.group(1).lower() if tm else ""
        if name in ALLOWED_TAGS:
            if name == "a":
                hm = re.search(r'href="([^"]+)"', tag)
                if tag.startswith("</"):
                    out.append("</a>")
                elif hm:
                    href = htmlmod.escape(hm.group(1), quote=True)
                    out.append(f'<a href="{href}">')
            else:
                out.append(f"</{name}>" if tag.startswith("</") else f"<{name}>")
        i = m.end()
    out.append(htmlmod.escape(raw[i:]))
    text = "".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_first_link(raw_html):
    """First external http(s) link in the message, if any."""
    m = re.search(r'href="(https?://[^"]+)"', raw_html)
    return m.group(1) if m else None


def fetch_source(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(4 * (i + 1))
    raise last


def bot_url(method):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set - export your bot token first "
            "(create a bot with @BotFather). It is never stored in a file.")
    return f"https://api.telegram.org/bot{token}/{method}"


def _try_send(url, data, tries=3, timeout=30):
    """POST to a Bot API URL; return (ok, detail). Retries transients and
    surfaces Telegram's own error description on failure."""
    last_err = None
    if isinstance(data, tuple):
        raw, ctype = data
        payload, headers = raw, {"Content-Type": ctype}
    else:
        payload = urllib.parse.urlencode(data).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                res = json.loads(r.read().decode())
            if res.get("ok"):
                return True, f"message_id {res['result']['message_id']}"
            last_err = res
        except Exception as e:  # noqa: BLE001
            try:
                body = e.read().decode() if hasattr(e, "read") else ""
            except Exception:  # noqa: BLE001
                body = ""
            last_err = f"{e} :: {body[:300]}" if body else e
        time.sleep(3 * (i + 1))
    return False, str(last_err)


def _download_bytes(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = (r.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip()
        return r.read(), ctype


def _multipart_photo_payload(fields, filename, file_bytes, content_type):
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
        body += str(value).encode("utf-8") + b"\r\n"
    body += f"--{boundary}\r\n".encode()
    body += (f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'
             f"Content-Type: {content_type}\r\n\r\n").encode()
    body += file_bytes + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def telegram_send(channel, text, photo_url=None, tries=3):
    if DRY_RUN:
        return True, "DRY-RUN: composed, not sent"
    if not photo_url:
        data = {"chat_id": channel, "text": text, "parse_mode": "HTML"}
        return _try_send(bot_url("sendMessage"), data, tries=tries)
    # Photo path. Telegram's servers sometimes cannot fetch preview-CDN
    # image URLs (400 "failed to get HTTP URL content") even though the
    # URL is valid. Fall back to downloading the image ourselves and
    # re-uploading it as a file, which always works.
    photo_api = bot_url("sendPhoto")
    data = {"chat_id": channel, "photo": photo_url,
            "caption": text, "parse_mode": "HTML"}
    ok, detail = _try_send(photo_api, data, tries=tries)
    if ok:
        return True, detail
    if "failed to get HTTP URL content" not in str(detail):
        return False, detail
    try:
        img, ctype = _download_bytes(photo_url)
    except Exception as e:  # noqa: BLE001
        log(f"photo download failed ({e}); posting text-only fallback")
        tdata = {"chat_id": channel, "text": text, "parse_mode": "HTML"}
        ok2, d2 = _try_send(bot_url("sendMessage"), tdata, tries=tries)
        return ok2, f"text-only fallback: {d2}"
    ext = {"image/jpeg": "jpg", "image/png": "png",
           "image/webp": "webp"}.get(ctype, "jpg")
    fields = {"chat_id": channel, "caption": text, "parse_mode": "HTML"}
    payload, ctype_hdr = _multipart_photo_payload(fields, f"post.{ext}", img, ctype)
    ok2, d2 = _try_send(photo_api, (payload, ctype_hdr), tries=tries, timeout=60)
    return ok2, f"upload fallback: {d2}" if ok2 else d2


def poll_cycle(channel, cfg):
    page = fetch_source(cfg["source"])
    parser = PreviewPageParser()
    parser.feed(page)
    msgs = sorted(parser.messages, key=lambda m: m["id"])
    if not msgs:
        log("WARN: no messages parsed from source page")
        return
    state = load_state()
    last = state.get("last_msg_id", 0)
    if last == 0:
        # First run: seed state, don't blast old posts.
        state["last_msg_id"] = msgs[-1]["id"]
        save_state(state)
        log(f"seeded state at msg {msgs[-1]['id']} "
            f"({len(msgs)} existing posts skipped)")
        return
    new = [m for m in msgs if m["id"] > last]
    if not new:
        log(f"no new posts (latest seen {msgs[-1]['id']})")
        return
    limit = cfg.get("caption_limit", 1000)
    for m in new:
        caption = to_telegram_html(m["html"])
        link = extract_first_link(m["html"])
        if len(caption) > limit:
            caption = caption[: limit - 60].rsplit("\n", 1)[0].strip() + "\n…"
            if link and link not in caption:
                caption += f"\n👉 <a href=\"{link}\">View</a>"
        ok, detail = telegram_send(channel, caption, m["photo"])
        log(f"post msg {m['id']}: {'OK' if ok else 'FAIL'} ({detail}) "
            f"photo={'yes' if m['photo'] else 'no'}")
        if ok:
            state["last_msg_id"] = m["id"]
            save_state(state)
        else:
            break  # stop on failure; retry next cycle
        time.sleep(2)  # gentle pacing between posts


def main():
    try:
        channel, cfg = load_config()
    except SystemExit as e:
        log(f"config error: {e}")
        raise
    poll_seconds = int(cfg.get("poll_seconds", 90))
    log(f"poller started -> {channel} (every {poll_seconds}s"
        f"{', DRY-RUN' if DRY_RUN else ''})")
    while True:
        try:
            poll_cycle(channel, cfg)
        except SystemExit:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"ERROR in poll cycle: {e}")
        if ONCE:
            break
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
