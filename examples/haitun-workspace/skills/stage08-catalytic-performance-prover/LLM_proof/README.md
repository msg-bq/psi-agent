# LLM Proof Runner

This folder keeps `SKILL.md` unchanged and provides an external-LLM runner for
the Stage08 catalytic-performance proof task.

The runner sends one API request per catalyst. Retained catalysts are never
placed in the same prompt, and each request contains only one candidate name and one
chemical formula. Requests are executed concurrently.

The API request uses a single user prompt template. The runner only replaces the
input-catalyst field with one candidate name and one chemical formula. No system
prompt, `SKILL.md` prompt, retry feedback prompt, or additional adaptation text
is appended to the model request.

## Environment

POSIX:

```bash
export LLM_PROOF_API_KEY="..."
export LLM_PROOF_BASE_URL="https://your-provider.example/v1"
```

Windows PowerShell:

```powershell
$env:LLM_PROOF_API_KEY = "..."
$env:LLM_PROOF_BASE_URL = "https://your-provider.example/v1"
```

Use the repository's existing active Python environment. On Windows, replace
the leading `python` in the commands below with
`& .\.venv\Scripts\python.exe`; do not use Bash or the `py` launcher.
Do not install dependencies during workflow execution.
Do not read, print, or log `LLM_PROOF_API_KEY`; provide it only through the
current shell environment.

The default model is `gpt-5.5`. Set `LLM_PROOF_MODEL` or pass `--model` only
when a different model is needed.

There is no default base URL. Set `LLM_PROOF_BASE_URL` or pass `--base-url`
explicitly for every provider.

## Dry Run

```bash
python skills/stage08-catalytic-performance-prover/LLM_proof/run_llm_proof.py \
  --input-json <output_root>/08-round-parallel-synthesis-advisor/rounds/<round_id>/ROUND_PARALLEL_SYNTHESIS_INDEX.json \
  --dry-run
```

## Batch Run

```bash
python skills/stage08-catalytic-performance-prover/LLM_proof/run_llm_proof.py \
  --input-json <output_root>/08-round-parallel-synthesis-advisor/rounds/<round_id>/ROUND_PARALLEL_SYNTHESIS_INDEX.json \
  --output <output_root>/10-catalytic-performance-prover/rounds/<round_id>/CATALYTIC_PERFORMANCE_PROOF.md \
  --checkpoint <output_root>/10-catalytic-performance-prover/rounds/<round_id>/CATALYTIC_PERFORMANCE_PROOF.jsonl \
  --concurrency 20
```

The Markdown output contains the assembled retained-catalyst proof document.
The audit JSON is written next to the Markdown output and records Chinese
character counts and repeated normalized sentences.
