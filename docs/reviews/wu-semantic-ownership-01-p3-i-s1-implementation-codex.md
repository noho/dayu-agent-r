# WU-SEMANTIC-OWNERSHIP-01 P3-I S1 Implementation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Slice: `S1 Public Package Entrypoints And README Truth`
- Gate: implementation
- Agent: AgentCodex

## Implementation

- Restored importable public package targets declared in `pyproject.toml`:
  - `dayu.web.__main__:main`
  - `dayu.wechat.main:main`
  - `dayu.render.render:main`
- Kept `pyproject.toml` unchanged because the declared target strings are the intended public contract for this slice.
- Added typed `main(argv: Sequence[str] | None = None) -> int` entrypoints with Chinese module/function docstrings.
- Kept module import paths lightweight: all new entrypoint modules import only standard-library `argparse`, `sys`, and typing helpers at module import time.
- Implemented `--help` and module `python -m ... --help` smoke behavior returning `0`.
- Implemented controlled non-help diagnostics for absent full Web UI, WeChat daemon/service, and Markdown render conversion.
- Did not create fake `dayu.render` CSS, HTML, Lua, DOCX, XLSX, Mermaid, or template resource files.

## Tests And Docs

- Added `tests/cli/test_public_package_entrypoints.py`.
- Updated `README.md` to describe only current public command truth:
  - `dayu-web`: help/current unavailable diagnostic only.
  - `dayu-wechat`: help/subcommand help/current unavailable diagnostic only.
  - `dayu-render`: help/current unavailable diagnostic only.
- Scope correction: write-related README edits were reverted; this slice does not implement or document `dayu-cli write`.
- Updated `tests/README.md` because a new `tests/cli` public package entrypoint smoke category was added.
- Updated `dayu/README.md` narrowly because adding `dayu.web`, `dayu.wechat`, and `dayu.render` changes the package boundary summary.

## Validation

Validation commands are recorded in the final response for this implementation gate.

## Propagation Audit

- Fact producer: `pyproject.toml` continues to declare `dayu-web`, `dayu-wechat`, and `dayu-render` script targets.
- Validation owner: `tests/cli/test_public_package_entrypoints.py` reads `pyproject.toml`, imports the exact targets, and verifies help/module smoke.
- Distribution owner: setuptools package discovery includes `dayu*`; new package directories make the declared targets importable in installed builds.
- Projection owner: root `README.md` now states only current help/current-diagnostic behavior for the three commands.
- User-visible output: command help and non-help diagnostics describe unavailable product behavior without presenting Host, Engine, or packaging internals as business facts.
- Deferred owner: real Web UI, WeChat daemon/service, and Markdown render conversion remain future product work; S1 did not fabricate render resources or fake workflows.

## Residual Risks

- `dayu.render` package-data resource completion remains deferred until a real renderer implementation owns actual resource files.
- Console-script binaries depend on editable/package installation state; this slice validates pyproject target import and module help regardless of whether editable scripts are installed.
