# WU-CLI-01 / CLI-01-S2 Implementation Re-Review Controller Adjudication

## Gate

- Work unit: WU-CLI-01
- Slice: CLI-01-S2
- Gate: implementation re-review controller adjudication
- Re-review artifacts:
  - `docs/reviews/wu-cli-01-s2-implementation-rereview-mimo.md`
  - `docs/reviews/wu-cli-01-s2-implementation-rereview-ds.md`
- Fix report: `docs/reviews/wu-cli-01-s2-implementation-fix-codex.md`

## Controller Verdict

结论：pass。

两路 re-review 均确认 accepted findings `S2-IMPL-F01` 至 `S2-IMPL-F04` 已关闭，fix 未引入新问题，S2 scope 未扩大。

## Closed Findings

| ID | Controller status | Evidence |
|---|---|---|
| S2-IMPL-F01 | closed | initial `get_run(...)` 已终态时跳过 `cancel_run(...)`；`cancel_run(...)` 与终态竞争失败时继续 public terminal observation / outbox fallback；均有测试覆盖。 |
| S2-IMPL-F02 | closed | watcher failure 不再静默丢弃，diagnostic 进入 terminal result / observation error；watcher failure -> outbox fallback 有测试覆盖。 |
| S2-IMPL-F03 | closed | `ensure_or_create_entrypoint_session(...)` 的 create 缺 context、create 缺 client_request_id、ensure 缺 scope、ensure 缺 slot_key 四类错误路径均有测试。 |
| S2-IMPL-F04 | closed | submit / cancel wait helper docstring 和 README 均明确 caller-owned timeout contract。 |

## Scope Check

- 未实现 CLI-01-S3 到 CLI-01-S7。
- 未新增 CLI command / Fins direct / init。
- `dayu.service.entrypoint_runtime` 不读取 Host durable internals，只使用 Host public API / Protocol。
- Deferred Host watch return typing 未在本 slice 修改，符合 controller adjudication。

## Verification

- `source .venv/bin/activate && pytest tests/runtime/test_runtime_location.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py -q`：71 passed，3 条 edgar deprecation warnings。
- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing -q`：18 passed，`entrypoint_runtime.py` 覆盖率 97%。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

## Next Gate

CLI-01-S2 可以提交为 accepted implementation commit。提交后进入 CLI-01-S3 implementation gate。
