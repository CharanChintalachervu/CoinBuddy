# Alerts

`coin-buddy watch` can notify you when the signal changes to BUY or SELL. Both channels are free.

## Sound (on by default)

| System | What you hear |
|---|---|
| Windows | A beep: high (1000 Hz) for BUY, low (500 Hz) for SELL. |
| macOS | A spoken "buy signal" or "sell signal". |
| Linux | The terminal bell. |

Turn it off in `config.yaml`:

```yaml
alerts:
  sound: false
```

## Discord (optional)

Get a message in a Discord channel, which works on your phone too.

1. In Discord, open **Server Settings → Integrations → Webhooks → New Webhook**.
2. Pick the channel, then click **Copy Webhook URL**.
3. Add it to your `.env` file:

    ```ini
    DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
    ```

4. Run `coin-buddy watch`.

Each alert contains the full explanation, the same text as `coin-buddy snapshot`.

!!! danger "The webhook URL is a secret"
    Anyone with the URL can post to your channel. Keep it in `.env`, never in `config.yaml` or the code. If it leaks, delete the webhook in Discord and create a new one.

## When alerts fire

- Only during `coin-buddy watch`. The dashboard doesn't alert.
- Only on a **change** to BUY or SELL: the first check that differs from the previous one.
- An alert that fails (no speaker, Discord down) is logged as a warning and never stops the watcher.
