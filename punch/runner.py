from __future__ import annotations

import asyncio
import logging
import json
from dataclasses import dataclass

logger = logging.getLogger("punch.runner")


@dataclass
class RunResult:
    stdout: str
    stderr: str
    exit_code: int
    session_id: str | None

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class ClaudeRunner:
    def __init__(self, claude_command: str = "claude", max_concurrent: int = 4):
        self.claude_command = claude_command
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    def _build_command(
        self,
        prompt: str,
        oneshot: bool = False,
        system_prompt: str | None = None,
        session_id: str | None = None,
        working_dir: str | None = None,
        output_format: str = "text",
        allowed_tools: list[str] | None = None,
    ) -> list[str]:
        cmd = [self.claude_command]

        if oneshot:
            cmd.append("--print")

        if session_id:
            cmd.extend(["--resume", session_id])

        if system_prompt:
            cmd.extend(["--system-prompt", system_prompt])

        if output_format == "json":
            cmd.extend(["--output-format", "json"])

        if allowed_tools:
            for tool in allowed_tools:
                cmd.extend(["--allowedTools", tool])

        cmd.extend(["-p", prompt])

        return cmd

    async def run(
        self,
        prompt: str,
        oneshot: bool = False,
        system_prompt: str | None = None,
        session_id: str | None = None,
        working_dir: str | None = None,
        timeout: int = 300,
        output_format: str = "text",
        allowed_tools: list[str] | None = None,
    ) -> RunResult:
        cmd = self._build_command(
            prompt=prompt,
            oneshot=oneshot,
            system_prompt=system_prompt,
            session_id=session_id,
            output_format=output_format,
            allowed_tools=allowed_tools,
        )

        logger.info(f"Running Claude Code: {' '.join(cmd[:5])}...")

        async with self._semaphore:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=working_dir,
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                stdout = stdout_bytes.decode("utf-8", errors="replace")
                stderr = stderr_bytes.decode("utf-8", errors="replace")

                # Try to extract session ID from JSON output
                new_session_id = None
                if output_format == "json":
                    try:
                        data = json.loads(stdout)
                        new_session_id = data.get("session_id")
                        stdout = data.get("result", stdout)
                    except json.JSONDecodeError:
                        pass

                result = RunResult(
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=proc.returncode or 0,
                    session_id=new_session_id or session_id,
                )
                logger.info(f"Claude Code finished: exit={result.exit_code}, output_len={len(result.stdout)}")
                return result

            except asyncio.TimeoutError:
                logger.warning(f"Claude Code timed out after {timeout}s")
                if proc:
                    proc.kill()
                return RunResult(
                    stdout="",
                    stderr=f"Task timed out after {timeout} seconds",
                    exit_code=-1,
                    session_id=session_id,
                )
            except Exception as e:
                logger.error(f"Claude Code error: {e}")
                return RunResult(
                    stdout="",
                    stderr=str(e),
                    exit_code=-1,
                    session_id=session_id,
                )

    async def quick(self, prompt: str, system_prompt: str | None = None, timeout: int = 120) -> str:
        """Convenience: one-shot query, returns just the text."""
        result = await self.run(prompt=prompt, oneshot=True, system_prompt=system_prompt, timeout=timeout)
        if result.success:
            return result.stdout.strip()
        raise RuntimeError(f"Claude Code failed: {result.stderr}")
