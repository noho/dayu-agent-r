# WU-SEMANTIC-OWNERSHIP-01 P3-I S1 controller validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P3-I - Public CLI/package entrypoints and terminal display watermark`
- Slice: `S1 - Public Package Entrypoints And README Truth`
- Gate: controller validation before code review
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p3-i-s1-implementation-codex.md`

## Controller scope audit

AgentCodex initially considered narrowing unrelated `dayu-cli write` README text after observing that command is not registered. The controller corrected scope during the implementation gate: S1 is limited to `dayu-web`, `dayu-wechat`, `dayu-render`, their package targets, help/import behavior, and README truth for those commands.

Post-correction diff audit confirms:

- `README.md` no longer changes the `write` workflow section body.
- Remaining top-level README changes remove or narrow WeChat/Web/render claims and keep the existing `write` bullet.
- `pyproject.toml` is unchanged.
- No Host, Service, Engine, Fins, or CLI terminal cursor code was changed in S1.

## Validation

Commands run by controller after scope correction and local quality tightening:

```bash
source .venv/bin/activate && pytest tests/cli/test_public_package_entrypoints.py -q
```

Result: `12 passed`.

```bash
source .venv/bin/activate && python -m dayu.web --help
source .venv/bin/activate && python -m dayu.wechat.main --help
source .venv/bin/activate && python -m dayu.render.render --help
```

Result: all passed with exit code `0`.

```bash
source .venv/bin/activate && dayu-web --help
source .venv/bin/activate && dayu-wechat --help
source .venv/bin/activate && dayu-render --help
```

Result: all installed console-script help commands passed with exit code `0`.

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Result: `0 errors, 0 warnings, 0 informations`.

```bash
git diff --check
```

Result: passed with no output.

```bash
rg -n "dayu-web|dayu-wechat|dayu-render" README.md
```

Result: every hit describes help/current diagnostic behavior or explicitly says the full Web UI, WeChat daemon/service, or Markdown conversion is unavailable.

## Propagation audit

- Fact source: `pyproject.toml` still declares `dayu-web = "dayu.web.__main__:main"`, `dayu-wechat = "dayu.wechat.main:main"`, and `dayu-render = "dayu.render.render:main"`.
- Producer/implementation: new `dayu.web`, `dayu.wechat`, and `dayu.render` packages provide the exact importable targets.
- Validation owner: `tests/cli/test_public_package_entrypoints.py` reads `pyproject.toml`, imports those targets, verifies `--help`, verifies module execution help, verifies non-help diagnostics, and verifies import does not load optional heavy dependencies.
- Distribution owner: setuptools package discovery already includes `dayu*`; no script target change was needed.
- Projection owner: `README.md`, `dayu/README.md`, and `tests/README.md` now describe the current package boundary and user-visible behavior without claiming unimplemented workflows as available.
- User-visible output: command help and diagnostics describe current capability limits without exposing Host / Engine internal facts as user-facing business facts.

## Residual risk

- Full Web UI, WeChat login/daemon/service, and Markdown render conversion remain unimplemented by design for this slice.
- `dayu.render` package-data resource files remain deferred until a future real renderer owner provides actual assets.

## Decision

S1 is ready for AgentMiMo and AgentDS code review.
