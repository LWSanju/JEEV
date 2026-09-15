# JEEV Coding Agent v1

This feature adds a natural-language coding agent to JEEV, using OpenCode-inspired agent/tool patterns rather than generating one giant code response.

## User experience

Examples:

- "Fix the OpenRouter error without breaking Gemini."
- "Add dark mode to this app."
- "Find why login is failing and fix it."
- "Create a settings page and wire it into the existing app."
- "Refactor this module and run the tests."

## Agent capabilities

- project tree inspection
- file reads
- glob/search
- regex grep
- file creation
- targeted edits
- terminal/test/build commands
- failure diagnosis and repair loop
- multi-step continuation
- persisted task state under `.jeev/coding/`
- plan-only mode
- one active writer per workspace

## Integration

`main.py` already exposes `dev_agent`. The replacement declaration now routes real coding work to `actions/dev_agent.py`.

`actions/dev_agent.py` is the JEEV-facing wrapper.

`core/coding/coding_agent.py` contains the coding engine.

## Model

The engine uses JEEV's existing `or_client.get_client().multi_turn()` backend. It therefore keeps model/provider handling outside the coding engine.

## Workspace selection

The tool accepts `project_path`, `root`, or `workspace`.
If none is provided it uses `JEEV_CODING_ROOT`, then the current working directory.

## Safety

The coding workspace is bounded to the selected project root. Secrets such as `.env` are not deliberately edited by the agent prompt. Terminal execution is performed in the workspace directory. A task is capped at 80 agent steps per invocation and saves its state so the workflow can be extended later rather than pretending a short model response is unlimited.
