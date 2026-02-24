from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger("punch.tools.macos")


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
    script = f'display notification "{message}" with title "{title}"'
    await run_applescript(script)


async def get_frontmost_app() -> str:
    return await run_applescript(
        'tell application "System Events" to get name of first application process whose frontmost is true'
    )


async def open_app(app_name: str) -> None:
    await run_applescript(f'tell application "{app_name}" to activate')


async def open_url(url: str) -> None:
    await run_applescript(f'open location "{url}"')


async def get_clipboard() -> str:
    return await run_applescript("the clipboard")


async def set_clipboard(text: str) -> None:
    await run_applescript(f'set the clipboard to "{text}"')


async def list_running_apps() -> list[str]:
    result = await run_applescript(
        'tell application "System Events" to get name of every application process whose background only is false'
    )
    return [app.strip() for app in result.split(",")]


async def keystroke(text: str, app: str | None = None) -> None:
    if app:
        script = f'tell application "{app}" to activate\ndelay 0.5\ntell application "System Events" to keystroke "{text}"'
    else:
        script = f'tell application "System Events" to keystroke "{text}"'
    await run_applescript(script)
