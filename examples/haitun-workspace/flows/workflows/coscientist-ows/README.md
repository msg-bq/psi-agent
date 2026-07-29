# Co-scientist OWS workflow

This directory is part of the `coscientist-ows` workspace overlay produced by
CI. Extract the archive into the root of a compatible Haitun workspace, keeping
the included `flows/` and `skills/` paths unchanged.

Invoke the saved workflow with this exact chat command:

```text
/workflow:coscientist-ows
```

The session asks for the seven values declared by `input_workflow`. The
`coscientist-ows.inputs.example.json` file is a sanitized input example for
copying values; it is not loaded automatically by `/workflow:coscientist-ows`.

## Host requirements

- A current psi-agent Haitun workspace with the FusionFlow runner.
- Python with `aiohttp`.
- `data/knowledge-base/knowledge_base_for_agent.json`.
- `data/laboratory-limitations/laboratory_limitations_for_agent.json`.
- The complete `data/chem-skills/` directory used by route-design agents.
- A working MatterGen/MatterSim installation, model files, and CUDA GPU.
- Network access, `LLM_PROOF_API_KEY`, and an explicit `LLM_PROOF_BASE_URL` for
  the catalytic-performance proof step. `LLM_PROOF_MODEL` is optional.

The catalytic-performance Step uses the bundled deterministic Program adapter:
it invokes the Stage08 runner once per candidate with the same Python
interpreter as psi-agent, writes proof/audit files beside that candidate, and
moves the actual `slot_n/<folder>` directory without trusting `candidate_id`.

API keys, model files, runtime histories, caches, and generated results are not
included in the CI artifact.
