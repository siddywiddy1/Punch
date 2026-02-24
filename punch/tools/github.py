from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger("punch.tools.github")


async def _run_gh(args: list[str], timeout: int = 30) -> dict:
    proc = await asyncio.create_subprocess_exec(
        "gh", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return {
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "exit_code": proc.returncode or 0,
    }


async def list_repos(limit: int = 20) -> list[dict]:
    result = await _run_gh(["repo", "list", "--json", "name,description,updatedAt,url", "-L", str(limit)])
    if result["exit_code"] == 0:
        return json.loads(result["stdout"])
    return []


async def list_issues(repo: str, state: str = "open", limit: int = 20) -> list[dict]:
    result = await _run_gh(["issue", "list", "-R", repo, "--state", state,
                            "--json", "number,title,state,createdAt,author", "-L", str(limit)])
    if result["exit_code"] == 0:
        return json.loads(result["stdout"])
    return []


async def list_prs(repo: str, state: str = "open", limit: int = 20) -> list[dict]:
    result = await _run_gh(["pr", "list", "-R", repo, "--state", state,
                            "--json", "number,title,state,createdAt,author,headRefName", "-L", str(limit)])
    if result["exit_code"] == 0:
        return json.loads(result["stdout"])
    return []


async def get_pr(repo: str, number: int) -> dict:
    result = await _run_gh(["pr", "view", str(number), "-R", repo,
                            "--json", "number,title,state,body,author,createdAt,headRefName"])
    if result["exit_code"] == 0:
        return json.loads(result["stdout"])
    return {}


async def create_issue(repo: str, title: str, body: str = "") -> dict:
    args = ["issue", "create", "-R", repo, "--title", title]
    if body:
        args.extend(["--body", body])
    result = await _run_gh(args)
    return {"output": result["stdout"], "exit_code": result["exit_code"]}


async def repo_status(repo_path: str) -> dict:
    """Get git status for a local repo."""
    proc = await asyncio.create_subprocess_exec(
        "git", "status", "--porcelain",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=repo_path,
    )
    stdout, _ = await proc.communicate()
    return {
        "changes": stdout.decode().strip().split("\n") if stdout.strip() else [],
        "clean": not stdout.strip(),
    }
