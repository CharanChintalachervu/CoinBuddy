# Copyright (c) 2025-2026 Charan Chintalachervu. All rights reserved. See LICENSE.
"""Alerts: a local sound, plus an optional free Discord webhook."""

from __future__ import annotations

import logging
import os
import platform
import subprocess

import requests

from coin_buddy.config import AlertConfig

log = logging.getLogger(__name__)


def play_sound(action: str) -> None:
    if action not in ("BUY", "SELL"):
        return
    try:
        system = platform.system()
        if system == "Windows":
            import winsound

            winsound.Beep(1000 if action == "BUY" else 500, 400)
        elif system == "Darwin":
            subprocess.run(["say", f"{action.lower()} signal"], check=False)
        else:
            print("\a", end="", flush=True)
    except Exception as exc:  # noqa: BLE001 - an alert must never crash the app
        log.warning("Sound alert failed: %s", exc)


def send_discord(message: str, webhook_url: str) -> None:
    try:
        requests.post(webhook_url, json={"content": message[:1900]}, timeout=10).raise_for_status()
    except requests.RequestException as exc:
        log.warning("Discord alert failed: %s", exc)


def notify(action: str, message: str, cfg: AlertConfig) -> None:
    """Alert only on actionable signals (BUY/SELL), never on HOLD."""
    if action not in ("BUY", "SELL"):
        return
    if cfg.sound:
        play_sound(action)
    webhook = os.getenv(cfg.discord_webhook_env, "")
    if webhook:
        send_discord(message, webhook)
