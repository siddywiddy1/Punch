from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("punch.tools.macos")


def _escape_applescript(s: str) -> str:
    """Escape a string for safe inclusion in AppleScript double-quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


async def run_applescript(script: str, timeout: int = 30) -> str:
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"AppleScript error: {stderr.decode()}")
    return stdout.decode().strip()


async def notify(title: str, message: str) -> None:
    t, m = _escape_applescript(title), _escape_applescript(message)
    script = f'display notification "{m}" with title "{t}"'
    await run_applescript(script)


async def get_frontmost_app() -> str:
    return await run_applescript(
        'tell application "System Events" to get name of first application process whose frontmost is true'
    )


async def open_app(app_name: str) -> None:
    name = _escape_applescript(app_name)
    await run_applescript(f'tell application "{name}" to activate')


async def open_url(url: str) -> None:
    u = _escape_applescript(url)
    await run_applescript(f'open location "{u}"')


async def get_clipboard() -> str:
    return await run_applescript("the clipboard")


async def set_clipboard(text: str) -> None:
    t = _escape_applescript(text)
    await run_applescript(f'set the clipboard to "{t}"')


async def list_running_apps() -> list[str]:
    result = await run_applescript(
        'tell application "System Events" to get name of every application process whose background only is false'
    )
    return [app.strip() for app in result.split(",")]


async def keystroke(text: str, app: str | None = None) -> None:
    t = _escape_applescript(text)
    if app:
        a = _escape_applescript(app)
        script = f'tell application "{a}" to activate\ndelay 0.5\ntell application "System Events" to keystroke "{t}"'
    else:
        script = f'tell application "System Events" to keystroke "{t}"'
    await run_applescript(script)
