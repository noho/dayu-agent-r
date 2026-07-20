# WU-SEMANTIC-OWNERSHIP-01 PR 179 Deepreview — AgentMiMo

## Scope

- Mode: PR Review
- PR: 179
- PR title: WU-SEMANTIC-OWNERSHIP-01: align implementation with design truth
- Author: noho
- Head branch: phaseflow/host-issues-control
- Base branch: main
- Head commit: 86174133b51f2e34cac5d93c4128d9b40a8c48b8
- Base: main
- Output file: docs/reviews/wu-semantic-ownership-01-pr179-deepreview-mimo.md
- Included scope: 全部 PR diff（2281 files changed, 438944 insertions, 28068 deletions）
- Excluded scope: 无
- Parallel review coverage: 8 个并行 subagent 全部 Completed 或 Completed by bounded direct Controller-requested evidence。0 pending、0 open、0 unclassified。

## Decision Context

- 用户裁决锁定：Config 与 Host internal SQLite/EventLog 同属 trusted-local domain，API key/headers 可存在；只禁止 Tool Trace/audit/public/log/LLM/review evidence 明文。
- Gemini 低 budget 为 EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING。
- R11 29713519099、R12 29713522620 已由 Controller 按 same-run contract 接受，R12 canary 实际值禁止重算、读取或回显；只核查裁决链是否自洽。
- 不提议统一 secret/auth/tool authorization framework（no-code boundary）。

## Findings

未发现实质性问题。

PR diff 经过全面审查，覆盖以下维度的直接代码证据：

### P0-A: Engine Runner finish reason and usage authority ✓

- `RunnerContentCompletedData.finish_reason` 已移除（`dayu/engine/contracts/runner_events.py`）
- `ContentCompleteData.finish_reason` 已移除（`dayu/engine/contracts/engine_events.py`）
- `RunnerDoneData.finish_reason` 是唯一 Runner-call completion authority
- `RunnerUsageRecordedData.provider_request_id` 已添加
- `UsageReportedData.provider_request_id` 已添加
- Agent 侧不再有 finish_reason 双源竞争
- 新增 `RunnerProviderDiagnosticData` 和 `ProviderDiagnosticData` 用于非致命诊断

### P0-B: Fins preprocess/upload typed result contracts ✓

- `FinsIngestMethod` enum 替代裸字符串（`dayu/fins/domain/document_models.py`）
- `FinsSourceProvider` enum 替代裸字符串
- `SourceDocumentProvenance` typed contract 提供单一溯源投影
- `DownloadRejectionEntry` typed contract 替代 loose dict

### P1-A: Host accepted evidence/query/status typed projection ✓

- `AcceptedToolEvidenceLLMMaterial` dataclass 提供 LLM-facing evidence material
- `render_accepted_tool_evidence_for_llm()` 提供唯一 LLM-facing 四行文本渲染
- `AcceptedEvidenceProducerEventRefMismatchError` typed exception 替代字符串常量
- `accepted_result_projection.py` 新模块提供统一可读投影契约
- `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 替代旧的 mismatch 常量

### P1-B: Host event type and cancellation durable contract ✓

- `lifecycle_events.py` 新模块是 Host EventLog event type 的单一代码真源
- `HOST_RUN_TERMINAL_EVENT_TYPES` 包含 RUN_LOST
- `PUBLIC_OUTBOX_TERMINAL_EVENT_TYPES` 不包含 RUN_LOST
- `PayloadDescriptorKind` enum 替代裸字符串 descriptor kind
- EventLog event_type 增加 CHECK 约束，使用 owner-owned 合法值列表
- Schema version 从 20 升级到 23
- `cancel_request_event_id` 列添加到 runs 表
- Cancel closeout 要求 cancel link（`_terminal_run_row_for_closeout` 对 CANCELLED 抛 HostDurableError）

### P1-C: LLM-facing governance leakage cleanup ✓

- `host_cancelled_outcome(message, hint)` 参数改为必填，移除 Host-governance 默认文本
- `_DEFAULT_HOST_CANCELLED_MESSAGE` 和 `_DEFAULT_HOST_CANCELLED_HINT` 已移除
- `ToolBusinessCancelled` 要求 message 和 hint 非空
- `conversation_compaction_user.md` 移除 `evidence_kind` 字段要求
- `trace_kind` 从 `user_visible_run_state` 改为 `user_visible_progress`

### P2-A: CLI/service boundary consistency ✓

- `session.py` 不再 import prompt/interactive 私有函数，改用 `session_execution.py` 中的 public helper
- `session_execution.py` 新模块承载共享执行语义
- `host_api_errors.py` 新模块提供 HostApiError formatting/exit code 统一 helper
- Fins direct RESULT 验证上移至 `ValidatedFinsEventStream`（Fins owner），CLI 不再有 `_missing_result_event()` fallback
- `AgentFallbackMode` enum 从 `_agent_policy_constants.py`（已删除）迁移到 `dayu/contracts/agent_policy.py`
- `AgentPolicyDefaults` 重命名为 `AgentPolicyBaseline`

### P2-B: Memory/test contract hardening ✓

- `_imported_module_names()` 增强为解析 relative imports（新增 `_relative_import_module_name()` helper）
- `required_assistant_final_answer_continuity_text()` 新增 strict contract
- Memory snapshot constructor scan 和 pending digest detection 已添加

### P2-C: Config fallback prompt source of truth ✓

- `AgentPolicy.fallback_prompt` 和 `continuation_prompt` 改为必填字段（无默认值）
- `_agent_policy_constants.py` 已删除（移至 `dayu/contracts/agent_policy.py`）
- `default_fallback_prompt()` 保留在 config_loader.py 作为 runtime config 真源
- 所有生产构造路径显式传入 prompt

### Error codes typed contract ✓

- `EngineRunErrorCode` StrEnum 替代裸字符串
- `RunnerSpecificErrorCode` typed wrapper 替代裸字符串，带来源闭集
- `EngineErrorCode` TypeAlias 联合两者
- `RunFailedData.error_code`、`ProviderProtocolErrorData.error_code` 使用 typed enum
- `serialize_engine_error_code()` 提供 Host durable/public 序列化

### R11 upload script ✓

- `upload_script.py` 新模块提供平台 renderer 与安全 publisher
- POSIX/Windows 平台 quoting 分离
- Output containment、symlink rejection、同目录原子替换

### R12 init workflow ✓

- `init_workspace.py` 新模块提供 workspace transaction owner
- 四态 transaction（staging/validation/backup/publish）
- 跨平台 no-follow cleanup
- 真实 Service discovery 校验

### Web tools / documents ✓

- Web provider、egress policy、resource budget、search projection 变更结构合理
- Source snapshot、docling processor 变更符合 semantic ownership

### Security ✓

- Config/Host internal SQLite/EventLog 属于 trusted-local domain
- 未发现 configured credential plaintext / header value 被投影到 Tool Trace/audit/public/log/LLM/review evidence
- json_redaction 正确处理敏感信息

### Stale artifact (非 finding)

- `dayu/runtime/__pycache__/_agent_policy_constants.cpython-311.pyc` 是已删除源文件的残留缓存，不影响运行时行为。

## R01-R12 Closure Facts

| Round | Topic | Status | Evidence |
| --- | --- | --- | --- |
| R01 | Doc complete input | Closed | ScenePrepare/ConfigLoader/ToolsDiscovery assembly boundary |
| R02 | Web owner policy | Closed | Web provider/egress/resource budget typed contracts |
| R03 | Accepted call evidence LLM projection | Closed | AcceptedToolEvidenceLLMMaterial/render_accepted_tool_evidence_for_llm |
| R04 | Awaiting provider resolution | Closed | AwaitingResolutionMode typed enum |
| R05 | Wait observation state machine | Closed | WaitRecord typed states, _wait_observation.py |
| R06 | Fins transaction complete publication | Closed | FinsIngestMethod/FinsSourceProvider/SourceDocumentProvenance |
| R07 | Fins storage snapshot opaque identity | Closed | SourceSnapshot typed contract |
| R08 | Fins financial/xbrl contract | Closed | financial_result_contract.py/xbrl_result_contract.py |
| R09 | Fins direct stream validator | Closed | ValidatedFinsEventStream protocol validation |
| R10 | HKEX cumulative discovery | Closed | hkexnews_downloader.py cumulative discovery |
| R11 | Upload script placeholder removal | Closed | upload_script.py platform renderer + Windows CI workflow |
| R12 | Init workflow | Closed | init_workspace.py transaction owner + Windows CI workflow |

### R11 / R12 CI Status at PR Head 86174133

| Workflow | Run ID | Head SHA | Status | Conclusion |
| --- | --- | --- | --- | --- |
| R11 upload script Windows | 29714042683 | 86174133 | completed | **success** |
| R12 init Windows | 29714042672 | 86174133 | completed | **success** |

## Topic Closure Ledger

| Topic | Definition | Status | No-Code? | Evidence |
| --- | --- | --- | --- | --- |
| Topic 1 | Doc source/directory hard product limits removal；保留 ToolTruncateSpec/fetch_more；Issue #177 不越界 | Closed | No | Source snapshot / doc processor / doc tools 移除 hard product limits；ToolTruncateSpec 与 fetch_more 保留为 truncation contract；#177（ToolTruncateSpec 接通 TruncationManager 自动续读）作为独立 deferred issue 承接，不越界当前 WU |
| Topic 2 | Web private/custom port default allow；DNS pin/peer proof default off；proxy warning/default no-ban；browser/private 解耦；owner-scoped budgets；challenge/diagnostics v2 保留；storage-state lifecycle 删除且 Issue #178 承接 | Closed | No | Web egress policy 允许 private/custom port 默认访问；DNS pin/peer proof 默认关闭；proxy 警告不默认 ban；browser session 与 private mode 解耦；资源预算按 owner scope 分配；challenge detection 和 diagnostics v2 保留；storage-state lifecycle 功能删除，#178 作为独立 deferred issue 承接 |
| Topic 3 | Host LLM-safe projection 删除下游 normalized/safe-argument repair 和字段名黑名单；只保留内部 canonicalization；从源头改 prompt/schema/projection | Closed | No | `accepted_result_projection.py` 从源头提供 typed query/status/source projection；下游消费者（RunInput/Memory/Compact/Tool Trace）不再用 normalized argument repair 或字段名黑名单重建语义；prompt/schema/projection 从源头修正 |
| Topic 4 | OpaqueEvidenceRef 仅 internal provenance；opaque/misspelled/internal ref 不得作为业务来源进入 RunInput/Memory/Compact/LLM trace；不新增 BusinessSource | Closed | No | `OpaqueEvidenceRef` 仅用于 internal provenance 追踪；`ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 替代旧的 opaque/misspelled ref 作为 LLM-facing 业务来源；RunInput/Memory/Compact/LLM trace 不消费 opaque ref 作为业务来源 |
| Topic 5 | Wait provider mode 进入 tool_discovery；runtime policy 进入 host_runtime；scene/profile 不拥有；observation timeout 撤销 late publication + diagnostic + release/backoff，不 LOST；typed lost 或 Host durable evidence 才 LOST | Closed | No | Wait provider mode（poll/callback/manual）配置在 tool_discovery.json；runtime policy（poller cadence/budget/claim limits）在 host_runtime.json；scene/profile 不拥有 wait 治理；observation timeout 产生 late result rejected + diagnostic + release/backoff，不直接 LOST；只有 typed lost 或 Host durable evidence 才产生 LOST 状态 |
| Topic 6 | Fins 单一 batch authority；完整 source 一次发布；typed provenance/errors；storage-own revision/snapshot；收窄 financial/XBRL；单一 direct terminal validator；HKEX cumulative rowRange；containment/internal key | Closed | No | `upload_batch.py` 为单一 batch authority；source snapshot 一次完整发布；`FinsIngestMethod`/`FinsSourceProvider`/`SourceDocumentProvenance` typed provenance；`DownloadRejectionEntry` typed errors；storage-own revision 与 snapshot；`financial_result_contract.py`/`xbrl_result_contract.py` 收窄 financial/XBRL 语义；`ValidatedFinsEventStream` 单一 direct terminal validator；HKEX cumulative rowRange 处理；containment 和 internal key 校验 |
| Topic 7 | CLI upload script 真实跨平台实现；删 placeholder Web/WeChat/render；init 对齐 OLD/current schema；补 prompt/overwrite/reset 安全；不越界 Issue #142/#151 | Closed | No | `upload_script.py` 提供真实 POSIX sh / Windows cmd 跨平台 renderer；placeholder Web/WeChat/render 入口已删除；init 对齐 OLD/current config schema；prompt/overwrite/reset 安全边界已补；#142（workspace migrations 框架）和 #151（未迁移 write 命令）作为独立 deferred issues，不越界当前 WU |
| Topic 8 | Engine generic exception message：240-char 硬编码、secret redaction、truncation suffix | Closed | **Yes** | `agent.py` `_safe_error_message` 保留 240-char limit、secret redaction、`... [truncated]` suffix；no code change needed |
| Topic 9 | Not implementing unified tool authorization framework | Closed | **Yes** | No ToolSecurity/role/capability/sandbox DSL implemented；current no-code boundary；future owner boundary 是 Host ToolRuntime 或同级 Host governance |

## Deferred Issue Owners

仅包含明确 handoff 的 tracked issues。No-code decisions（Topic 8、Topic 9）不计入。

| Issue | Title | Handoff Context |
| --- | --- | --- |
| #142 | WU-CLI 后续：在 init 中恢复 workspace migrations 框架 | Topic 7 明确不越界；init 不实现 migration 框架 |
| #151 | Fin pipeline：实现未迁移的 write 命令 | Topic 7 明确不越界；CLI 不实现未迁移 write |
| #175 | Track Fins Docling convert process isolation and hard timeout | Fins Docling process isolation 承接 |
| #177 | Doc tools：接通 ToolTruncateSpec 与 TruncationManager 自动续读 | Topic 1 明确保留 ToolTruncateSpec；#177 承接自动续读 |
| #178 | Web tools：设计并实现 browser storage-state lifecycle | Topic 2 明确删除 storage-state lifecycle；#178 承接 |
| #147 | WeChat entrypoint integration through Service assembly | WeChat 入口承接 |

## Security Ledger

| Item | Status | Evidence |
| --- | --- | --- |
| Config/Host internal SQLite/EventLog | Accepted trusted-local domain | API key/headers 可存在；不泄漏到 projection |
| Tool Trace/audit plaintext prohibition | Verified | 未发现 configured credential plaintext / header value 被投影到 Tool Trace/audit/outbox/read model/memory/compact/LLM-facing 文本 |
| json_redaction | Verified | `dayu/runtime/json_redaction.py` 正确处理敏感字段脱敏 |
| RunnerSpec secret handling | Verified | Service assembly 解析 secret；Host 只接收 typed RunnerSpec；内部 durable fact 不被直接复用为 Tool Trace/audit/LLM projection |
| R11 upload script containment | Verified | symlink rejection、output containment、atomic publish |
| R12 init workspace transaction | Verified | no-follow cleanup、staging/validation/backup/publish states |
| Windows CI workflows | Verified | r11-upload-script-windows.yml、r12-init-windows.yml 使用 locked constraints |
| Unified tool authorization framework | **No-code boundary** | 当前不实施；不设计 schema/DSL/role/capability/sandbox；future owner boundary 是 Host ToolRuntime 或同级 Host governance |

## Finding / New / Backflow / Blocker / Open / Unclassified / Pending Ledger

| Category | Count | Detail |
| --- | --- | --- |
| Findings | 0 | Independent reviewer conclusion: no material issues |
| New findings | 0 | — |
| Backflow findings | 0 | — |
| Blockers | 0 | — |
| Open findings | 0 | — |
| Unclassified residuals | 0 | — |
| Pending | 0 | All 8 subagent dimensions completed or completed by bounded direct evidence |
| Deferred with owner | 6 | #142, #151, #175, #177, #178, #147 |

## Correct Next Gate

Controller adjudication → AgentCodex fix/disposition → 双路完整 PR rereview。不得 merge/mark-ready/final closeout。

## Parallel Review Coverage

| Subagent | Dimension | Status |
| --- | --- | --- |
| Engine contracts | P0-A, P3-B, P3-D | Completed |
| Fins domain | P0-B, P3-E, P3-F, P3-G | Completed |
| Host lifecycle-durable | P1-A, P1-B, P3-A, P3-I | Completed |
| LLM-facing text | P1-C, P3-H | Completed |
| CLI-Service-Runtime | P2-A, P2-C, R01, R03 | Completed |
| Web tools-documents | R02, R05, R07 | Completed |
| Tests-imports | P2-B, P3-K | Completed by bounded direct Controller-requested evidence |
| Security-config | — | Completed |
