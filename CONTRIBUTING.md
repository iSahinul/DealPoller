# Contributing to DealPoller

Thanks for considering it. This is a small project with a few firm
house rules - they exist because the tool handles a credential and
publishes to real channels.

## Ground rules

- **Token discipline:** the bot token is read from the
  `TELEGRAM_BOT_TOKEN` environment variable only. Any change that
  stores, logs or transmits a token anywhere else will be rejected.
- **No user-session mode.** Do not add Telethon/MTProto login support -
  the no-login design is the product's reason to exist.
- Standard library only.
- The watermark advances only after a successful send; failure stops
  the cycle. Behaviour changes here need a stated reason and tests.

## Getting set up

```bash
python3 -m unittest discover -s tests
POLLER_DRY_RUN=1 POLLER_ONCE=1 python3 poller.py   # parse-only smoke run
```

## Making a change

1. Open an issue first for anything bigger than a typo.
2. One topic per pull request; add or update tests when behaviour
   changes; make sure the full suite passes.
3. Never commit config.json, state.json, logs or any credential.
4. Update the README and CHANGELOG when behaviour changes.

## Reporting bugs

Use the bug-report issue form: what source channel shape, what the log
said, what you expected. Never paste a bot token into an issue.
