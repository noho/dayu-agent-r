# WU-CLI-01 / CLI-01-S2 Implementation Review Controller Adjudication

## Gate

- Work unit: WU-CLI-01
- Slice: CLI-01-S2
- Gate: implementation review controller adjudication
- Review artifacts:
  - `docs/reviews/wu-cli-01-s2-implementation-review-mimo.md`
  - `docs/reviews/wu-cli-01-s2-implementation-review-ds.md`
- Implementation report: `docs/reviews/wu-cli-01-s2-implementation-codex.md`

## Controller Verdict

结论：pass-with-fix。

两路 review 均确认 S2 scope、Service boundary、Host public API 使用、runtime config overlay、override merge、测试与 pyright 基本通过。但 review 暴露出 cancel race 与 watcher failure 可诊断性问题。总控接受下列 findings，进入 fix gate 后再 re-review。

## Accepted Findings

| ID | Severity | Finding | Controller decision |
|---|---|---|---|
| S2-IMPL-F01 | medium | `cancel_entrypoint_run_and_wait(...)` 在 `get_run` 与 watcher attach / `cancel_run` 之间存在 terminal race。 | accepted；若 initial `get_run` 已显示终态，应跳过 `cancel_run` 并走 terminal observation / outbox fallback。若 `cancel_run` 与终态竞争失败，也应尽量继续通过 public observation 取得 terminal，而不是直接丢弃已 attach watcher。 |
| S2-IMPL-F02 | medium | watcher drain failure 被静默忽略，且 watcher failure -> outbox fallback 路径无测试覆盖。 | accepted；应让 watcher failure 进入可诊断状态或 terminal result，不可静默丢弃；补 watcher failure 后仍能通过 public outbox fallback 返回 terminal 的测试。 |
| S2-IMPL-F03 | low | `ensure_or_create_entrypoint_session(...)` 的参数校验错误路径无测试覆盖。 | accepted；补充缺 `create_context`、缺 `create_client_request_id`、ensure 缺 `scope`、ensure 缺 `slot_key` 的 ValueError 测试。 |
| S2-IMPL-F04 | low | `_wait_for_terminal(...)` 无内部超时，caller 责任未写清。 | accepted as documentation/test-contract fix；在 public helper docstring 或 report 中明确 Service helper 不持有 timeout，调用方应通过 cancel / task cancellation / `asyncio.wait_for` 控制等待生命周期。 |

## Rejected / Deferred Findings

| Finding | Decision | Rationale |
|---|---|---|
| `_attach_watcher` 使用 `cast(ClosableHostEventIterator, ...)`。 | deferred-with-owner | Accepted plan 已要求 S2 在 Service 内定义窄 `ClosableHostEventIterator` Protocol 表达 `aclose()`；当前 Host 实现返回 async generator，运行时具备 `aclose()`。把 `Host.watch_session_events` public Protocol 返回类型改为 closable protocol 属于 Host public contract typing refinement，应另行设计，不阻塞 S2。 |

## Fix Gate Requirements

- 只修复 S2 accepted findings，不实现 S3-S7，不新增 CLI command / Fins direct / init。
- 继续只使用 Host public API / Protocol，不读取 Host durable internals。
- 修复后运行：
  - `source .venv/bin/activate && pytest tests/runtime/test_runtime_location.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py -q`
  - `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing -q`
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `git diff --check`
- 写 fix report：`docs/reviews/wu-cli-01-s2-implementation-fix-codex.md`。
