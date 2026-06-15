# WU-CLI-01 / CLI-01-S2 implementation fix report

## Scope

本次只修复 CLI-01-S2 implementation review controller accepted findings。未实现 S3-S7，未新增 CLI command、Fins direct、init，未读取 Host durable internals，未提交、push 或开 PR。

## 修复内容

- S2-IMPL-F01：修复 `cancel_entrypoint_run_and_wait(...)` 的 terminal race。
  - 初始 `get_run(...)` 已终态时跳过 `cancel_run(...)`，直接通过 public `get_run(...)` / `read_outbox_terminal_items(...)` terminal fallback 返回结果。
  - `cancel_run(...)` 抛 `HostApiError` 后，继续用 public `get_run(...)` 判断是否已经终态；若已终态则保留已 attach watcher 并继续 terminal wait，若仍非终态则原样抛出 cancel 错误。

- S2-IMPL-F02：修复 watcher drain failure 静默丢弃。
  - `_TerminalObservationState` 记录首个 watcher drain failure 诊断。
  - `EntrypointRunTerminalResult` 新增 `watcher_failure_message: str | None`，outbox fallback 成功时把 watcher failure 带给调用方。
  - outbox projection error / caught-up-without-match error 也会附带 watcher failure 诊断。
  - 新增 watcher failure 后仍通过 public outbox fallback 返回 terminal 的测试。

- S2-IMPL-F03：补齐 `ensure_or_create_entrypoint_session(...)` 参数校验错误路径测试。
  - 覆盖 create 缺 `create_context`。
  - 覆盖 create 缺 `create_client_request_id`。
  - 覆盖 ensure 缺 `scope`。
  - 覆盖 ensure 缺 `slot_key`。

- S2-IMPL-F04：明确等待生命周期契约。
  - `submit_entrypoint_turn_and_wait(...)`、`cancel_entrypoint_run_and_wait(...)` 与 `_wait_for_terminal(...)` docstring 明确：Service helper 不持有内部 timeout；调用方应通过 task cancellation、`asyncio.wait_for(...)` 或显式 cancel 请求控制等待生命周期。
  - 同步更新 `dayu/service/README.md`、`dayu/README.md` 与 `tests/README.md`，只记录当前已实现边界。

## 验证

- `source .venv/bin/activate && pytest tests/runtime/test_runtime_location.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py -q`
  - 结果：`71 passed`。
  - 备注：3 条 `edgar` deprecation warnings，与本次修复无关。

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py --cov=dayu.service.entrypoint_runtime --cov-report=term-missing -q`
  - 结果：`18 passed`，`dayu/service/entrypoint_runtime.py` 覆盖率 97%。
  - 备注：3 条 `edgar` deprecation warnings，与本次修复无关。

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`。
  - 备注：pyright 提示存在新版本 `v1.1.410`，不属于项目类型错误。

- `git diff --check`
  - 结果：通过，无输出。

## README 判断

- `dayu/service/README.md`：本次修改 Service public helper 行为与契约，已同步 watcher failure 诊断、cancel terminal race 处理与 caller-owned timeout。
- `tests/README.md`：本次新增 Service 测试覆盖，已同步 entrypoint runtime 覆盖范围。
- `dayu/README.md`：本次涉及 Service / Host entrypoint 边界描述，已同步总览级 Service helper 行为。
- 未修改 Host / Engine / Fins / Config 包，因此未更新对应 README。

## 剩余风险

- Deferred-with-owner：`_attach_watcher` 仍保留 `cast(ClosableHostEventIterator, ...)`，按 controller adjudication 属于 Host public contract typing refinement，不在本 fix gate 处理。
- Covered by later approved slice：本轮仍未做真实 CLI prompt / interactive smoke；S2 范围只用 mocked Host public Protocol 验证 Service boundary，真实 CLI command path 留给 S3 / S4。
- Fixed in current slice：watcher failure 不再静默丢弃；若 fallback 成功，terminal result 带 `watcher_failure_message`，若 fallback 失败，Service error 带同一诊断。
