# PR 68 post-draft second manual full-repo review repair - AgentCodex

## 实际修复项

- 修复 `tests/host/test_public_tool_wiring_smoke.py` 的 public tool wiring smoke 断言：测试现在确认 mock tool result 已经通过 Host accept barrier 进入同一 Run 的 continuation，并确认后续 Run 只依赖对话连续性，不再要求 raw `TOOL_RESULT_ACCEPTED` event id 出现在 RunInputBuilder 初始输入中。
- 补齐 `tests/service/test_host_assembly.py` 的 Service assembly 边界测试：
  - `_render_headers`：缺 env key、空白 key、未解析占位符 fail-fast。
  - `_resolve_prompt_asset_path`：空字符串、绝对路径、`../` 逃逸 fail-fast。
  - `_tooling_options_from_discovery`：空 bundle 返回 `None`，有工具但 `source_refs` 为空 fail-fast。
  - `_tool_discovery_specs`：provider 同时缺 `import_path` 与 `entry_point` fail-fast，并覆盖 entry point 映射路径。
  - `_compactor_agent_policy_from_scene_inputs`：参数化覆盖 `max_iterations`、`fallback_mode`、`max_consecutive_failed_tool_batches` 缺失；保留既有 override `None` 测试。
- 低风险修复 `dayu/runtime/tools_discovery.py`：`_validate_provider_output` 内部重新校验并返回规范化 provider identity，调用方统一使用该规范化身份做重复检测与 report 构造。
- 补 `tests/runtime/test_tools_discovery.py`：覆盖 provider 输出空白 identity 在 output validation 阶段 fail-fast。
- 按测试 README 触发规则更新 `tests/README.md`，补充 runtime tools discovery 与 service host assembly 边界测试覆盖说明。

## test failure root cause 裁决

裁决为旧 smoke 断言过期，不修 production memory / run_input。

依据：

- `docs/host/design.md` 的 P12.5 / P9 memory 设计明确规定：`evidence_backed_facts` 只来自 accepted evidence refs 的 compaction-gated extraction；`TOOL_RESULT_ACCEPTED` 通过 accept barrier 记录 accepted evidence envelope，但不直接物化 stable evidence-backed fact。
- 当前 `dayu/host/memory.py` 对 `TOOL_RESULT_ACCEPTED` 的处理只推进 cursor，不生成 fact；已有 `tests/host/test_memory_projection.py::test_tool_result_accepted_does_not_project_evidence_backed_fact` 锁定该语义。
- 后续普通 Run 在未 compact 的短链路中依赖 recent raw turns / assistant conclusion 等 continuity，而不是要求 raw tool result event id 进入 stable memory block。因此原断言 `event_id=event-tool-result-accepted-` 属于旧契约残留。

## Deferred 项及理由

- `owner_host_instance_id=None` recovery blind spot：需要 Host dispatch/admission ownership contract 设计，本轮不碰 recovery / dispatch。
- `_promote_after_release PromotionResult` 语义、`_closeout_worker_startup_timeout` 诊断字段：非当前 P12.5 blocker。
- working assumptions、fact-candidate-only partial projection、compact budget estimate、semantic repair attempts、RAW_ASSISTANT_TURN、ensure_session idempotency、projection checkpoint CAS、memory snapshot CAS：转后续 memory / durable / context hardening。
- `_require_non_empty_text`、JSON helper、secret redaction、token estimator 等去重：属于大范围重构，本轮窄范围不做。
- runner_events re-export、filelock marker warning、engine_ingest 拆分、admission durable private import、schema version message：按总控要求 defer。

## 运行命令和结果

- `source .venv/bin/activate && pytest tests/host/test_public_tool_wiring_smoke.py::test_mock_tool_result_feeds_same_run_and_later_run_continuity -q`：1 passed。
- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py -q`：24 passed。
- `source .venv/bin/activate && pytest tests/runtime/test_tools_discovery.py -q`：10 passed。
- `source .venv/bin/activate && pytest tests/host/test_public_tool_wiring_smoke.py tests/service/test_host_assembly.py tests/runtime/test_tools_discovery.py -q`：36 passed。

## pyright 结果

- `source .venv/bin/activate && pyright dayu tests`：0 errors, 0 warnings, 0 informations。

## README 检查结论

- 命中 `tests/` 变更触发规则，已更新 `tests/README.md`。
- 未修改 `dayu/host/`、`dayu/service/`、`dayu/fins/`、`dayu/config/`、CLI/render 或分层装配入口文档职责范围内的稳定说明，因此其它 README 无需同步。

## 剩余风险

- 本轮没有跑全量 pytest，仅跑受影响测试文件与 `pyright dayu tests`。
- public tool wiring smoke 的旧 node id 已随测试名变更失效；新的测试名反映当前稳定契约。
