# WU-SEMANTIC-OWNERSHIP-01 Umbrella Aggregate Regression Accepted-Finding Fix Plan

## 0. Gate identity / verdict

- 状态：`PLAN_ONLY / LOCAL_TRUST_CORRECTED / DUAL_PLAN_REVIEW_PENDING / IMPLEMENTATION_NOT_AUTHORIZED`。
- umbrella：`WU-SEMANTIC-OWNERSHIP-01`。本计划只处理既有 umbrella aggregate regression 的 Controller accepted findings，不创建新 WU，不改变原 WU 的目标、设计真源或 residual destination。
- 当前 correction gate 基线：branch `phaseflow/host-issues-control`；HEAD `ffbf48c2cf5f701c627fda1ebcce7aa1813383ab`；aggregate parent 仍为 `3410d7422655c56bdf13c643f77c27f40b9d4550`。
- 本次 local-trust correction 的 entry plan SHA-256 已精确核对为 `7e91421b8bc8c442dcf72e94c20eb84d4f27f2b9878b427481448d6f2f4ea714`。本 gate 只允许修改 `docs/host/design.md`、`docs/ui/design.md` 与本文件，并新建 `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-correction-codex.md`；`docs/engine/design.md` 经直接核对无需修改。不得修改 product、test、README、workflow、control、其它 review / Controller artifact；不得 implementation、stage、commit、push、开 PR、运行 implementation tests、启动 subagent/reviewer 或 aggregate deepreview。
- 当前三个 Slice 1 test delta 必须按 correction entry SHA-256 原样保护：`tests/service/test_host_admin.py`=`5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db`，`tests/tools/web/test_smoke_web_ci.py`=`86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3`，`tests/host/test_public_compact_smoke.py`=`f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169`。本 plan correction 不重写、格式化或运行这些测试。
- 本计划固定三个 implementation slices，精确关闭 `AR-F01`—`AR-F05`。`AR-F06` 保持 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，`AR-F07` 保持 `PENDING_RELEASE_BLOCKER`。
- `S1-SEC-F01` 按 2026-07-19 用户产品裁决关闭为 no-code blocker：本地 Config 与 Host SQLite / EventLog 是同一受信任产品域，内部持久化 resolved provider headers / API key 不要求 production redesign；Tool Trace、audit、public / LLM-facing projection、日志、diff 与 review surface 仍要求 secret 明文为零。
- 计划只有在 AgentMiMo 与 AgentDS 对本次完整修订版做双路完整 plan review、AgentCodex修复全部 accepted plan findings、两路完整 re-review 均通过，并由 Controller 明确接受后，才可恢复 Slice 1 implementation validation。

## 1. Source of truth 与已核对证据

本计划原始 accepted 版本已读取下列真源；本次 correction 又严格按用户指定顺序完整重读 `AGENTS.md`、两份 control、overdesign discussion、Host / Engine / Tool / Fins / UI 五份 design，随后完整读取 user-decision record、prior evidence / adjudication、两路 corrected design-truth reviews、accepted aggregate plan与其 commit validation、Slice 1 authorization / implementation artifact及五份 stop adjudication。精确读取清单与 SHA-256 记录在本 gate artifact。裁决优先级如下：

1. `AGENTS.md`。
2. `docs/host/issues-implementation-control.md` 当前工作区状态，尤其 current gate、aggregate adjudication 与 next-entry condition。
3. `docs/phaseflow-umbrella-optimization-control.md`。
4. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`。
5. 五份永久 design 真源：
   - `docs/host/design.md`
   - `docs/engine/design.md`
   - `docs/tool/design.md`
   - `docs/fins/design.md`
   - `docs/ui/design.md`
6. `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`，尤其 aggregate regression、security、deferred/no-code 与 closeout gates。
7. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md` 的 fresh command/evidence ledger。
8. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-controller-adjudication.md` 的最终 finding disposition。
9. `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-controller-adjudication.md` 对 `AR-PLAN-PF01..02` 的唯一本轮 plan-fix 授权；该文档已完整读取，SHA-256 为 `a5876c47c38c3d80091e20e7958932af8cdf2430f80ef8ee96e9b40a647eaa06`。
10. 当前 HEAD 代码、测试、配置与 import graph。历史 artifact 只能证明历史运行；与当前代码冲突时，以当前代码和 Controller adjudication 为准。

11. 本次最高优先级 correction authority：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-user-decision-controller-record.md`，SHA-256=`4a75899fbdb8244d93f1633b0be3f36e65d2ae211a3211f57f326289f6c3f12b`。它 supersede 旧的“Host 不接收 API key 明文 / EventLog 必须零 headers”设计冲突与 `S1-SEC-F01` production redesign 建议，但不 supersede Tool Trace、audit、public / LLM-facing projection 与日志的零明文要求。

当前 correction 的 owner 结论是：ConfigLoader 仍只产生 typed config；Service / execution environment 解析 secret 并构造 resolved typed `RunnerSpec`；Host admission 持久化 exact effective execution canonical fact，dispatch / retry / replay / recovery 恢复该内部 truth；每个 Tool Trace、audit、HostEvent、memory / compact、runner-input / observation 与 log projection owner分别做显式安全字段选择。禁止 Host-safe / Engine-only split、header descriptor、secret resolver callback、secret manager或统一 tool authorization framework；本计划不扩张 CLI init secret 存储，也不进入 Issues 142、151、175、177、178。

以下清单是原始 plan-fix gate 的历史 protection baseline，不替代本次 correction artifact 记录的 fresh workspace baseline；其中所有 Controller-owned / pre-existing changes 继续不得被修改或 stage：

```text
 M  93dd662e755b0f7bbfc8ad82045bc54ed61b94d7bf3df22f14c385b242e56100  docs/host/issues-implementation-control.md
??  eb6528c2c1e59d4791a62b5cbb5f90fe84d517db368cd2cae4e51da253cacb11  docs/reviews/wu-semantic-ownership-01-aggregate-regression-codex.md
??  73dfecd1aed86ca59c44d6b40c012add309b261539b8f25d129a728ae2942539  docs/reviews/wu-semantic-ownership-01-aggregate-regression-controller-adjudication.md
??  bddc028b58eda529a295e70fa6652613265c55b32af511fb7e446db16037a4d4  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-controller-validation.md
??  a5876c47c38c3d80091e20e7958932af8cdf2430f80ef8ee96e9b40a647eaa06  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-controller-adjudication.md
??  94f315701dfe2d4ff432c60615dfd5f93c2615699462c59607c2a1bcafb6e615  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-ds.md
??  2cab2ad9d1348a9f934f86857e3442895a3442149f343d29a4dc2d34aeaedb36  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo-cleanroom.md
??  2cb0496819ac6709d3d53d85fb27f468b3ce790a0628f9b29d8645713de1cf20  docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-plan-review-mimo.md
??  03c41be0313394b2c8cf3e8ab2309a09665668545d4b7e7a1682ffa201a498ea  docs/reviews/wu-semantic-ownership-01-r12-accepted-implementation-commit-controller-validation.md
```

## 2. 第一性原理判断与 owner adjudication

### 2.1 动机成立

Aggregate regression 不是重复验证。R01—R12 的 accepted evidence 只证明各自当时的 slice tree，不能证明最终整合树的全量测试顺序、跨层 import、当前 artifact schema、逐文件 coverage 或真实 Windows runner。当前 direct evidence 已稳定复现五组本地 actionable defects，因此不能用历史 sub-WU PASS 覆盖本轮失败，也不能提前进入 aggregate deepreview。

### 2.2 Findings closure matrix

| ID | 当前代码直接证据与唯一 owner | 本计划 disposition |
| --- | --- | --- |
| AR-F01 | `tests/service/test_host_admin.py::_write_host_runtime` 写出的 current host runtime profile 缺少 `ConfigLoader` 已要求的 `wait_poller_policy`；这是 test fixture schema owner 缺陷，不是 product loader 容错缺陷 | Slice 1 只修 test fixture；禁止给 production 加默认值/fallback |
| AR-F02 | Service 直接 import `dayu.fins.direct_stream` 与 `dayu.fins.tools._ingestion_tool_helpers`；现有 Service allowlist 已允许 `dayu.fins.direct_events` 与 `dayu.fins.ingestion`，故问题是 Fins public contract owner 放错边界，不是 allowlist 太窄 | Slice 2 做一次物理 owner migration；禁止扩大 allowlist、兼容 re-export、lazy import、duplicate enum/protocol |
| AR-F03 | `utils/smoke_web_ci.py::main` 的 standalone `configure_root=True` 是 operator logging 语义；同进程测试直接调用 `main` 后未恢复全局 logger state，导致后续两个 node 顺序依赖失败 | Slice 1 只在 `tests/tools/web/test_smoke_web_ci.py` 增加 in-process harness isolation；standalone product logging 零改动 |
| AR-F04 | current compactor 成功发布 `context_compaction` schema v3 artifact；测试仍猜 `accepted_candidate.candidate_id == llm-compact:{run_id}`。Current runner-call manifest 已发布 `host_run_id`、`runner_call_kind=compactor_proposal` 及 `compactor_identity.compaction_request_digest`，compact artifact 发布同一 `compaction_request_digest` | Slice 1 用 manifest run identity -> request digest -> compact artifact digest equality 的唯一关联；禁止恢复 candidate_id、raw guess、fallback 或 loose scan |
| AR-F05 | aggregate parent 到当前树的 219 个现存 changed production Python 中 210 个 line coverage `>=80%`，8 个低于 80%，`dayu/runtime/argparse_exit.py` 未命中；没有可信 accepted evidence可补签 | Slice 3 只补 owner-contract tests；九个 production paths 默认且必须零 diff |
| AR-F06 | coverage instrumentation 下同一 R05 scheduler close/promotion node复现；R05 已把真实 bug裁决给未来独立 Host scheduler/lifecycle work item | 不写代码、不 waiver、不标 resolved；canonical non-coverage 不排除，coverage 仅精确排除这一个 node |
| AR-F07 | 当前远端无可用 Actions workflow/run/artifact，Darwin skip 不能证明 cmd.exe / Windows init | 本地 slices 不改 workflow、不伪造 PASS；最终 release 继续被真实 `windows-latest` evidence 阻塞 |
| S1-SEC-F01 | fresh configured-secret scan 的唯一命中 owner 是 Host internal `USER_INPUT_ACCEPTED.effective_execution_config.config.runner_spec.headers`；Service 解析 secret，Host 冻结 exact execution truth。Tool Trace event filter 不消费该 event；audit、HostEvent、run-input / memory / compact 与日志 owner都没有透传该字段，fresh projection / output / review / diff scan 为零 | `CLOSED_AS_NO_CODE_BLOCKER`；内部 Config / Host durable 命中做 accepted classification，Slice 1 只补 owner-level negative tests与分 surface scan，不改 production、不增加 slice |

### 2.2.1 Local trust / projection owner adjudication

`S1-SEC-F01` 的 production redesign 动机不成立。用户已明确裁决本地 Config 与 Host SQLite / EventLog 属于同一受信任产品域；为了让 dispatch、retry、replay、recovery使用同一份 exact effective execution truth，Host 持久化 resolved `RunnerSpec.headers` 是 owner-correct 行为，不是新增泄露面。当前代码与 real output 的直接证据也只证明该内部路径有值，不能把它外推成 Tool Trace、audit 或 LLM-facing leak。

本次只读 owner evidence 的 disposition 固定为：

| Surface | 唯一 projection owner / direct boundary | 当前 verdict | Slice 1 validation |
| --- | --- | --- | --- |
| Host internal effective execution | `dayu/service/host_assembly.py::_render_headers` -> Host admission -> `dayu/host/_execution_config_projection.py::runner_spec_json` -> `USER_INPUT_ACCEPTED` -> dispatch / replay restore | `ACCEPTED_TRUSTED_INTERNAL`；允许 exact Config / Host internal owner path 命中 | 用 real configured-value scan做逻辑 row/path分类；不要求清零，不改 production |
| Tool Trace hot / cold / query | `dayu/host/tool_trace.py::ToolTraceProjectionConsumer.event_filter` 与 typed extract / render helpers | `NO_CURRENT_LEAK`：filter 不包含 `USER_INPUT_ACCEPTED`，extract 不复制 effective execution config；fresh Tool Trace output scan为零 | synthetic sentinel canonical fact必须被filter跳过，hot / cold / query均零 sentinel |
| Audit JSONL / query | `dayu/host/audit.py::build_audit_json_line` | `NO_CURRENT_LEAK`：固定字段只含refs / digests / summaries，不复制 payload；fresh audit scan为零 | source event payload含sentinel时，整行序列化仍为零 sentinel并保持exact key contract |
| Public HostEvent / read API | `dayu/host/read_api.py::_host_event_from_row` / `_activity_from_row` | `NO_CURRENT_LEAK`：`USER_INPUT_ACCEPTED` 只成为无 activity 的typed progress，raw payload不进入DTO | public DTO / serialization零 sentinel |
| LLM-facing run input / memory / compact | `dayu/host/run_input.py`、`dayu/host/memory.py`、`dayu/host/compact_material.py` 的 user-input field selectors | `NO_CURRENT_LEAK`：只读取 `display_text`；resolved `RunnerSpec` 仍可作为 Engine执行参数，但不是LLM message/material | 只扫描 `messages`、memory / compact material与runner-call observation，不得错误要求 Engine执行所需 `request.runner_spec.headers` 清零 |
| Operator logs | 各 Host / Service / Engine logger callsite与既有 Engine diagnostic redaction owner | `NO_CURRENT_LEAK`：调用点记录ids / counts / refs / error classes，fresh log output scan为零；Topic 8现有redaction tests继续有效 | resolved runner header sentinel不进入caplog；不改变Engine exception redaction/truncation行为 |

上述 verdict 来自当前代码与实物扫描，不是按字段名猜测。若 Slice 1 owner test 暴露真实 projection leak，必须立即停止并提交同一 umbrella 内的最小复现：修复边界只能是该行对应的唯一 source projection owner或其直接 typed input validation，不得在下游UI、adapter、scan脚本或测试fixture中做黑名单、字符串替换、fallback或兼容 repair。本 plan当前没有发现真实 leak，因此 production allowlist保持为空。

### 2.3 AR-F02 唯一 public Fins contract owner

当前 `ValidatedFinsEventStream` 与 `FinsEvent`、`FinsDirectStreamProtocolError`、`FinsOperationKind` 是同一个 direct event/terminal contract。把 validator 单独放在 `dayu.fins.direct_stream` 迫使 Service 越出既有 public boundary。正确修复不是放宽 Service，而是把 validator 实现物理迁入现有 public owner `dayu/fins/direct_events.py`：

- `dayu/fins/direct_events.py` 成为 direct event、terminal protocol error、validated stream state machine 的唯一真源。
- 删除 `dayu/fins/direct_stream.py`；所有 production/test consumers 直接 import `dayu.fins.direct_events.ValidatedFinsEventStream`。
- 不在 `dayu/fins/__init__.py`、旧模块、其他模块或 `TYPE_CHECKING` 分支 re-export；不保留 wrapper/facade；不使用 importlib/lazy import。
- validator state machine、原异常身份、close-at-most-once、terminal result identity 和 public error contract保持不变；本轮只迁 owner，不重设计 protocol。

Awaiting resolution mode 是 Fins ingestion provider 与 Service host assembly 共享的 public closed contract，不属于 tools 私有 helper：

- 新建 `dayu/fins/ingestion/awaiting_resolution.py`，唯一拥有 `AWAITING_RESOLUTION_MODE_CONFIG_FIELD`、`AwaitingResolutionMode` 与 `parse_awaiting_resolution_mode`。
- 从 `dayu/fins/tools/_ingestion_tool_helpers.py` 物理删除上述定义；providers、Service 与 tests 直接 import 新 owner。
- `dayu/fins/ingestion/__init__.py` 不 re-export；Service 已允许 `dayu.fins.ingestion`，`tests/service/test_import_boundary.py::SERVICE_ALLOWED_IMPORTS` 不增加任何项。
- 不在 Service 重建枚举、Protocol、parser、字符串闭集或配置字段名；Fins owner 继续产生/校验该语义，Service 只消费 typed contract。

### 2.4 AR-F04 current run/artifact association

测试 oracle 必须按当前发布事实执行以下精确链路：

1. 在 runner-call artifact 集合中，以 current schema version、`host_run_id == run_id`、`runner_call_kind == "compactor_proposal"` 精确定位唯一 manifest；缺失或重复立即失败。
2. 从该 manifest 的 typed `compactor_identity.compaction_request_digest` 读取非空 SHA-256 digest；同时断言 `parent_host_run_id == host_run_id`。不得把 run id 拼接成 candidate id 或从文件名/顺序/mtime 反推。
3. 在 compact artifact 集合中，以 `artifact_kind == "context_compaction"` 且 top-level `compaction_request_digest` 与 manifest 完全相等，精确定位唯一 artifact；缺失、重复、schema/type 不符立即失败。
4. 对定位后的 artifact 继续执行 existing current-schema、continuity、accepted candidate 内容断言。删除 `_CANDIDATE_ID_FIELD` 与所有 `llm-compact:{run_id}` 逻辑。

这里的 raw JSON 读取只负责进入 current schema oracle；关联事实只能来自 owner-published exact fields，并通过严格 mapping/text/digest/uniqueness checks 消费。禁止 unknown-field probing、`dict.get` 猜测链、候选回退、扫描第一个匹配项或历史 schema 兼容。

### 2.5 AR-F03 in-process logging boundary

`utils/smoke_web_ci.py` 的 standalone CLI 确实需要 root logger 输出第三方诊断，因此不能把 `configure_root=True` 删除或改为默认。唯一缺陷是 pytest 在同一个解释器内多次调用 `main`，却没有隔离进程全局 logging registry。

Slice 1 的 test-only harness 必须：

- 在每一次 in-process `smoke.main(...)` 调用外层统一包装，而不是只修一个 case。
- 调用前 snapshot root 及当前 logging registry 中所有 concrete `logging.Logger` 的 level、handlers、filters、propagate、disabled；记录 registry identity。
- 在 `finally` 中恢复原 handler identity/order 与全部 logger fields，卸载并只关闭本次调用新增的 handlers，清除本次调用新建的 logger entries；成功、返回错误码、`SystemExit` 或被测异常都必须恢复。
- 不复制 `_DEFAULT_THIRD_PARTY_SUPPRESSIONS` 等 production 列表，不针对两个失败 logger写特例，不修改 `tests/conftest.py` 的全局 fixture。
- 增加 harness contract test：预置 root 与至少一个 named logger 的非默认状态，分别覆盖成功和失败调用，断言调用后 registry/logger/handler identity 与状态完全一致。

## 3. Global scope lock

### 3.1 Implementation mutable production allowlist

三个 slices 合计只允许下列 production paths；Slice 1 与 Slice 3 的 production allowlist 为空：

```text
# Slice 2 only
M dayu/cli/commands/fins.py
M dayu/fins/direct_events.py
D dayu/fins/direct_stream.py
A dayu/fins/ingestion/awaiting_resolution.py
M dayu/fins/ingestion_runtime.py
M dayu/fins/tools/_ingestion_tool_helpers.py
M dayu/fins/tools/download_provider.py
M dayu/fins/tools/preprocess_provider.py
M dayu/fins/tools/upload_provider.py
M dayu/service/fins_direct.py
M dayu/service/fins_wait_adapter.py
M dayu/service/host_assembly.py
```

任何额外 production path 都是 stop condition，不能以 pyright、Ruff、coverage、import cycle、测试便利或 README 同步为由自行扩域。

### 3.2 Implementation mutable test allowlist

```text
# Slice 1 only
M tests/service/test_host_admin.py
M tests/tools/web/test_smoke_web_ci.py
M tests/host/test_public_compact_smoke.py
M tests/host/test_audit_sink.py
M tests/host/test_tool_trace_projection.py
M tests/host/test_host_activity_event_projection.py
M tests/host/test_run_input_builder.py
M tests/host/test_logging.py

# Slice 2 only
M tests/cli/test_fins_commands.py
M tests/fins/test_fins_direct_stream.py
M tests/fins/test_fins_ingestion_tools.py
M tests/service/test_fins_direct.py
M tests/service/test_fins_wait_adapter.py
M tests/service/test_host_assembly.py

# Slice 3 only
M tests/documents/test_processors.py
M tests/fins/test_sec_pipeline_download.py
M tests/fins/test_processor_read_consistency.py
M tests/fins/test_fins_ingestion_tools.py
M tests/host/test_effective_execution_config.py
A tests/runtime/test_argparse_exit.py
```

Slice 1 后五个新增 allowlist path 只允许加入 §2.2.1 / §4.1 定义的 configured-secret projection sentinel tests；不得借此修改 projection contract、重写现有测试或触碰 production。correction entry 已有 delta 的前三个 Slice 1 tests必须在 plan review与恢复 implementation entry前保持上述 SHA-256 不变；后续 implementation只能在 Controller重新授权后继续其既有 Slice 1 delta。同一路径 `tests/fins/test_fins_ingestion_tools.py` 可在 Slice 2 迁移 public owner import，并在 Slice 3 补 preprocess owner cases；每个 slice 的 diff 与 review 必须只包含该 slice 新增的语义。`tests/service/test_import_boundary.py` 是验证 oracle，不在 mutable allowlist，必须零 diff。

### 3.3 Slice 2 mutable validation-utility allowlist

```text
# Slice 2 only
M utils/smoke_host_public_awaiting_entrypoint.py
```

该独立 allowlist 只允许把 `AwaitingResolutionMode` 的 import 从 `dayu.fins.tools._ingestion_tool_helpers` 迁到唯一 public owner `dayu.fins.ingestion.awaiting_resolution`。九个业务/类型使用位置与其它行必须保持不变；不得复制 enum、parser 或 config field，不得新增 fallback、兼容路径或其它 utility 改动。该路径在 Slice 1 与 Slice 3 必须零 diff。

### 3.4 README allowlist / decision

- 当前 plan-only gate 不修改任何 README。
- Slice 1：读取 `tests/README.md` 的更新约束并记录 `NO_UPDATE`；test fixture/harness/oracle不改变测试入口或最终用户工作流。
- Slice 2：只允许按现有职责更新 `dayu/fins/README.md`，把文件树和 direct/awaiting public owner描述迁到新真源；这是代码路径变化后的必需同步。读取并裁决 `dayu/service/README.md`、`tests/README.md`、根 `README.md` 与 `dayu/README.md`，预期均 `NO_UPDATE`，因为没有用户可见命令、层级关系或 Service 行为变化。
- Slice 3：读取 `tests/README.md` 更新约束并记录 `NO_UPDATE`；只增加 owner contract cases，不改变 canonical 测试工作流。
- 除 `dayu/fins/README.md` 外，任何 README 被判定必须修改时先 STOP，请 Controller 扩充精确 allowlist；不得机械同步。

### 3.5 Protected zero-diff paths

以下路径/集合在全部 slices、fix rounds、reviews 与 aggregate regression 中必须零 diff：

1. AR-F06 owner 与 scheduler evidence：

```text
dayu/host/dispatch.py
dayu/host/engine_ingest.py
dayu/host/_execution_health.py
tests/host/test_dispatch_scheduler.py
```

以及任何 scheduler/lifecycle/health-gate product 或 owner test。不得加入 retry、sleep、xfail、skip、timeout 放宽或 test-order 特例。

2. AR-F03 standalone product logging：

```text
utils/smoke_web_ci.py
dayu/runtime/log.py
tests/conftest.py
```

3. AR-F01 production config owner：

```text
dayu/runtime/config_loader.py
dayu/config/host_runtime.json
```

4. AR-F04 production compact/manifest owners：

```text
dayu/host/compact_payload.py
dayu/host/compact_artifact.py
dayu/host/compaction_operation.py
dayu/host/_runner_call_manifest.py
dayu/host/llm_compaction.py
dayu/host/context_events.py
```

5. AR-F02 boundary/compatibility traps：

```text
tests/service/test_import_boundary.py
dayu/fins/__init__.py
dayu/fins/ingestion/__init__.py
```

除 §3.3 在 Slice 2 允许的单行 import 迁移外，所有其它 `utils/**` 路径在全部 slices、fix rounds、reviews 与 aggregate regression 中必须零 diff；`utils/smoke_host_public_awaiting_entrypoint.py` 的其它行也必须零 diff。

6. AR-F05 九个 production owners：

```text
dayu/documents/processors/docling_processor.py
dayu/fins/pipelines/sec_6k_rules.py
dayu/fins/processors/sec_form_section_common.py
dayu/fins/processors/sec_report_form_common.py
dayu/fins/processors/sec_section_build.py
dayu/fins/processors/sec_table_extraction.py
dayu/fins/tools/preprocess_tools.py
dayu/host/_execution_config_projection.py
dayu/runtime/argparse_exit.py
```

7. AR-F07 workflow truth：

```text
.github/workflows/r11-upload-script-windows.yml
.github/workflows/r12-init-windows.yml
```

8. 本次 correction 被 Controller接受后的所有 design docs、control docs、既有 plan/review/completion artifacts、除 Slice 2 唯一 README allowlist外的全部 README，以及开始时已有 Controller-owned worktree changes。本 correction gate 对 `docs/host/design.md`、`docs/ui/design.md`、本 plan与固定新artifact的精确例外只用于写回用户裁决；不延续成 implementation allowlist。

每个 slice 开始记录 `SLICE_BASE=$(git rev-parse HEAD)`、完整 `git status --short`、pre-existing tracked diff清单及每个pre-existing tracked/untracked path的SHA-256。implementation、fix、review结束均重新采集 `git diff --name-status "$SLICE_BASE"` 和untracked列表：先验证pre-existing集合的path/status/hash完全不变，再把该集合从当前工作树清单中扣除，剩余delta才允许与本节 production/test/validation-utility/README allowlists精确比对。本次 correction gate 必须以新 artifact 的 entry status/hash 保护集合做同样校验，只允许 §0 列出的三份文档被修改并新增固定 correction artifact，尤其三个现有 test delta hash必须不变。发现额外路径立即停止，不先清理、不覆盖用户改动。

## 4. Dependency order 与三个 implementation slices

依赖顺序固定为 Slice 1 -> Slice 2 -> Slice 3：先恢复 current schema/test oracle 和 in-process isolation，再迁 public Fins owner并让 canonical suite全绿，最后在稳定整合树补齐九路径 coverage。不得并行实现或把 AR-F05 测试混入前两个 slices。

### 4.1 Slice 1 — current-schema / test-oracle closure + local-trust projection verification（AR-F01、AR-F03、AR-F04、S1-SEC-F01 no-code closure）

#### Implementation

1. `tests/service/test_host_admin.py`
   - 让 `_write_host_runtime` 写出 current required `wait_poller_policy` 全量 12 字段：`enabled=true`、`poll_interval_seconds=1.0`、`claim_ttl_seconds=60.0`、`claim_batch_size=100`、`backoff_initial_delay_seconds=30.0`、`backoff_multiplier=2.0`、`backoff_max_delay_seconds=300.0`、`not_ready_observe_interval_seconds=1.0`、`idle_poll_interval_seconds=5.0`、`adapter_call_timeout_seconds=30.0`、`close_drain_timeout_seconds=5.0`、`max_outstanding_adapter_calls=8`。
   - fixture继续表达“只加载 host runtime，不需要 models/secrets”；不得 import另一测试模块的 helper，不得给 production loader加兼容或默认值。
   - 增补/收紧断言，证明 fixture current schema加载成功且测试目标未漂移。
2. `tests/tools/web/test_smoke_web_ci.py`
   - 增加模块级私有、typed、带中文 docstring 的 logger snapshot/invocation helper，按 §2.5 统一包裹当前六个 `smoke.main(...)` in-process calls。
   - success/failure 两路都断言 root/named logger state与 handler identity恢复；测试不得依赖执行顺序才能通过。
3. `tests/host/test_public_compact_smoke.py`
   - 删除 candidate-id 常量、拼接和匹配；把 `_runner_call_manifest_for_run` 改为严格唯一定位，并从 `compactor_identity.compaction_request_digest` 取得关联 digest。
   - `_compact_artifact_for_run` 接收该 digest，以 current artifact kind/schema/digest严格唯一定位；保持 existing first/second run continuity assertions。
   - 新增 deterministic cases：正确 run/digest 成功；missing manifest、duplicate manifest、missing compact artifact、duplicate matching compact artifact、wrong/missing digest 均 fail closed。不得加 historical schema fixture。
4. `S1-SEC-F01` 只做 owner-boundary verification，不修改任何 production path：
   - 用一个不来自真实环境的 synthetic configured-secret sentinel 构造含 resolved `RunnerSpec.headers` 的 `USER_INPUT_ACCEPTED.effective_execution_config`，先断言 internal durable round-trip保留 exact value，证明测试没有把 accepted owner path误清零。
   - `tests/host/test_tool_trace_projection.py` 必须通过 projection runner / consumer filter证明该 event不产生 hot row、cold JSONL或query material；不得只对最终字符串做字段名黑名单断言。
   - `tests/host/test_audit_sink.py` 必须把同一 source event交给 `build_audit_json_line` / sink owner，断言 exact audit key contract保持且完整序列化零 sentinel。
   - `tests/host/test_host_activity_event_projection.py` 必须通过 public HostEvent owner投影同一 event，断言 typed DTO / serialization零 sentinel，且未知/不可展示payload不被拼进activity。
   - `tests/host/test_run_input_builder.py` 必须分别断言 LLM-facing `messages`、memory / compact material与runner-call observation零 sentinel；`AgentRunRequest.runner_spec.headers` 是 Engine执行所需的受信任 typed input，必须保留 sentinel，不得把它误判成LLM projection。
   - `tests/host/test_logging.py` 必须让resolved runner header sentinel经过Host接受/dispatch或等价owner callsite，断言caplog零 sentinel。Engine已有exception diagnostic redaction / diagnostic payload tests只重跑，不修改Topic 8行为。
   - 这些测试只允许source-owner白名单投影与完整serialization断言；禁止按 `Authorization`、`api_key` 等字段名列黑名单，禁止下游repair、mock-only bypass或改变accepted内部持久化。

#### Focused tests / real smoke

```bash
source .venv/bin/activate
pytest tests/service/test_host_admin.py -q
pytest tests/tools/web/test_smoke_web_ci.py -q
pytest tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_log.py::test_configure_does_not_touch_root_by_default \
  tests/fins/test_sec_downloader.py::test_sec_request_debug_logs_success_response -q
pytest tests/host/test_public_compact_smoke.py -q
pytest \
  tests/host/test_audit_sink.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_host_activity_event_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_logging.py -q
pytest \
  tests/engine/test_agent_phase2.py \
  tests/engine/runners/openai/test_diagnostic_payload.py -q
DAYU_RUN_REAL_COMPACTOR_SMOKE=1 pytest \
  tests/host/test_public_compact_smoke.py::test_real_compactor_public_opener_compacts_and_preserves_continuity \
  --basetemp=workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-real-compactor -q -rs
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-web \
  --include-playwright --external-limit 0 \
  --run-label wu-semantic-ownership-01-ar-fix-s1
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-awaiting \
  --keep-workspace
```

Standalone Web smoke必须仍输出 `status=passed`、11 local required、4 diagnostic-only、0 failure、0 skip；real compactor不得 skip且两轮 terminal/continuity/artifact oracle全绿。

#### Slice exit

- AR-F01、AR-F03、AR-F04 全部 closed。
- `S1-SEC-F01=CLOSED_AS_NO_CODE_BLOCKER`：internal Config / Host effective-execution命中按 §6.7 accepted classification记录；Tool Trace、audit、public HostEvent、LLM-facing material、日志、review与diff surface的owner tests / scans全部零 sentinel或零configured-value match。不得用“全局所有outputs零命中”重新打开已裁决的internal durable blocker。
- Canonical non-coverage full suite必须运行；在 AR-F02 尚未实施的顺序点，只允许 `tests/service/test_import_boundary.py::test_service_does_not_import_forbidden_layers` 保持已知失败，原三个 F01/F03 failures及其他 node必须全绿。这个临时预期不是 waiver，Slice 2 exit后不得再存在。
- Fresh aggregate coverage按 §6.2 exact scheduler exclusion运行；同样只允许 AR-F02 import-boundary失败，九个 AR-F05 paths继续登记 `OPEN_BY_SEQUENCE`，不得把中间数值签为最终 coverage PASS。

### 4.2 Slice 2 — public Fins contract / Service boundary closure（AR-F02）

#### Implementation

1. 按 §2.3 把 `ValidatedFinsEventStream` 的实现与私有 state/constants物理迁入 `dayu/fins/direct_events.py`，删除 `dayu/fins/direct_stream.py`，直接迁移四类 consumers：Fins runtime、CLI、Service、tests。其中 `tests/cli/test_fins_commands.py` 只把 `ValidatedFinsEventStream` import 迁到 `dayu.fins.direct_events`，不改 CLI 行为或 test oracle。
2. 新建 `dayu/fins/ingestion/awaiting_resolution.py` 作为 awaiting mode唯一 public owner；从 tools私有 helper删除三项语义，迁移三个 provider、两个 Service modules、host assembly与测试 imports。按 §3.3 只把 `utils/smoke_host_public_awaiting_entrypoint.py` 的 `AwaitingResolutionMode` import 迁到新 owner，utility 的九个业务/类型使用位置与其它行零 diff。
3. `tests/service/test_import_boundary.py` 零 diff并必须自然通过。新增 public module不能促使 allowlist扩张。
4. 保持所有 public业务行为：stream对象 identity、恰好一个且最后一个 RESULT、缺失/重复/RESULT 后事件 typed error、clean exhaustion 后 terminal identity、close-at-most-once、原异常/取消 identity、provider mode闭集与错误文本语义均不变。
5. 更新 `dayu/fins/README.md` 的现行文件树和 owner说明；不保留旧路径或兼容承诺。

#### Focused tests / import-owner scans / real smoke

```bash
source .venv/bin/activate
pytest tests/cli/test_fins_commands.py \
  tests/fins/test_fins_direct_stream.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/service/test_fins_direct.py \
  tests/service/test_fins_wait_adapter.py \
  tests/service/test_host_assembly.py \
  tests/service/test_import_boundary.py -q
pytest tests/fins -q
rg -n 'dayu\.fins\.direct_stream' dayu tests utils
rg -n 'from dayu\.fins\.direct_events import ValidatedFinsEventStream' dayu tests utils
rg -n '^(AWAITING_RESOLUTION_MODE_CONFIG_FIELD(?::[^=]+)?[[:space:]]*=|class AwaitingResolutionMode|def parse_awaiting_resolution_mode)' dayu tests utils
rg -n -U 'from dayu\.fins\.ingestion\.awaiting_resolution import (?:\([^)]*\b(?:AWAITING_RESOLUTION_MODE_CONFIG_FIELD|AwaitingResolutionMode|parse_awaiting_resolution_mode)\b[^)]*\)|[^\n]*\b(?:AWAITING_RESOLUTION_MODE_CONFIG_FIELD|AwaitingResolutionMode|parse_awaiting_resolution_mode)\b)' dayu tests utils
rg -n '^(AWAITING_RESOLUTION_MODE_CONFIG_FIELD(?::[^=]+)?[[:space:]]*=|class AwaitingResolutionMode|def parse_awaiting_resolution_mode)' dayu/fins/tools/_ingestion_tool_helpers.py
rg -n -U 'from dayu\.fins\.tools\._ingestion_tool_helpers import (?:\([^)]*\b(?:AWAITING_RESOLUTION_MODE_CONFIG_FIELD|AwaitingResolutionMode|parse_awaiting_resolution_mode)\b[^)]*\)|[^\n]*\b(?:AWAITING_RESOLUTION_MODE_CONFIG_FIELD|AwaitingResolutionMode|parse_awaiting_resolution_mode)\b)' dayu tests utils
```

第一个 direct-stream stale scan 必须在 `dayu tests utils` 零命中；第二个 consumer scan 必须精确命中三个 production 与三个 test consumers，并显式包含 `tests/cli/test_fins_commands.py`。Awaiting definition scan 必须在 `dayu tests utils` 精确命中新 owner `dayu/fins/ingestion/awaiting_resolution.py` 中的三个唯一定义；新 owner import scan 的每个命中都必须是 §3.1—§3.3 中的合法 consumer。最后两个旧 private owner definition/import scans必须都在 `dayu tests utils` 零命中；执行证据必须记录 `rg` 的 zero-match exit 1，不得把 scan error 冒充零命中。还必须静态检查 diff 中无 `__getattr__`、importlib、lazy import、try/except import、duplicate enum/protocol、package-root re-export或 Service字符串重算。

真实 Fins / Host smoke：

```bash
python -m dayu.cli \
  --base workspace/tmp/wu-semantic-ownership-01-ar-fix-s2-r03 \
  upload_filing --ticker AAPL --action create \
  --files tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm \
  --fiscal-year 2024 --fiscal-period FY --filing-date 2024-11-01 \
  --report-date 2024-09-28 --company-name 'Apple Inc.'
python -m dayu.cli \
  --base workspace/tmp/wu-semantic-ownership-01-ar-fix-s2-download \
  download --ticker AAPL --forms 10-K --start 2025-01-01 --end 2025-12-31
python -m dayu.cli \
  --base workspace/tmp/wu-semantic-ownership-01-ar-fix-s2-download \
  process --ticker AAPL
python utils/smoke_host_public_r03_semantic_ownership.py \
  --workspace-root workspace/tmp/wu-semantic-ownership-01-ar-fix-s2-r03 \
  --doc-file tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/meta.json \
  --web-query 'Apple annual report 2024 revenue' --fins-ticker AAPL \
  --fins-document-id fil_sec_8a5b42e2bf5e9e5f6d5aa480a10f913a8e37e283 \
  --keep-workspace
python utils/smoke_host_public_awaiting_entrypoint.py \
  --workspace-root workspace/tmp/wu-semantic-ownership-01-ar-fix-s2-awaiting \
  --keep-workspace
```

每个 direct operation必须有唯一 success terminal；不得从 summary、文件名或日志重建 progress/terminal；external provider不可用时保留完整 failure evidence并由 Controller裁决，不能改成 mock PASS。

#### Slice exit

- AR-F02 closed；Service boundary oracle在零改动下通过。
- Owner migration 后的 public-awaiting smoke 必须在 Slice 2 fresh 通过；不得沿用 Slice 1 在迁移前的结果。Direct-stream/awaiting definition、consumer 与 stale-private scans 必须覆盖 `dayu tests utils`，旧 `dayu.fins.direct_stream` 与 awaiting 三项语义的旧 private import/definition均为零命中。
- Canonical non-coverage full suite必须 0 failed；AR-F06 scheduler node在非 coverage模式不得排除且必须通过。
- Exact-exclusion aggregate coverage test run必须 0 failed；除明确留给 Slice 3 的九路径外，全部 aggregate-range production paths（含 Slice 2新 owner）line coverage `>=80%`，不得出现新的低覆盖路径。

### 4.3 Slice 3 — nine-path owner-test coverage closure（AR-F05）

#### Test-only implementation

Production allowlist严格为空。只在 §3.2 的六个测试文件中，从 public/owner contract补齐下表分支；不得直接复制 production算法到期望值，不得只调用 private helper而没有业务可观察断言：

| Production owner | Baseline line coverage | Test owner / required behavior families |
| --- | ---: | --- |
| `dayu/documents/processors/docling_processor.py` | 63.46% | `tests/documents/test_processors.py`：Docling payload sniff/support、section/table/page/search/full-text、records/markdown fallback、caption/header/context、noise/default/dedup header、malformed/missing metadata fail-safe，均通过 public processor结果断言 |
| `dayu/fins/pipelines/sec_6k_rules.py` | 67.56% | `tests/fins/test_sec_pipeline_download.py`：candidate filename/type/rank、quarter/half-year/XBRL signals、current result与未来/会议/管理变化/资本动作/演示/运营更新等正负分类，最终断言选取/拒绝业务结果 |
| `dayu/fins/processors/sec_form_section_common.py` | 78.23% | `tests/fins/test_processor_read_consistency.py`：virtual section构建/展开、structured/fallback headings、TOC/reference-guide抑制、table映射、boundary search、short/empty section与public read/search一致性 |
| `dayu/fins/processors/sec_report_form_common.py` | 65.14% | 同上：line-preserving HTML、edgartools rebuild、statement dataframe、TOC cutoff、item marker order/refinement、inline reference与候选优先级，断言public report section/statement结果 |
| `dayu/fins/processors/sec_section_build.py` | 77.56% | 同上：fast/full/single-section paths、body anchor、TOC cutoff、duplicate occurrence、table fingerprint与安全 text extraction，断言稳定 section顺序/范围/table ownership |
| `dayu/fins/processors/sec_table_extraction.py` | 66.16% | 同上：dataframe/dict/object/HTML/Markdown sources、section消歧、headers/row headers、financial classification、records recovery、MultiIndex/ghost columns、numeric/footnote normalization，断言public table content与section ref |
| `dayu/fins/tools/preprocess_tools.py` | 75.81% | `tests/fins/test_fins_ingestion_tools.py`：missing/invalid/valid `source_kind`、optional tuple/bool、start/cancel/failure/awaiting outcomes与schema contract |
| `dayu/host/_execution_config_projection.py` | 76.43% | `tests/host/test_effective_execution_config.py`：optional/required JSON scalar矩阵、RunnerSpec/options/provider request/AgentPolicy round-trip、missing/wrong/unknown/tampered fields fail closed |
| `dayu/runtime/argparse_exit.py` | 未命中 | 新建 `tests/runtime/test_argparse_exit.py`：int codes（含 0/2/负数）原样返回，`None`/字符串/其他非 int统一为 usage error 2；不改 helper |

以上是测试选择优先级，不授权为了命中行而构造不可能状态、mock-only hook、dead branch、production seam、`pragma: no cover`、coverage omit、动态 import或实现镜像。测试必须具备完整中文模块/类/函数 docstring与严格类型。

#### Stop condition

若任一新增 owner-contract case暴露真实 production correctness/type/security defect，或只有修改 production/直接耦合不稳定私有实现才能达到 80%，立即停止 Slice 3，保存最小复现、预期/实际、stack与coverage missing-line证据，交 Controller重新裁决 production owner与 allowlist。不得在本 slice顺手修 production，也不得降低 threshold。

#### Focused tests / coverage / real smoke

```bash
source .venv/bin/activate
pytest tests/documents/test_processors.py \
  tests/fins/test_sec_pipeline_download.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/host/test_effective_execution_config.py \
  tests/runtime/test_argparse_exit.py -q
```

Focused coverage先作为快速反馈，最终签署只采用 §6.2 fresh aggregate coverage。Slice 3还必须重跑真实 affected-owner paths：

```bash
python -m dayu.cli \
  --base workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-download \
  download --ticker AAPL --forms 10-K --start 2025-01-01 --end 2025-12-31
python -m dayu.cli \
  --base workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-download \
  process --ticker AAPL
python utils/smoke_host_public_r03_semantic_ownership.py \
  --workspace-root workspace/tmp/wu-semantic-ownership-01-ar-fix-s3-r03 \
  --doc-file tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/meta.json \
  --web-query 'Apple annual report 2024 revenue' --fins-ticker AAPL \
  --fins-document-id fil_sec_8a5b42e2bf5e9e5f6d5aa480a10f913a8e37e283 \
  --keep-workspace
```

#### Slice exit

- 九路径每个 fresh line coverage `>=80.00%`，AR-F05 closed。
- Final aggregate-range ledger必须精确为 `219/219 >=80%`。预期集合变化是原 219 中删除 `dayu/fins/direct_stream.py`、新增 `dayu/fins/ingestion/awaiting_resolution.py`，总数仍为 219；任何其他增删都是 scope failure。
- Canonical non-coverage suite、exact-exclusion coverage suite、full pyright、Ruff delta、build、scans、smokes全部满足 §6，不得仅凭 focused tests接受。

## 5. Per-slice mandatory review / fix / re-review state machine

每个 slice 都必须独立完成以下顺序，前一 slice未接受不得开始下一 slice：

1. AgentCodex implementation仅修改该 slice production/test/validation-utility/README allowlists；Controller先验证 path/status/staged/semantic-owner/test evidence。
2. AgentMiMo与AgentDS分别对从 immutable slice base 到完整当前 tree的全部 product/test/validation-utility/README diff做完整 code review。不得只看摘要、selected hunks或另一路 finding；两路都必须覆盖 correctness、stability、maintainability、architecture boundary、semantic ownership、over-coupling、security、tests/coverage和protected paths。
3. Controller逐条裁决两路 findings。AgentCodex只修 accepted findings；若修复需要扩 allowlist或触发本计划 stop condition，先停，不自行实施。
4. 修复后重跑该 slice的 focused tests、真实 smoke以及 §6全门禁；不得用旧运行结果补签。
5. AgentMiMo与AgentDS再次对完整修订后 slice tree做双路完整 re-review，确认 accepted findings真正关闭且无新 finding。只 review fix hunk不算 re-review。
6. Controller做最终 slice validation并明确接受后，才可按当时授权处理 slice commit/control transition。计划本身不授权 stage/commit/push。

## 6. 每个 slice 的统一验证门禁

### 6.1 Canonical non-coverage full suite

每个 slice implementation及每轮 accepted-finding fix后都运行无 PTY canonical command：

```bash
source .venv/bin/activate
pytest tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli
```

- Slice 1只允许 §4.1 已声明的单个 AR-F02 import-boundary中间失败；不能把该运行标为全绿。
- Slice 2、Slice 3及最终 aggregate必须 exit 0、0 failed。AR-F06 scheduler node不 deselect、不 skip、不 retry。
- pass count不得低于基线已通过 tests加本计划新增 cases；10 skips与5 deselected必须逐项保持现有平台/测试配置分类，不能新增未裁决 skip/deselect。

### 6.2 Coverage 与 exact scheduler node exclusion

Coverage measurement只能排除下面这一个已裁决 R05 node：

```text
tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
```

命令：

```bash
source .venv/bin/activate
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage erase
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage run --branch -m pytest \
  tests/documents tests/tools tests/host tests/engine tests/runtime tests/service tests/fins tests/cli \
  --deselect=tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task
COVERAGE_FILE=workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate.coverage \
  python -m coverage json \
  -o workspace/tmp/wu-semantic-ownership-01-ar-fix-aggregate-coverage.json
```

禁止任何额外 `--deselect`、`--ignore`、omit、xfail、skip、retry、parallel race掩盖或 coverage config修改。这个 exclusion只使219文件 coverage可测，不表示 AR-F06已修复/waived；canonical non-coverage仍必须运行该 node并通过。

最终 ledger生成规则：

- 从 `git diff --name-only --diff-filter=ACMR 3410d7422655c56bdf13c643f77c27f40b9d4550..FINAL_ACCEPTED_HEAD -- 'dayu/**/*.py'` 得到现存 changed production Python，排序、去重，必须恰好219个。
- 对 coverage JSON 的每个路径按 `covered_lines / num_statements * 100` 计算 fresh **line** coverage；不得使用含 branch的 combined `percent_covered` 冒充 line coverage，不在 JSON即按0处理。
- Slice 1/2必须输出 cumulative ledger；Slice 1只保留 AR-F02中间失败，Slice 1/2可把九个 AR-F05 paths标为 `OPEN_BY_SEQUENCE`，但不得出现其他 `<80%`。
- Slice 3与最终 aggregate必须 `219/219 >=80.00%`；九路径及 Slice 2新增 public owner都单列 statements/covered/missing/percent。

### 6.3 Full pyright / Ruff

```bash
source .venv/bin/activate
pyright
ruff check dayu tests utils --output-format json
```

- pyright必须 0 errors / 0 warnings / 0 informations；不得加 ignore、cast逃逸、`Any`、`object`、无类型签名或 `hasattr/getattr` fallback。
- 当前 full Ruff immutable baseline是144 findings。每个 slice开始与结束都把 JSON规范化为 `(filename,row,column,code,message)` 集合：完整集合相对 slice base不得新增；所有本 slice mutable paths必须0 finding。不得改 Ruff config、加 `# noqa`、删除无关代码或把 pipeline exit 0冒充 Ruff本身通过。
- 最终 aggregate同样要求 full Ruff baseline set无增量、全部本计划 mutable paths零 finding；若基线被外部提交合法改变，Controller必须先记录新 immutable set，不能只比较数字。

### 6.4 Diff / allowlist / staged state

每个 checkpoint运行：

```bash
git status --short
git diff --name-status "$SLICE_BASE"
git diff --check
git diff --cached --name-status
```

- `git diff --check`必须 exit 0。
- `git diff --cached --name-status`必须为空，除非后续 Controller在独立 gate明确授权 stage。
- 扣除开始时pre-existing protected集合后，剩余name/status必须与当前slice production/test/validation-utility/README allowlists精确相等或为其子集；delete/add status也必须匹配。Slice 2 的 validation-utility delta 必须只有 `M utils/smoke_host_public_awaiting_entrypoint.py`，且只有 §3.3 授权的 import 行迁移。既有Controller-owned modified/untracked paths不得被扣除后遗忘：必须以开始/结束SHA-256证明内容未变，mtime不作为语义证据。
- 不得删除、格式化、恢复或纳入既有工作区 changes。

### 6.5 Build

每个 slice及最终 aggregate均运行：

```bash
source .venv/bin/activate
python -m build --outdir workspace/tmp/wu-semantic-ownership-01-ar-fix-<gate>-build
```

必须同时生成 wheel与sdist、exit 0，记录文件名/bytes/SHA-256；输出只进入 gitignored `workspace/tmp`与build工具既有临时目录，visible worktree不新增路径。PyPA build已是本地验证前置，不得为了本计划修改 project runtime/dev dependencies。

### 6.6 Six canonical scans

每个 slice和最终 aggregate都重跑，不沿用旧结果：

```bash
rg -n 'DocResourceBudget|SourceBudgetExceeded|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files' dayu tests README.md
rg -n 'llm_safe_replay_arguments|arguments_summary_unsafe|_INTERNAL_SOURCE_REF_KINDS' dayu tests
rg -n 'stage_source_document|ingest_complete.*false|owner_scope_id|owner_token|_BATCH_OWNER_CONTEXT|_execute_with_auto_batch' dayu/fins tests/fins
rg -n 'statement_locator|statement_method_missing|raw_total|deduped_count' dayu/fins/tools dayu/fins/domain tests/fins
rg -n '\btotal\b|raw_total' dayu/fins/domain/xbrl_result_contract.py dayu/fins/processors tests/fins
rg -n 'schema_version.*commands|JSON argv|dayu-web|dayu-wechat|dayu-render' pyproject.toml dayu tests README.md
```

前四组必须零命中；S5/S6按 aggregate accepted classification逐项比对，允许 immutable fixture/财务术语/operational label既有命中，但不允许新 stale public semantic、raw total projection、removed entrypoint或JSON argv contract。

Slice 2 与最终 aggregate 还必须 fresh 重跑 §4.2 的 direct-stream/awaiting owner scans：扫描根固定为 `dayu tests utils`，新 owner definitions 各唯一、consumer imports 只落在精确 allowlists，旧 `dayu.fins.direct_stream` 与 awaiting 三项语义的旧 private definition/import 均必须零命中。

### 6.7 README / security / deferred / no-code ledger

每个 slice必须形成明确 ledger：

- README：按 §3.4 读取目标 README约束、记录 `UPDATE`或`NO_UPDATE`及直接理由；除 Slice 2 `dayu/fins/README.md` 外不允许先改后解释。
- Security：重跑 Doc path containment/output truncation、Web DNS/private/proxy/redirect/diagnostic、Host digest/EventLog/opaque ref、wait late-publication fence、Fins transaction/atomic swap/path/opaque id/direct validator、CLI POSIX quoting/init containment/process fencing相关既有矩阵。AR-F07 Windows项只能记 `PENDING_RELEASE_BLOCKER`。
- Configured-secret scan 必须按 semantic owner分类，不能继续用跨全部surface的单一零命中规则：
  - secret集合只从current typed model config的 `api_key_ref` 解析当前环境中非空values；只输出 configured value count、各surface match count / matched path count与Host logical row count，不输出value、ref名称、header名称或命中正文。
  - `ACCEPTED_TRUSTED_INTERNAL` 只允许两个精确owner：ConfigLoader管理的本地 Config source，以及Host internal SQLite / EventLog中 `USER_INPUT_ACCEPTED.effective_execution_config.config.runner_spec.headers` 的exact effective-execution canonical fact。SQLite物理file命中必须再以只读logical row / JSON path核对；所有logical命中必须是该event / path，logical other count必须为0。非零internal count不阻断release，也不要求清理、redact或production redesign。这个classification不授权改变`dayu-cli init` secret source storage。
  - `ZERO_REQUIRED` surfaces固定为Tool Trace hot/cold/query、audit JSONL/query、public HostEvent / read model / outbox、memory / compact / evidence / runner-call observation等LLM-facing material、operator logs、其它smoke输出、git diff与review artifacts。每一类必须分别输出0 match / 0 matched path；不得把它们与internal SQLite合并计数后waive。
  - 每个slice扫描本slice全部 `workspace/tmp/wu-semantic-ownership-01-ar-fix*` outputs、该slice artifact、当前git diff与相关review artifacts；final aggregate重新扫描三slice全部outputs与完整diff/reviews。binary SQLite只进入trusted-internal物理分类；audit / tool-trace文件、log、public / LLM artifacts与其余outputs进入各自zero-required分类。
  - owner-level synthetic sentinel tests与real configured-value surface scan必须同时通过：synthetic值证明投影owner明确排除，real scan证明实际assembly输出没有旁路。测试数据中的疑似token必须是显式synthetic值，不能把真实configured value写进test、artifact、diff或review。
  - 任一zero-required surface非零，或internal logical命中不在上述exact event / JSON path，立即按§9停止；不得按文件名、字段名黑名单、删除smoke output、改synthetic key或缩小scan root来“修复”结果。
- Deferred：Issue 177、178、175、142/151仍由各自 owner保留；本计划不得引入 TruncationManager wiring、storage-state lifecycle output/TTL/retention/refresh、Fins hard-kill/process isolation或assets migration。
- No-code：Topic 8与Codex F-13的 `dayu/engine/agent.py`、`dayu/engine/contracts/error_codes.py`零 diff；Topic 9不得引入统一 authorization框架、capability token、policy DSL或role model。
- AR-F06：持续写作 `RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`，不得用coverage exclusion改状态。

### 6.8 Per-slice real-smoke completeness

除各 slice列出的 real smokes外，Slice 2、Slice 3和最终 aggregate至少重跑：

```bash
DAYU_RUN_LIVE_BROWSER_CLEANUP_SMOKE=1 pytest \
  tests/tools/web/test_web_playwright_backend.py::test_playwright_live_browser_cleanup_terminates_descendants -q -rs
pytest \
  tests/cli/test_upload_filings_from_command.py::test_upload_filings_from_default_output_generates_posix_script_and_summary \
  tests/cli/test_upload_filings_from_command.py::test_posix_script_round_trips_adversarial_argv_with_real_sh \
  tests/cli/test_upload_filings_from_command.py::test_posix_generated_script_runs_real_cli_into_temp_storage \
  tests/cli/test_init_smoke.py -q
```

Darwin上的Windows nodes继续记真实 skip，不能算成功。HKEX external official GET不在本 fix无条件重发；必须重新校验 accepted immutable R10 raw evidence三份文件存在且SHA-256不变，并运行full Fins deterministic HKEX tests。若 evidence缺失/hash漂移，STOP交 Controller，不伪造本轮外部 success。

## 7. All-slices aggregate regression / deepreview gate

三个 slices各自经过双路完整 review/fix/re-review并由 Controller接受后，AgentCodex必须从最终整合树重新执行一轮 aggregate regression；不得拼接各 slice旧结果。至少包括：

1. §6.1 canonical non-coverage full suite，0 failed；AR-F06 node真实执行并通过。
2. §6.2 exact single-node exclusion coverage，coverage pytest 0 failed，final ledger `219/219 >=80%`。
3. full pyright、full Ruff exact baseline delta、diff-check、allowlist/protected path hashes、staged state。
4. wheel/sdist build及artifact hashes。
5. 六组 scans、Slice 2 direct-stream/awaiting owner/stale scans、README/security/configured-secret semantic-classification/deferred/no-code ledger；所有 owner/stale scans 都覆盖 `dayu tests utils`并证明旧 private import零命中，configured-secret scan必须把exact trusted internal owner与每个zero-required projection surface分开报告。
6. Real Web、public awaiting、R03 semantic ownership、real compactor、Fins upload/download/process、live browser cleanup、POSIX generated script/CLI/init，及accepted immutable HKEX evidence复核。
7. AR-F01—AR-F05逐项以当前命令和当前 tree标 `CLOSED`；AR-F06保持 no-code residual；AR-F07保持 pending external gate。

Aggregate regression全部本地门禁通过后，才进入 AgentMiMo与AgentDS双路 **aggregate deepreview**：

- 两路独立审查从 aggregate parent到最终 accepted HEAD的完整umbrella tree与本 fix，不复用per-slice review结论替代aggregate review。
- Controller裁决两路 findings；AgentCodex修复全部 accepted findings，每轮修复后重跑受影响测试和整套aggregate regression。
- AgentMiMo与AgentDS对最终完整aggregate tree做双路完整 re-review；两路都无未解决accepted finding后，Controller才能宣告aggregate deepreview local pass。
- 若aggregate fix触及本计划allowlist外路径或改变219集合，STOP并先修订/重审计划；不得以deepreview名义扩域。

## 8. AR-F07 Windows evidence gate

Local aggregate pass和MiMo/DS aggregate deepreview pass都不能关闭AR-F07。只有后续 Controller明确授权把包含最终accepted fix commit的分支推到真实remote后，才可触发/读取：

- `.github/workflows/r12-init-windows.yml`（优先；always step同时覆盖R11两个真实cmd nodes）。
- 必要时独立 `.github/workflows/r11-upload-script-windows.yml`。

必须验证：

1. run checkout commit包含 `ed9bfa9...` 与本 fix最终accepted commits；runner=`windows-latest`、Python 3.11、locked constraints安装成功，job非 skipped/cancelled，所有pytest node exit 0。
2. R11 artifact `r11-windows-upload-script-{run_id}` 包含environment/cmd help、pytest stdout/stderr/junit、cmd-recorder/generated script、单行 recorder oracle、CLI storage/generated script、grammar oracle；`cmd_invocation`精确为`cmd.exe /d /c`，script hash和portfolio artifact count一致。
3. R12 artifact `r12-init-windows-{run_id}` 包含`versions.txt`、`environment-names.txt`、`source-hashes.json`、`init-pytest-junit.xml`、`r11-pytest-junit.xml`；五个Windows init nodes、platform capability、rollback/race与两个R11 cmd nodes全绿。
4. workflow files相对本计划基线零 diff；不得为获得PASS改workflow、改测试skip或用Darwin/模拟cmd代签。

在这些真实run/artifact evidence被Controller接受前，状态始终是：

```text
AR-F07 = PENDING_RELEASE_BLOCKER
push / PR / final closeout = NOT AUTHORIZED
```

## 9. Stop conditions / residual risk

任一条件出现立即停止当前 slice并交 Controller：

- 正确语义 owner与本计划判断不一致，或需要新增production/test/validation-utility/README/workflow path。
- AR-F05测试暴露production defect，或只有private implementation mirroring/mock-only hook才能达到80%。
- Service boundary必须扩大allowlist才可通过；出现import cycle并诱发lazy import/re-export/facade方案；`tests/cli/test_fins_commands.py` 或 public-awaiting utility 需要超出精确 import 迁移的改动。
- Current compact artifact没有唯一manifest digest关联、出现重复owner-published association或schema与本计划直接证据不一致。
- Logger state无法在test harness内完整恢复而必须改变standalone logging行为。
- Canonical full suite在Slice 2后非零、public-awaiting smoke在owner迁移后非零、direct-stream/awaiting stale-private scans在 `dayu tests utils` 有命中、coverage除精确R05 node外还需排除任何node、219集合不是精确219或任何文件<80%。
- Full pyright新增错误、Ruff baseline set扩散、protected zero-diff path变化、staged state非空或Controller-owned worktree hash漂移。
- Security/deferred/no-code scan出现新命中；configured-secret scan在任一Tool Trace、audit、public / LLM-facing、log、其它output、diff或review surface非零，或trusted-internal logical match超出exact Config / Host effective-execution owner；build失败；真实smoke只有mock/skip才能通过。
- 任一§2.2.1 owner-level sentinel test失败，视为真实projection leak候选并立即停止。证据必须指出唯一失败owner（Tool Trace filter/extract、audit line builder、HostEvent projection、run-input / memory / compact selector或具体logger callsite）及最小输入/输出；不得新建sub-WU或额外slice。Controller若接受为真实leak，只能在同一umbrella内扩充该唯一source owner及其直接owner test的精确allowlist，再重审本三-slice plan；禁止字段名黑名单、下游UI / adapter repair、兼容分支或统一authorization框架。
- Windows evidence缺失、artifact不完整或run未checkout最终accepted commit。

已知 residual：

- `AR-F06` 是真实 scheduler/lifecycle bug，不因本计划消失；本轮只保持其owner/destination，不修、不waive。
- `AR-F07` 依赖真实remote Windows runner，不能在本地关闭。
- AR-F05大型SEC/Docling owner的80%门槛需要较多高价值边界cases；若测试揭示真实缺陷，进度可以停止，但不能牺牲owner boundary或测试质量。

## 10. Plan acceptance checklist

- [ ] 本 local-trust correction gate只修改Host/UI design与entry plan，并新增固定correction artifact；Engine design、product/test/README/workflow/control/其它review/Controller artifacts零变化，三个既有Slice 1 test delta SHA-256逐项不变，staged为空。
- [ ] 三个slices且顺序固定，AR-F01—F05均有唯一closure owner与test oracle。
- [ ] `S1-SEC-F01`关闭为no-code blocker；exact Config / Host internal effective-execution命中是accepted classification，Tool Trace、audit、public / LLM-facing、log、其它output、diff与review surface分别要求零明文。
- [ ] Slice 1追加五个精确owner-test allowlist path与synthetic sentinel contract，不增加production path、不增加slice；测试明确保留Engine执行所需`RunnerSpec.headers`，只对projection做zero断言。
- [ ] AR-F02不扩大Service allowlist，无compat re-export/lazy import/duplicate enum/protocol；Slice 2 test allowlist、focused tests 与direct consumer scan均覆盖 `tests/cli/test_fins_commands.py`。
- [ ] Slice 2 的独立 validation-utility allowlist 只含 `M utils/smoke_host_public_awaiting_entrypoint.py`，只迁移 `AwaitingResolutionMode` import；owner迁移后fresh运行 public-awaiting smoke。
- [ ] Direct-stream/awaiting definition、consumer 与stale-private scans在 Slice 2 与final aggregate均覆盖 `dayu tests utils`，旧 private import/definition零命中。
- [ ] AR-F04只用current runner manifest + compaction request digest关联，无candidate_id/raw guess/fallback。
- [ ] AR-F03只做in-process test harness isolation，standalone product logging零 diff。
- [ ] AR-F05九路径production零 diff，production defect触发stop。
- [ ] Production/test/validation-utility/README allowlists与protected paths精确列出。
- [ ] 每slice含focused tests、canonical suite、coverage、pyright、Ruff、diff、build、scans、README/security/deferred/no-code和真实smoke。
- [ ] Coverage只排除R05精确单node；最终要求219/219 line coverage >=80%。
- [ ] 每slice要求MiMo/DS完整code review、fix、完整re-review；全部slice后重新aggregate regression，再进入MiMo/DS aggregate deepreview。
- [ ] AR-F06保持no-code residual，AR-F07保持Windows pending release blocker。
- [ ] Plan经双路完整plan review/fix/re-review与Controller接受前不实施。
