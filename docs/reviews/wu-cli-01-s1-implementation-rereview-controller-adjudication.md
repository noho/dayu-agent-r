# WU-CLI-01 / CLI-01-S1 Implementation Re-Review Controller Adjudication

## Gate

- Work unit: WU-CLI-01
- Slice: CLI-01-S1
- Gate: implementation re-review controller adjudication
- Re-review artifacts:
  - `docs/reviews/wu-cli-01-s1-implementation-rereview-mimo.md`
  - `docs/reviews/wu-cli-01-s1-implementation-rereview-ds.md`
- Fix report: `docs/reviews/wu-cli-01-s1-implementation-fix-codex.md`

## Controller Verdict

结论：pass。

两路 re-review 均确认 accepted findings `S1-IMPL-F01` 与 `S1-IMPL-F02` 已关闭，fix 未引入新问题，CLI-01-S1 scope 未扩大。

## Closed Findings

| ID | Controller status | Evidence |
|---|---|---|
| S1-IMPL-F01 | closed | `CommandSubparserRegistry` Protocol 已隔离 argparse subparser registry，新增范围内 `_SubParsersAction` 零残留，且无 `Any` / `object` 逃逸。 |
| S1-IMPL-F02 | closed | runner 缺失路径输出 stderr 内部诊断，`test_main_reports_missing_command_runner` 覆盖退出码与诊断文本。 |

## Scope Check

- 未实现 CLI-01-S2 到 CLI-01-S7。
- `dayu/cli` 未 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.fins` / `dayu.ui`。
- 命令执行仍是 S1 placeholder，不触达 Host / Fins business execution。
- 本轮仍是迁移旧 CLI 的用户可见 command surface / parser / help 语义，不复制旧 dayu-agent 实现代码。

## Verification

- `source .venv/bin/activate && pytest tests/cli -q`：25 passed。
- `source .venv/bin/activate && pytest tests/cli --cov=dayu.cli --cov-report=term-missing -q`：25 passed，总覆盖率 99%。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

## Next Gate

CLI-01-S1 可以提交为 accepted implementation commit。提交后进入 CLI-01-S2 implementation gate。
