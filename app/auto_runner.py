import asyncio
import ctypes
import logging
import msvcrt
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from app.config import ROOT, get_settings
from app.db import (
    Draft,
    DraftStatus,
    active_draft_today,
    draft_created_today,
    init_db,
    post_published_today,
    rejected_drafts_today,
    session,
)
from app.inbox import check_email_replies
from app.linkedin import publish_draft
from app.orchestrator import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("auto_runner")

_lock_file_handle = None


def acquire_single_instance_lock() -> bool:
    """Ensure only one instance of auto_runner runs at a time."""
    global _lock_file_handle
    lock_path = ROOT / ".auto_runner.lock"
    try:
        _lock_file_handle = open(lock_path, "a+")
        msvcrt.locking(_lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except (BlockingIOError, OSError, PermissionError):
        return False


def set_cmd_title(title: str = "Personal Social Media Agent - Live Runner"):
    """Set the Windows CMD window title."""
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass


def print_banner():
    now_str = datetime.now().strftime("%A, %b %d, %Y - %I:%M %p")
    print("\n" + "=" * 76)
    print("        🚀  PERSONAL SOCIAL MEDIA AGENT - LIVE CONSOLE RUNNER  🚀")
    print("=" * 76)
    print(f" Local Time  : {now_str}")
    print(f" Workspace   : {ROOT}")
    print(f" Target      : LinkedIn Auto-Publisher with Email Review")
    print("=" * 76 + "\n")


def print_draft_preview(d: Draft):
    border = "-" * 76
    print("\n" + border)
    print(f" 📝 DRAFT #{d.id}: {d.topic[:55]}")
    print(f" Status: {d.status} | Words: {d.word_count} | Model: {d.model}")
    print(border)
    preview_lines = d.text.strip().splitlines()
    for line in preview_lines[:12]:
        print(f"  {line}")
    if len(preview_lines) > 12:
        print(f"  ... [{len(preview_lines) - 12} more lines]")
    print(border + "\n")


def is_online(timeout: float = 2.5) -> bool:
    """Instant check if internet connection is alive (connects to DNS servers)."""
    for host in ("1.1.1.1", "8.8.8.8"):
        try:
            with socket.create_connection((host, 53), timeout=timeout):
                return True
        except OSError:
            continue
    return False


async def wait_for_internet(max_wait_seconds: int = 600, check_interval: int = 5) -> bool:
    """Wait for Wi-Fi or Ethernet to connect after laptop boot / wake."""
    if is_online():
        return True

    log.info("🌐 Laptop awake / starting, waiting for Wi-Fi / Internet connection...")
    start_time = time.time()
    while time.time() - start_time < max_wait_seconds:
        await asyncio.sleep(check_interval)
        if is_online():
            log.info("🌐 Internet connection established! Resuming agent.")
            return True

    log.warning("⚠️ No internet connection available after %d seconds. Exiting for now.", max_wait_seconds)
    return False


def ensure_ollama_running() -> bool:
    """Check if Ollama server is running; try to start it if not."""
    settings = get_settings()
    url = settings.ollama_url.rstrip("/")
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{url}/api/version")
            if resp.status_code == 200:
                log.info("Ollama LLM is online at %s", url)
                return True
    except Exception:
        pass

    log.info("Ollama is not running. Attempting to start tray app/service...")
    try:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        ollama_app = os.path.join(local_app_data, "Programs", "Ollama", "ollama app.exe")
        if os.path.exists(ollama_app):
            subprocess.Popen([ollama_app], shell=True)
            for _ in range(15):
                time.sleep(2)
                try:
                    with httpx.Client(timeout=2.0) as client:
                        if client.get(f"{url}/api/version").status_code == 200:
                            log.info("Ollama started successfully.")
                            return True
                except Exception:
                    continue
    except Exception as e:
        log.warning("Could not auto-start Ollama: %r", e)

    return False


def unload_ollama_model() -> None:
    """Free model RAM after drafting so laptop memory is preserved."""
    try:
        settings = get_settings()
        url = settings.ollama_url.rstrip("/")
        model = settings.ollama_model
        with httpx.Client(timeout=5.0) as client:
            client.post(f"{url}/api/generate", json={"model": model, "keep_alive": 0})
        log.info("Unloaded Ollama model '%s' to free laptop RAM.", model)
    except Exception:
        pass


async def main():
    set_cmd_title("Personal Social Media Agent - Live Runner")
    print_banner()

    # Step 0: Ensure single running instance
    if not acquire_single_instance_lock():
        log.info("ℹ️ Personal Social Agent is already running in another window.")
        log.info("Exiting duplicate instance to avoid conflict.")
        time.sleep(3)
        sys.exit(0)

    init_db()

    # Step 1: Check if today's post is ALREADY posted to LinkedIn
    with session() as s:
        already_posted = post_published_today(s)
        if already_posted:
            log.info(
                "✅ Today's post (Draft #%d - '%s') was ALREADY published to LinkedIn at %s!",
                already_posted.id,
                already_posted.topic[:40],
                already_posted.posted_at or already_posted.created_at,
            )
            log.info("🎉 Daily social media goal is already achieved! Closing in 15 seconds...")
            await asyncio.sleep(15)
            sys.exit(0)

    # Step 2: Ensure internet connection is available
    connected = await wait_for_internet(max_wait_seconds=600)
    if not connected:
        log.warning("Laptop appears offline. Exiting auto-runner for now; will re-check on next wake/startup.")
        await asyncio.sleep(10)
        sys.exit(0)

    # Step 3: Check today's active draft status
    MAX_REJECTIONS_PER_DAY = 3
    with session() as s:
        current_draft = active_draft_today(s)
        rejected_today = rejected_drafts_today(s)

    if current_draft:
        log.info(
            "📌 Today's active draft #%d already exists (Status: %s, Topic: '%s').",
            current_draft.id,
            current_draft.status,
            current_draft.topic[:45],
        )
        print_draft_preview(current_draft)
    elif len(rejected_today) >= MAX_REJECTIONS_PER_DAY:
        log.warning(
            "⚠️ Today's draft limit reached (%d rejected drafts). Skipping further posting today.",
            len(rejected_today),
        )
        log.info("Closing agent in 15 seconds...")
        await asyncio.sleep(15)
        sys.exit(0)
    else:
        # Generate fresh draft
        if rejected_today:
            log.info(
                "🔄 Previous draft(s) today were rejected (%d/%d). Generating alternative draft on next topic...",
                len(rejected_today),
                MAX_REJECTIONS_PER_DAY,
            )
        else:
            log.info("⚡ No post drafted yet for today. Starting generation pipeline...")

        ensure_ollama_running()
        run = await run_pipeline(force=True)

        if run.status != "OK" or not run.draft_id:
            log.error("Pipeline failed to create draft: %s", run.message)
            log.info("Window will close in 20 seconds...")
            await asyncio.sleep(20)
            sys.exit(1)

        with session() as s:
            current_draft = s.get(Draft, run.draft_id)

        unload_ollama_model()
        log.info("✉️ Draft #%d created and emailed for approval!", current_draft.id)
        print_draft_preview(current_draft)

    # Step 4: Handle approval & publishing loop
    print("📱 WAITING FOR YOUR MOBILE APPROVAL VIA GMAIL:")
    print("   - Reply 'YES' or 'APPROVE' to publish to LinkedIn immediately")
    print("   - Reply 'NO' or 'REJECT' to generate an alternative topic")
    print("   - Reply with edits or feedback (e.g. 'make it punchier') to rewrite with AI")
    print("⏳ Polling Gmail inbox every 25 seconds... (Press Ctrl+C to close)\n")

    while True:
        with session() as s:
            d = s.get(Draft, current_draft.id)
            if not d:
                break

            # 1. APPROVED
            if d.status == DraftStatus.APPROVED:
                log.info("🎉 Draft #%d is APPROVED! Publishing to LinkedIn...", d.id)
                try:
                    res = publish_draft(d.id)
                    log.info("🚀 Successfully published to LinkedIn! Post URN: %s", res.get("linkedin_post_id"))
                    log.info("✅ Daily post complete! Window will close in 30 seconds.")
                    await asyncio.sleep(30)
                    sys.exit(0)
                except Exception as e:
                    log.exception("Failed to publish to LinkedIn: %r", e)

            # 2. POSTED
            if d.status == DraftStatus.POSTED:
                log.info("✅ Draft #%d is POSTED. Daily work complete! Closing in 30 seconds.", d.id)
                await asyncio.sleep(30)
                sys.exit(0)

            # 3. REJECTED -> Generate alternative draft
            if d.status == DraftStatus.REJECTED:
                rejected_count = len(rejected_drafts_today(s))
                log.info("❌ Draft #%d was REJECTED by user.", d.id)

                if rejected_count >= MAX_REJECTIONS_PER_DAY:
                    log.warning(
                        "⚠️ Reached maximum daily rejection limit (%d). Stopping for today.",
                        MAX_REJECTIONS_PER_DAY,
                    )
                    log.info("Window will close in 20 seconds...")
                    await asyncio.sleep(20)
                    sys.exit(0)

                log.info(
                    "🔄 Generating alternative draft (%d/%d) on next trending topic...",
                    rejected_count + 1,
                    MAX_REJECTIONS_PER_DAY,
                )
                ensure_ollama_running()
                run = await run_pipeline(force=True)

                if run.status != "OK" or not run.draft_id:
                    log.error("Pipeline failed to create alternative draft: %s", run.message)
                    await asyncio.sleep(20)
                    sys.exit(1)

                current_draft = s.get(Draft, run.draft_id)
                unload_ollama_model()
                log.info("✉️ Alternative Draft #%d created and emailed for approval!", current_draft.id)
                print_draft_preview(current_draft)
                continue

        # If internet drops temporarily while laptop is sleeping/waking, don't crash
        if not is_online(2.0):
            log.debug("Network temporarily offline, waiting to reconnect...")
            await asyncio.sleep(15)
            continue

        # Check Gmail inbox for reply
        try:
            replies = await asyncio.to_thread(check_email_replies)
            if replies:
                log.info("📬 Processed inbox reply: %r", replies)
        except Exception as e:
            log.debug("Inbox check error: %r", e)

        # Sleep before next check
        await asyncio.sleep(25)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user (Ctrl+C). Goodbye!")
        sys.exit(0)
