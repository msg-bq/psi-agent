"""Manage reusable Fusion Method assets."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import _runtime_paths as _paths
import anyio


def _mtds_dir() -> anyio.Path:
    # Mtd task dirs live under the user workspace.
    return _paths.resolve_workspace() / "mtds"


def _validate_mtd_name(mtd_name: str) -> str | None:
    if not mtd_name.strip():
        return "Invalid mtd name: name cannot be empty."
    if "/" in mtd_name or "\\" in mtd_name:
        return f"Invalid mtd name {mtd_name!r}: must not contain path separators."
    if ".." in mtd_name:
        return f"Invalid mtd name {mtd_name!r}: must not contain '..'."
    if "\x00" in mtd_name:
        return f"Invalid mtd name {mtd_name!r}: must not contain null characters."
    if not re.fullmatch(r"[A-Za-z0-9_-]+", mtd_name):
        return f"Invalid mtd name {mtd_name!r}: only letters, digits, hyphens, and underscores are allowed."
    return None


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    if not content.startswith("---\n"):
        return {}, content
    end = content.find("\n---", 4)
    if end == -1:
        return {}, content

    frontmatter: dict[str, str] = {}
    for line in content[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        frontmatter[key.strip()] = value.strip().strip("\"'")
    return frontmatter, content[end + 4 :].lstrip("\n")


async def _atomic_write(path: anyio.Path, content: str) -> None:
    await path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp"
    await tmp.write_text(content, encoding="utf-8")
    await tmp.replace(path)


async def _find_task_mtd(mtds_dir: anyio.Path, mtd_name: str) -> anyio.Path | None:
    task_dir = mtds_dir / mtd_name
    preferred = task_dir / f"{mtd_name}.method"
    if await preferred.exists():
        return preferred
    if not await task_dir.is_dir():
        return None
    async for candidate in task_dir.glob("*.method"):
        return candidate
    return None


def _format_mtd_document(
    *,
    mtd_name: str,
    description: str,
    category: str,
    body: str,
    mtd_source: str,
    source: str = "",
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "---",
        f"name: {mtd_name}",
        f"description: {description or '(no description)'}",
        f"category: {category or 'general'}",
        "created_by: agent",
        f"created_at: {now}",
    ]
    if source:
        lines.append(f"source: {source}")
    lines.append("---")

    sections = ["\n".join(lines), body.strip()]
    if mtd_source.strip():
        sections.append("```fusionmethod\n" + mtd_source.strip() + "\n```")
    return "\n\n".join(section for section in sections if section).rstrip() + "\n"


async def mtd_manage(
    action: str = "list",
    mtd_name: str = "",
    description: str = "",
    category: str = "general",
    body: str = "",
    mtd_source: str = "",
    target: str = "curated",
) -> str:
    """Create, patch, view, list, or promote reusable Fusion Method assets.

    Args:
        action: One of "list", "view", "create", "patch", or "promote".
        mtd_name: Mtd name for view/create/patch/promote.
        description: One-line description for created or promoted mtds.
        category: Category tag for created or promoted mtds.
        body: MTD.md body text, excluding frontmatter and FusionMethod block.
        mtd_source: FusionMethod G4 source to store in MTD.md.
        target: For list/view/create. Use "curated", "tasks", "adhoc", or "all".

    Returns:
        A result message, list output, or mtd content.
    """
    mtds_dir = _mtds_dir()
    action = action.strip().lower()
    target = target.strip().lower() or "curated"

    if action == "list":
        lines: list[str] = []

        if target in {"curated", "all"}:
            curated_dir = mtds_dir / "curated"
            curated_entries: list[str] = []
            if await curated_dir.exists():
                async for entry in curated_dir.iterdir():
                    mtd_md = entry / "MTD.md"
                    if not await entry.is_dir() or entry.name.startswith(".") or not await mtd_md.exists():
                        continue
                    raw = await mtd_md.read_text(encoding="utf-8", errors="replace")
                    frontmatter, _body = _parse_frontmatter(raw)
                    desc = frontmatter.get("description") or "(no description)"
                    tag = " [agent]" if frontmatter.get("created_by") == "agent" else ""
                    curated_entries.append(f"  - {entry.name}{tag}: {desc}")
            if curated_entries:
                lines.append("curated/")
                lines.extend(sorted(curated_entries))

        if target in {"tasks", "all"} and await mtds_dir.exists():
            task_entries: list[str] = []
            async for entry in mtds_dir.iterdir():
                if not await entry.is_dir() or entry.name.startswith(".") or entry.name in {"curated", "adhoc"}:
                    continue
                task_mtd = await _find_task_mtd(mtds_dir, entry.name)
                if task_mtd is not None:
                    task_entries.append(f"  - {entry.name}: {task_mtd.name}")
            if task_entries:
                lines.append("tasks/")
                lines.extend(sorted(task_entries))

        if target in {"adhoc", "all"}:
            adhoc_dir = mtds_dir / "adhoc"
            adhoc_entries: list[str] = []
            if await adhoc_dir.exists():
                async for entry in adhoc_dir.iterdir():
                    mtd_file = entry / "mtd.method"
                    if await entry.is_dir() and not entry.name.startswith(".") and await mtd_file.exists():
                        adhoc_entries.append(f"  - {entry.name}: mtd.method")
            if adhoc_entries:
                lines.append("adhoc/")
                lines.extend(sorted(adhoc_entries))

        return "\n".join(lines) if lines else "No mtds found."

    if action == "view":
        if err := _validate_mtd_name(mtd_name):
            return f"[Error] {err}"

        if target in {"curated", "all"}:
            mtd_md = mtds_dir / "curated" / mtd_name / "MTD.md"
            if await mtd_md.exists():
                return await mtd_md.read_text(encoding="utf-8", errors="replace")

        if target in {"tasks", "all"}:
            task_mtd = await _find_task_mtd(mtds_dir, mtd_name)
            if task_mtd is not None:
                return await task_mtd.read_text(encoding="utf-8", errors="replace")

        if target in {"adhoc", "all"}:
            adhoc_mtd = mtds_dir / "adhoc" / mtd_name / "mtd.method"
            if await adhoc_mtd.exists():
                return await adhoc_mtd.read_text(encoding="utf-8", errors="replace")

        return f"[Error] Mtd not found: {mtd_name!r}"

    if action == "create":
        if err := _validate_mtd_name(mtd_name):
            return f"[Error] {err}"
        if target not in {"curated", "adhoc"}:
            return "[Error] Create target must be 'curated' or 'adhoc'."

        if target == "adhoc":
            mtd_path = mtds_dir / "adhoc" / mtd_name / "mtd.method"
            if await mtd_path.exists():
                return f"[Error] Adhoc mtd already exists: {mtd_name!r}"
            await _atomic_write(mtd_path, mtd_source.strip() + "\n")
            return f"Adhoc mtd created: {mtd_name!r}"

        mtd_md = mtds_dir / "curated" / mtd_name / "MTD.md"
        if await mtd_md.exists():
            return f"[Error] Curated mtd already exists: {mtd_name!r}. Use action='patch' to update it."
        await _atomic_write(
            mtd_md,
            _format_mtd_document(
                mtd_name=mtd_name,
                description=description,
                category=category,
                body=body,
                mtd_source=mtd_source,
            ),
        )
        return f"Curated mtd created: {mtd_name!r}"

    if action == "patch":
        if err := _validate_mtd_name(mtd_name):
            return f"[Error] {err}"

        mtd_md = mtds_dir / "curated" / mtd_name / "MTD.md"
        if not await mtd_md.exists():
            return f"[Error] Curated mtd not found: {mtd_name!r}"

        raw = await mtd_md.read_text(encoding="utf-8", errors="replace")
        frontmatter, existing_body = _parse_frontmatter(raw)
        if frontmatter.get("created_by") != "agent":
            return f"[Error] Mtd {mtd_name!r} is user-authored or unmanaged; patch is read-only."

        frontmatter["updated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines = ["---", *(f"{key}: {value}" for key, value in frontmatter.items()), "---"]
        next_body = body.strip() or existing_body.strip()
        if mtd_source.strip():
            next_body = re.sub(
                r"```(?:fusionmethod|g4)\s*\n.*?```",
                "```fusionmethod\n" + mtd_source.strip() + "\n```",
                next_body,
                flags=re.DOTALL,
            )
            if "```fusionmethod" not in next_body and "```g4" not in next_body:
                next_body += "\n\n```fusionmethod\n" + mtd_source.strip() + "\n```"

        await _atomic_write(mtd_md, "\n".join(lines) + "\n\n" + next_body.strip() + "\n")
        return f"Curated mtd patched: {mtd_name!r}"

    if action == "promote":
        if err := _validate_mtd_name(mtd_name):
            return f"[Error] {err}"

        source_path = await _find_task_mtd(mtds_dir, mtd_name)
        source_label = f"mtds/{mtd_name}"
        if source_path is None:
            adhoc_path = mtds_dir / "adhoc" / mtd_name / "mtd.method"
            if await adhoc_path.exists():
                source_path = adhoc_path
                source_label = f"mtds/adhoc/{mtd_name}/mtd.method"

        if source_path is None:
            return f"[Error] No task or adhoc mtd found for: {mtd_name!r}"

        mtd_md = mtds_dir / "curated" / mtd_name / "MTD.md"
        if await mtd_md.exists():
            return f"[Error] Curated mtd already exists: {mtd_name!r}"

        source = await source_path.read_text(encoding="utf-8", errors="replace")
        await _atomic_write(
            mtd_md,
            _format_mtd_document(
                mtd_name=mtd_name,
                description=description,
                category=category,
                body=body,
                mtd_source=source,
                source=source_label,
            ),
        )
        return f"Mtd promoted to curated: {mtd_name!r}"

    return "[Error] Unknown action. Use 'list', 'view', 'create', 'patch', or 'promote'."
