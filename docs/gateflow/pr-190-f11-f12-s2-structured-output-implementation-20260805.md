# PR 190 F11/F12 S2 Structured Output Implementation

## Gate metadata

- Gate：`implementation`，slice `S2 — Engine generic structured output 与 config capability`
- Work unit：PR 190 F11/F12 Interactive Memory 收口
- Branch：`codex/interactive-oracle`
- Required clean base：`c8be3e5184b8b797c59458027e991f0284cbb3b5`
- Observed HEAD：`c8be3e5184b8b797c59458027e991f0284cbb3b5`
- Artifact path：`docs/gateflow/pr-190-f11-f12-s2-structured-output-implementation-20260805.md`
- Completion status：**S2 code-review fix implementation complete**
- Current gate：`S2 code-review fix complete / controller re-review dispatch pending`
- Next entry point：由总控且仅由总控派发独立 re-review
- Review dispatch ownership：implementation agent 不派发 reviewer；本轮没有启动
  reviewer、子 Agent 或 tmux Agent，也不执行 acceptance

## Code-review fix gate update

本轮完整读取并以以下 durable inputs 为准：

- `docs/gateflow/pr-190-f11-f12-s2-code-review-adjudication-20260805.md`
- `docs/reviews/pr-190-f11-f12-s2-mimo-code-review-20260805.md`
- `docs/reviews/pr-190-f11-f12-s2-ds-code-review-20260805.md`
- 本 artifact 与当前完整 S2 diff

Reviewer interference 已按总控裁决隔离：MiMo 在原 review 中执行的
`git stash` / `git stash pop` 违反只读约束；该窗口内 MiMo/DeepSeek 观察到的
HEAD-only import、旧 hash 与非隔离 baseline test 结果全部作废。稳定工作树的 raw-byte
hash 仍为 `models.json=dc924f842be81599c00606dae0cbe464d6f766147581d4bbb4167e83044e5f2b`
与 `manifest=0e1ec1047062eecbe6dc8eae89139460058219c881ce4d7960e6c96c7a182469`。
本 fix gate 没有执行任何 Git state mutation。

三项裁决已按 owner boundary 关闭：

1. `DS-LOW-01`：`build_request_payload.structured_output` 保留合法类型
   `StructuredOutputRequest | None`，移除 default；production caller 与全部 direct test
   caller 都显式传入 typed request 或 `None`。signature owner test 锁定 required
   keyword-only contract，不增加 wrapper、fallback 或 overload。
2. `DS-LOW-02`：`tests/service/test_host_assembly.py` 在 Service mechanical assembly
   boundary 比较 runtime config enum 与 Engine enum 的完整 value 集合，并逐个 runtime
   value 构造 Engine enum。runtime 不 import Engine，production 不新增 helper，也没有
   第三份 enum。
3. `S1 deterministic import-boundary regression`：冻结 plan/design 已明确 Host Tool Trace
   复用 Engine canonical `SuccessfulRunnerResponseIdentity`。测试 policy 从 basename
   收敛为精确 workspace-relative file path，保留原有允许文件，并只新增
   `dayu/host/durable/tool_trace.py` 与
   `dayu/host/tool_trace_analysis_contracts.py`；没有复制 identity 或删除合法 import。

Fix 后稳定验证：

- 指定两个 Host nodes：`2 passed`。
- owner/payload 小范围回归：`35 passed`；局部 pyright：0 error。
- S2 affected suite：稳定复跑 `1361 passed, 3 warnings`。
- 首轮 affected suite 曾出现
  `test_open_host_active_cancel_watchdog_public_watch_observes_cancelled` 单次时序失败；该文件
  的 S2 diff 只有 `RunnerSpec.structured_output_capability=NONE` 机械迁移，失败事实是 cancel
  token recorder 观察到两次调用。该 node 隔离复跑 PASS，随后完整 affected suite 稳定
  1361 PASS，因此不把非同源、不可复现观察升级为本 fix finding。
- full `tests/engine`：`602 passed`。
- `pyright dayu tests utils`：PASS，exit 0。
- Ruff、compileall、JSON parse、raw-byte hashes 与 `git diff --check`：PASS。
- 受影响 production files branch coverage 全部 `>=80%`，最低
  `dayu/engine/runners/openai/runner.py=80%`，总计 90%。

README decision：本 fix 不改变 S2 已记录的公开 contract 或用户工作流，既有
`dayu/engine/README.md`、`dayu/config/README.md` 与 `dayu/README.md` 无需追加；已读取
`tests/README.md`，新增 owner assertions 未改变测试分层、运行入口或 fixture system，故不更新。

## Preflight and motivation judgment

- 根 `AGENTS.md`、Gateflow skill、accepted plan/checkpoints、S0 design truth、
  Engine/config/Service/Host projection 代码及相关 README 自身更新约束均已读取。
- preflight 时工作树 clean，当前分支不是 protected trunk，HEAD 精确匹配要求基线。
- S2 动机成立：原基线没有 provider-neutral structured-output request、Runner
  capability 或 generic `response_format` projection。若在 Host、provider-name 分支或
  extra payload 中补偿，会产生多 owner、隐式推断与静默降级。
- 正确 owner chain 固定为：

```text
models.json
  -> runtime ConfigLoader typed capability
  -> Service mechanical RunnerSpec projection
  -> AgentRunRequest explicit typed request
  -> AsyncRunner required call parameter
  -> OpenAI-compatible response_format projection
```

## Authoritative wording clarification

实现前曾把初始任务 wording 中“request 包含 mode/digest”理解为要扩张 public request
字段，因此短暂停止并记录 owner conflict。总控随后明确裁决：

- 唯一 contract 真源是 `docs/engine/design.md:112-123,257-265` 与 accepted plan；
- `StructuredOutputRequest` 保持两个 typed variant 的封闭联合；
- `JsonObjectStructuredOutputRequest` 无字段；
- `JsonSchemaStructuredOutputRequest` 精确且仅有 `name/schema/strict`；
- mode 由 concrete variant 类型唯一表达，不新增 stored `mode`；
- request 不新增 `digest`；
- “schema name/digest 同源”只要求测试从同一个 canonical schema
  bytes/structure 核对 transport identity，不建立第二持久字段。

最终实现严格采用该裁决。schema mapping 原样进入 transport；owner test 从同一
canonical structure 计算 digest 前后核对，并断言 transport 持有同一 schema object。

## Implementation summary

### Engine typed contract and validation owner

- 新增 `dayu/engine/contracts/structured_output.py`：
  - `StructuredOutputCapability` 三值 `none/json_object/json_schema`；
  - 无字段 JSON object variant；
  - 仅含 `name/schema/strict` 的 JSON Schema variant；
  - name 非空且无首尾空白、strict 必须为 bool、schema 必须是严格 JSON mapping，
    拒绝非字符串 key、非 JSON 值与非有限浮点数；
  - 唯一 capability/request matrix validator。
- `RunnerSpec.structured_output_capability` 是 required typed field。
- `AgentRunRequest.structured_output` 是显式 typed field；request construction 在
  Agent loop 与 outbound HTTP 之前通过同一 validator fail fast。
- `AsyncRunner.call` 增加 required、无 default、keyword-only `structured_output`；
  Protocol、唯一实现、Agent 唯一 production call site 和全部 fake/stub/direct call
  同一未提交 diff 迁移，没有 default 遮蔽漏传。
- public Engine/contracts exports 同步公开两个 variant、capability、union 与 validator。

固定矩阵：

| capability | `None` | JSON object request | JSON Schema request |
| --- | --- | --- | --- |
| `none` | allow | reject | reject |
| `json_object` | allow | allow | reject |
| `json_schema` | allow | allow | allow |

### OpenAI-compatible transport

- `None` 不写 `response_format`。
- JSON object 精确投影为 `{"type":"json_object"}`。
- JSON Schema 精确投影为
  `{"type":"json_schema","json_schema":{"name":...,"strict":...,"schema":...}}`。
- structured output 使用独立 top-level channel，不进入 provider extension、header、
  metadata 或 `extra_body`。
- 不读 provider/model 名称，不 probe，不 retry/downgrade；provider 拒绝后保留原失败。

### Config and projection

- `ModelConfig` 新增 required、fail-fast enum；runtime 层使用层中立 enum，不反向
  import Engine。
- Service 只按 enum value 机械投影到 Engine `StructuredOutputCapability`。
- Host effective execution config projection 从同一个 `RunnerSpec` field 序列化/恢复。
- package catalog：两个 DeepSeek base records 为 `json_object`；MiMo 与其它无直接
  capability 证据的 base records 为 `none`；派生记录继承父值；当前没有
  `json_schema` record。

### Publication integrity

- `dayu/config/models.json` raw-byte SHA256：
  `dc924f842be81599c00606dae0cbe464d6f766147581d4bbb4167e83044e5f2b`
- 只更新 workspace manifest 中 `config/models.json` 的 content digest。
- 稳定 manifest 后 raw-byte SHA256：
  `0e1ec1047062eecbe6dc8eae89139460058219c881ce4d7960e6c96c7a182469`
- 只把该最终 manifest digest 同步到 frozen CLI smoke constant。

## Exact out-of-owner-list typed migrations

Accepted plan 要求 required signature/field 在同一 diff 全仓迁移。以下 path 不扩张
production scope，只做 required `structured_output=None`、required
`StructuredOutputCapability.NONE`、fake/stub typed parameter、protocol surface expectation
或直接相关 projection/export assertion；没有加入行为 fallback：

```text
tests/engine/runners/openai/_factories.py
tests/engine/runners/openai/test_cancellation_boundaries.py
tests/engine/runners/openai/test_cancellation_no_done_event.py
tests/engine/runners/openai/test_http_error_event.py
tests/engine/runners/openai/test_http_unknown_status_runner.py
tests/engine/runners/openai/test_no_extra_payload_bag.py
tests/engine/runners/openai/test_request_identity.py
tests/engine/runners/openai/test_response_cleanup_race.py
tests/engine/runners/openai/test_retry_backoff.py
tests/engine/runners/openai/test_runner_b3_extra.py
tests/engine/runners/openai/test_runner_diagnostics.py
tests/engine/runners/openai/test_stream_idle.py
tests/engine/runners/openai/test_streaming_capability_and_content_type.py
tests/engine/test_agent_phase2.py
tests/engine/test_agent_phase3_tool_call.py
tests/engine/test_metadata_boundary.py
tests/engine/test_package_exports.py
tests/host/fake_compaction.py
tests/host/public_smoke_support.py
tests/host/test_active_cancel_dispatch.py
tests/host/test_admission_multiprocess.py
tests/host/test_admission_queue.py
tests/host/test_command_handle.py
tests/host/test_compaction_cancellation_scope.py
tests/host/test_dispatch_scheduler.py
tests/host/test_effective_execution_config.py
tests/host/test_engine_ingest_mapping.py
tests/host/test_host_activity_event_projection.py
tests/host/test_local_proxy_engine_ingest.py
tests/host/test_logging.py
tests/host/test_open_host_runtime.py
tests/host/test_per_run_tool_selection.py
tests/host/test_phase5_local_execution_integration.py
tests/host/test_phase6_toolruntime_integration.py
tests/host/test_phase7_waiting_integration.py
tests/host/test_proactive_compaction_operation.py
tests/host/test_projection_read_model.py
tests/host/test_public_contracts.py
tests/host/test_public_host_admin.py
tests/host/test_public_lifecycle_smoke.py
tests/host/test_public_open_host_options.py
tests/host/test_public_retry_replay.py
tests/host/test_public_session_api.py
tests/host/test_resolve_wait_command.py
tests/host/test_run_input_builder.py
tests/host/test_storage_maintenance.py
tests/host/test_storage_usage_report.py
tests/host/test_submit_followup_public_contract.py
tests/host/test_tool_trace_queries.py
tests/host/test_watch_session_events.py
utils/smoke_async_agent_providers.py
```

`utils/smoke_async_agent_providers.py` 是非 production smoke helper；它显式携带 typed
capability，DeepSeek 为 `json_object`，MiMo/Gemini/Qwen 为 `none`，不按 provider
名称推断。没有修改 accepted S2 list 外的 production 文件。

## Owner tests

Owner tests 覆盖：

- 两个 request variant 的严格不变量与 capability 三值；
- 六个合法矩阵组合和三个非法组合；
- `RunnerSpec` capability required、Protocol/实现 `structured_output` required 且无 default；
- Agent 每个 iteration 原样透传 request；
- `None`、JSON object、JSON Schema exact payload；
- canonical schema name/structure/digest transport identity 同源，且 request 无 digest field；
- structured output 不进入 extra bag；
- provider 400 拒绝 JSON Schema 时只发送一次，不 downgrade/retry；
- missing/unknown config enum fail fast，继承与 Service/Host projection 同源；
- DeepSeek=`json_object`、MiMo/其它=`none`、catalog 无 `json_schema`；
- package exports 与 publication manifest digest。

## Validation evidence

- Modified tests + supplemental payload branch tests：`1337 passed, 3 warnings`。
- Latest contract/protocol/payload focused rerun：`85 passed`。
- CLI publication suite：`199 passed, 5 skipped, 3 warnings`。
- Full `tests/engine`：`601 passed`。
- `pyright dayu tests utils`：`0 errors, 0 warnings, 0 informations`。
- `ruff check` on all modified Python files：PASS。
- `compileall` on affected production/tests/smoke helper：PASS。
- `jq -e` validation on models catalog and workspace manifest：PASS。
- raw-byte SHA256 validation：PASS。
- `git diff --check`：PASS。

Branch coverage for every modified production Python file：

| file | branch coverage |
| --- | ---: |
| `dayu/engine/__init__.py` | 100% |
| `dayu/engine/agent.py` | 88% |
| `dayu/engine/contracts/__init__.py` | 100% |
| `dayu/engine/contracts/agent_run.py` | 98% |
| `dayu/engine/contracts/runner.py` | 100% |
| `dayu/engine/contracts/runner_spec.py` | 98% |
| `dayu/engine/contracts/structured_output.py` | 82% |
| `dayu/engine/runners/openai/payload.py` | 83% |
| `dayu/engine/runners/openai/runner.py` | 80% |
| `dayu/host/_execution_config_projection.py` | 91% |
| `dayu/runtime/config_loader.py` | 95% |
| `dayu/service/host_assembly.py` | 93% |

Coverage command report total：90%。三个 warning 都来自 `edgar` dependency 的既有
deprecation warning，不是本 slice 新行为。

## README decision

- 更新 `dayu/engine/README.md`：公开 request/capability、required Runner call、matrix、
  transport 与 no-extra/no-downgrade 规则。
- 更新 `dayu/config/README.md`：required enum、inheritance、catalog matrix 与机械投影。
- 更新 `dayu/README.md`：只补充稳定跨层 request flow 摘要。
- 不更新 Service README：没有改变 Service 的公开装配职责，只在既有 projection owner
  中机械映射新 typed field。
- 不更新 tests README：没有新增 test layer、fixture system 或测试运行入口。
- 不更新根 README：没有用户可见 CLI/安装/工作区流程变化。

## Residual risks and next gate

- `fixed in current S2`：generic typed request/capability、严格矩阵、required call
  migration、exact OpenAI-compatible transport、config catalog/projection、publication hash。
- `covered by later approved S3`：Host compact v3 schema/prompt/parser、compactor 按
  capability 选择 request、Host-owned canonical schema manifest/digest。
- `covered by later approved S4`：真实 Mimo/DeepSeek endpoint/model/options conformance。
- 当前 slice 不包含 prompt/Host compact v3，也没有为未来 provider 添加 probe、special
  case、retry 或 downgrade。
- `fixed in current review-fix gate`：DS-LOW-01、DS-LOW-02 与 S1 deterministic
  import-boundary regression。
- 下一 gate 是独立 re-review，但 reviewer 派发只归总控所有。implementation agent
  在本 artifact 完成后停在 idle，不启动 reviewer，也不提前做 controller adjudication
  或 acceptance。

未 stage、commit 或 push。
