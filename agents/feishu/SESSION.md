# Session path rules

The user workspace and the agent package may be different directories.

- `read("relative/path")` always resolves that relative path under the current **user workspace**. It does not search the agent package.
- Bundled Skills live under the **agent package** at `skills/<name>/SKILL.md`, not necessarily under the user workspace.
- When a prompt section provides an **absolute** `SKILL.md` path, pass that exact absolute path to `read`. If the same section also shows a `Relative path: skills/...` hint, the absolute path is authoritative when `agent != workspace`.
- Do not search the filesystem, installation directories, package locations, or tool source files just to locate a bundled Skill.
- For `workflow`, `FusionFlow`, `TerminalStep`, `BoolArtifact`, feedback loops, or `.workflow` requests: read the exact absolute Workflow `SKILL.md` path shown in the `## Workflow` section, then use `run_flow`. `flow_run` is only for explicit legacy `.flow.ts` / Fuclaw requests.
- If a bundled Skill is clearly applicable but no absolute path is supplied, use `skill_manage(action="view", skill_name="<name>")` instead of filesystem discovery.
