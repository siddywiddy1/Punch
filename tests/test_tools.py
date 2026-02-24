import pytest
from punch.tools.shell import run_shell
from punch.tools.filesystem import list_dir, read_file, write_file, search_files
from punch.tools.macos import run_applescript, notify, get_frontmost_app


@pytest.mark.asyncio
async def test_run_shell():
    result = await run_shell("echo hello")
    assert result["stdout"].strip() == "hello"
    assert result["exit_code"] == 0


@pytest.mark.asyncio
async def test_run_shell_failure():
    result = await run_shell("false")
    assert result["exit_code"] != 0


@pytest.mark.asyncio
async def test_list_dir(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("world")
    items = await list_dir(str(tmp_path))
    names = [i["name"] for i in items]
    assert "a.txt" in names
    assert "b.txt" in names


@pytest.mark.asyncio
async def test_read_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    content = await read_file(str(f))
    assert content == "hello world"


@pytest.mark.asyncio
async def test_write_file(tmp_path):
    f = tmp_path / "output.txt"
    await write_file(str(f), "test content")
    assert f.read_text() == "test content"


@pytest.mark.asyncio
async def test_search_files(tmp_path):
    (tmp_path / "hello.txt").write_text("find me here")
    (tmp_path / "other.txt").write_text("nothing")
    results = await search_files(str(tmp_path), "find me")
    assert len(results) == 1
    assert "hello.txt" in results[0]["path"]
