# WU-CLI-01 / CLI-01-S2 implementation report

## Scope

本次只实现 CLI-01-S2：runtime location 显式 config overlay，以及 prompt / interactive 可复用的 Agent entrypoint Service boundary。未实现 S3 prompt command、S4 interactive command、S5-S7 Fins/init，也未提交、push 或开 PR。

## 改动

- `dayu/runtime/location.py`
  - `resolve_runtime_locations(...)` 新增 keyword-only `explicit_config_overlay_dir: Path | None = None`。
  - `None` 时保持默认 `workspace/config` 探测行为；显式路径必须存在且为目录，否则抛 `RuntimeLocationError`。

- `dayu/service/host_assembly.py`
  - 新增 `ServiceRunOverrides`。
  - 新增 `compose_submit_followup_request_with_overrides(...)`，在 host assembly 真源内把单次 `temperature` 与 AgentPolicy override 合并为完整 `RunnerCallOptions` / `AgentPolicy`。
  - 保持既有 `compose_submit_followup_request(...)` 行为不变。

- `dayu/service/entrypoint_runtime.py`
  - 新增 `EntrypointRuntimeRequest/Result`、`EntrypointTurnRequest`、`EntrypointCancelRequest`、`EntrypointRunTerminalResult` 与 terminal source enum。
  - 新增 `prepare_entrypoint_runtime(...)`、`ensure_or_create_entrypoint_session(...)`、`submit_entrypoint_turn_and_wait(...)`、`cancel_entrypoint_run_and_wait(...)`。
  - `submit_entrypoint_turn_and_wait(...)` 在 submit 前 attach `watch_session_events(session_id)`，按 `accepted_run_id` 过滤 terminal。
  - watcher 未命中时只用 public `get_run(...)` + `read_outbox_terminal_items(...)` fallback，覆盖 `OutboxTerminalCursor`、`seen_terminal_event_ids`、`limit=50`、`CAUGHT_UP/LAGGED/FAILED`、`has_more` 与 caught-up-without-match。
  - `cancel_entrypoint_run_and_wait(...)` 构造 Host public `CancelRunRequest(context, client_request_id, reason, mode)`；未安装 signal handler。

- Tests / README
  - 扩展 `tests/runtime/test_runtime_location.py`、`tests/service/test_host_assembly.py`。
  - 新增 `tests/service/test_entrypoint_runtime.py`。
  - 更新 `dayu/service/README.md`、`tests/README.md`、`dayu/README.md`，只记录当前已实现边界。

## 验证

- `source .venv/bin/activate && pytest tests/runtime/test_runtime_location.py tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime.py -q`
  - 结果：`64 passed`。
  - 备注：出现 3 条 `edgar` 依赖 deprecation warnings，与本次实现无关。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`
  - 结果：通过。
- `rg -n "[ \t]+$" dayu/service/entrypoint_runtime.py tests/service/test_entrypoint_runtime.py docs/reviews/wu-cli-01-s2-implementation-codex.md`
  - 结果：无输出；用于补充检查 untracked 新增文件的行尾空白。

## README 判断

- `dayu/service/README.md`：新增 Service public helper，属于该 README 当前职责，已更新。
- `tests/README.md`：新增 Service entrypoint runtime 测试与 runtime location 显式 overlay 测试事实，已更新。
- `dayu/README.md`：本次触及 Service / Host entrypoint 装配边界，按总览职责补充已实现边界。
- 未检查或修改 Host / Engine / Fins / Config README：本次未改对应包。

## 风险 / 未覆盖项

- 当前 `EntrypointRuntimeRequest.context_slot_values` 输入面按 plan 保留 `JsonValue`，但进入当前 `ScenePrepareRequest` 前必须校验为字符串；非字符串 slot 会 fail fast。
- `cancel_entrypoint_run_and_wait(...)` 是独立 cancel wait helper，会在 cancel 前 attach watcher；后续 UI adapter 若要复用 submit turn 已 attach watcher，可在 S3/S4 再接入同一等待状态。
- 未做真实 Host / provider / CLI smoke；S2 范围用 mocked Host public Protocol 验证 Service boundary，真实 CLI 命令在后续 slices 实现。
