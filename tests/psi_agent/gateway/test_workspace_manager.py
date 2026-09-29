"""Tests for WorkspaceManager browsing, places, and reusable methods."""

from __future__ import annotations

import anyio
import pytest

from psi_agent.gateway._workspace_manager import WorkspaceManager


async def _write_method(
    workspace: anyio.Path,
    name: str,
) -> anyio.Path:
    method_dir = workspace / "mtds" / "methods" / name
    await method_dir.mkdir(parents=True, exist_ok=True)
    await (method_dir / f"{name}.method").write_text(
        f"method {name.replace('-', '_')} {{}}",
        encoding="utf-8",
    )
    return method_dir


@pytest.mark.anyio
async def test_browse_returns_segments_and_directories(tmp_path) -> None:
    child = tmp_path / "child"
    child.mkdir()
    (tmp_path / "readme.txt").write_text("hi", encoding="utf-8")

    wm = WorkspaceManager()
    result = await wm.browse(str(tmp_path))

    assert result["path"].replace("\\", "/") == str(tmp_path).replace("\\", "/")
    assert isinstance(result["segments"], list) and len(result["segments"]) >= 1
    names = [e["name"] for e in result["entries"]]
    assert "child" in names
    assert "readme.txt" not in names


@pytest.mark.anyio
async def test_browse_file_kind_includes_files(tmp_path) -> None:
    (tmp_path / "note.md").write_text("# x", encoding="utf-8")

    wm = WorkspaceManager()
    result = await wm.browse(str(tmp_path), kind="file")

    kinds = {e["name"]: e["kind"] for e in result["entries"]}
    assert kinds.get("note.md") == "file"


@pytest.mark.anyio
async def test_list_places_includes_cwd() -> None:
    wm = WorkspaceManager()
    data = await wm.list_places()
    assert isinstance(data["places"], list)
    assert any(r["id"] == "cwd" for r in data["places"])
    assert isinstance(data["drives"], list)


@pytest.mark.anyio
async def test_list_methods_returns_valid_sorted_summaries(tmp_path) -> None:
    workspace = anyio.Path(str(tmp_path))
    await _write_method(workspace, "zeta-mtd")
    await _write_method(workspace, "alpha-mtd")

    result = await WorkspaceManager().list_methods(str(workspace))

    assert result == [
        {
            "name": "alpha-mtd",
            "path": "mtds/methods/alpha-mtd/alpha-mtd.method",
        },
        {
            "name": "zeta-mtd",
            "path": "mtds/methods/zeta-mtd/zeta-mtd.method",
        },
    ]


@pytest.mark.anyio
async def test_list_methods_skips_corrupt_and_incomplete_entries(tmp_path) -> None:
    workspace = anyio.Path(str(tmp_path))
    await _write_method(workspace, "valid-mtd")

    missing_source = workspace / "mtds" / "methods" / "missing-source"
    await missing_source.mkdir(parents=True)
    await (missing_source / "other.method").write_text(
        "method other {}",
        encoding="utf-8",
    )

    invalid_name = await _write_method(workspace, "Invalid_Name")
    assert await invalid_name.exists()

    result = await WorkspaceManager().list_methods(str(workspace))

    assert [method["name"] for method in result] == ["valid-mtd"]


@pytest.mark.parametrize(
    "name",
    [
        "con",
        "prn",
        "aux",
        "nul",
        "com1",
        "com9",
        "lpt1",
        "lpt9",
    ],
)
def test_method_name_rejects_windows_reserved_names(name: str) -> None:
    assert not WorkspaceManager._is_valid_method_name(name)


@pytest.mark.anyio
async def test_list_methods_skips_symlinked_entries_and_sources(tmp_path) -> None:
    workspace = anyio.Path(str(tmp_path))
    registry = workspace / "mtds" / "methods"
    await registry.mkdir(parents=True)

    outside = workspace / "outside"
    await _write_method(outside, "linked-mtd")
    outside_entry = outside / "mtds" / "methods" / "linked-mtd"
    try:
        await (registry / "linked-mtd").symlink_to(outside_entry, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not available")

    source_link = await _write_method(workspace, "source-link")
    await (source_link / "source-link.method").unlink()
    await (source_link / "source-link.method").symlink_to(outside_entry / "linked-mtd.method")

    result = await WorkspaceManager().list_methods(str(workspace))

    assert result == []


@pytest.mark.anyio
async def test_list_methods_skips_symlinked_registry_components(tmp_path) -> None:
    workspace = anyio.Path(str(tmp_path))
    real_mtds = workspace / "real-mtds"
    await _write_method(real_mtds, "linked-mtd")
    try:
        await (workspace / "mtds").symlink_to(real_mtds / "mtds", target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not available")

    assert await WorkspaceManager().list_methods(str(workspace)) == []

    await (workspace / "mtds").unlink()
    await (workspace / "mtds").mkdir()
    await (workspace / "mtds" / "methods").symlink_to(real_mtds / "mtds" / "methods", target_is_directory=True)

    assert await WorkspaceManager().list_methods(str(workspace)) == []


@pytest.mark.anyio
async def test_list_methods_skips_oversized_source(tmp_path) -> None:
    workspace = anyio.Path(str(tmp_path))
    oversized_source = await _write_method(workspace, "oversized-source")
    await (oversized_source / "oversized-source.method").write_bytes(b"x" * (8 * 1024 * 1024 + 1))

    assert await WorkspaceManager().list_methods(str(workspace)) == []


@pytest.mark.anyio
async def test_list_methods_missing_registry_is_empty(tmp_path) -> None:
    result = await WorkspaceManager().list_methods(str(tmp_path))
    assert result == []


@pytest.mark.anyio
async def test_reveal_requires_path() -> None:
    wm = WorkspaceManager()
    with pytest.raises(ValueError, match="path is required"):
        await wm.reveal("  ")


@pytest.mark.anyio
async def test_reveal_missing_path(tmp_path) -> None:
    wm = WorkspaceManager()
    with pytest.raises(FileNotFoundError):
        await wm.reveal(str(tmp_path / "no-such-file.txt"))


@pytest.mark.anyio
async def test_reveal_invokes_platform_launcher(tmp_path, monkeypatch) -> None:
    target = tmp_path / "out.md"
    target.write_text("hi", encoding="utf-8")
    calls: list[list[str]] = []

    async def fake_run_process(cmd: list[str] | tuple[str, ...], **_kwargs: object) -> None:
        calls.append(list(cmd))

    monkeypatch.setattr("psi_agent.gateway._workspace_manager.anyio.run_process", fake_run_process)
    monkeypatch.setattr("psi_agent.gateway._workspace_manager.sys.platform", "win32")

    wm = WorkspaceManager()
    result = await wm.reveal(str(target))
    assert result["ok"] is True
    assert result["path"].replace("\\", "/").endswith("out.md")
    assert len(calls) == 1
    assert calls[0][0] == "explorer"
    assert calls[0][1].startswith("/select,")
    assert "out.md" in calls[0][1]
