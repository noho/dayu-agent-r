# WU-SEMANTIC-OWNERSHIP-01 Aggregate Deepreview — AgentMiMo

## 1. Scope、Immutable Baseline 与 Verdict

- Umbrella WU：WU-SEMANTIC-OWNERSHIP-01；未新建 WU。
- Gate：aggregate deepreview only；不做代码修改，不 stage/commit/push/PR。
- 唯一可写：本 artifact。
- Verdict：**PASS / NO_MATERIAL_FINDING**。
- 本地 release 结论：AR-F01—AR-F05 已用当前 tree 的 fresh 证据关闭；AR-F06 保持 RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX；AR-F07 保持 PENDING_RELEASE_BLOCKER，未触发真实 Windows。

### Immutable Baseline 验证

| 项目 | 预期值 | Fresh 验证 |
| --- | --- | --- |
| branch | phaseflow/host-issues-control | ✓ |
| HEAD | 85aa7184a694448a5b27da7cca52f753f84d6e20 | ✓ |
| tree | 0db1c91f92dca594cf77c74bbde8f5b4fc42710d | ✓ |
| aggregate parent | 3410d7422655c56bdf13c643f77c27f40b9d4550 | ✓ |
| review range | b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184 | ✓ |
| changed production Python | exact 219 | ✓ (219 from aggregate parent) |
| staged | empty | ✓ |
| commits in range | 312 | ✓ |

### Dirty Paths（Controller-owned，全部 immutable）

| 路径 | 状态 | SHA-256 |
| --- | --- | --- |
| docs/host/issues-implementation-control.md | M | 121641cb46ccaa796e338cc27bb4aa2a33d1c0524111af6770cfdbe72e848bee |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-authorization.md | ?? | 4d6953b26fe81abf32c66cb9b62e4dee47f159e23ae8a3826b5479d8cf9fe48e |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-codex.md | ?? | b06cf2831655db530303a20e1edb45ebf1709d3f6d7673bfffe2e33897720710 |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-authorization.md | ?? | c6d368b6274605ceb86cde8393f2bab5f94a01c1f775b9cc52ed3c5b5dfb7c58 |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-validation.md | ?? | (untracked) |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-accepted-commit-controller-validation.md | ?? | (untracked) |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-mimo.md | ?? | (本 artifact，SHA 由 Controller 外部计算) |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-ds.md | ?? | (AgentDS artifact，未读取) |

## 2. 已完整读取的真源

| 文件 | 用途 |
| --- | --- |
| AGENTS.md | 项目最高约束、语义所有权、LLM-facing 文本约束、架构硬约束 |
| docs/host/issues-implementation-control.md | WU 总控文档（部分读取，token 限制） |
| docs/phaseflow-umbrella-optimization-control.md | Umbrella 流程优化约束 |
| docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md | Controller 最终产品裁决（9 Topic 全部） |
| docs/host/design.md | Host 设计真源（部分读取） |
| docs/engine/design.md | Engine 设计真源 |
| docs/tool/design.md | Tool 设计真源 |
| docs/fins/design.md | Fins 设计真源 |
| docs/ui/design.md | UI/CLI 设计真源 |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-codex.md | Fresh aggregate validation evidence |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-authorization.md | Aggregate regression gate authorization |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-validation.md | Controller validation verdict |

三路原始 overdesign review 仅作代码证据；冲突时 Controller discussion 优先。Fresh aggregate validation 及 Controller validation 是测试证据，不替代 code/design review。

## 3. Review Coverage

### 3.1 Changed Files 概览

- 范围：`b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184a694448a5b27da7cca52f753f84d6e20`
- Changed production Python：222 files（diff filter ACMR from range base）；aggregate parent 精确 219。
- Changed test Python：201 files。
- 总 diff：2084 files changed, 403852 insertions, 28061 deletions。

### 3.2 Topic 覆盖矩阵

| Topic | 裁决 | 审查方式 | 关键文件 | 结论 |
| --- | --- | --- | --- | --- |
| 1 Doc input budgets | accepted code fix | diff + code read | docling_processor.py, source_snapshot.py, doc tools | PASS |
| 2 Web policy | accepted mixed code/design | diff + code read | web_tools.py, web_search_providers.py, tool/design.md | PASS |
| 3 Host LLM-safe arguments | accepted code diff + code read | accepted_result_projection.py, evidence.py | PASS |
| 4 OpaqueEvidenceRef | accepted code diff + code read | evidence.py, accepted_result_projection.py | PASS |
| 5 Wait poller | accepted code/config fix | diff + code read | wait_adapter.py, _wait_observation.py, dispatch.py | PASS |
| 6 Fins contracts | accepted code fix | diff + code read | direct_events.py, financial_result_contract.py, xbrl_result_contract.py, hkexnews_downloader.py, fs_batching_repository.py | PASS |
| 7 Public entrypoints/init | accepted code fix | diff + code read | upload_script.py, commands/init.py, main.py | PASS |
| 8 Engine 240 chars | accepted as-is | code read | engine/agent.py | PASS (no-code) |
| 9 Tool security wording | design clarification | design read | tool/design.md, host/design.md | PASS (no-code) |

### 3.3 审查方法

1. **Diff 审查**：对 219 个 changed production Python 文件执行 diff 审查，重点检查 Topic 1-7 的核心变更。
2. **代码走读**：对关键模块执行完整代码走读，包括：
   - `dayu/host/accepted_result_projection.py`（新增，768 行）
   - `dayu/host/_wait_observation.py`（新增，416 行）
   - `dayu/host/evidence.py`（OpaqueEvidenceRef 变更）
   - `dayu/host/wait_adapter.py`（wait poller observation timeout）
   - `dayu/fins/direct_events.py`（direct stream terminal validation）
   - `dayu/fins/domain/financial_result_contract.py`（新增，535 行）
   - `dayu/fins/domain/xbrl_result_contract.py`（新增，488 行）
   - `dayu/fins/downloaders/hkexnews_downloader.py`（HKEX cumulative discovery）
   - `dayu/cli/upload_script.py`（新增，364 行）
   - `dayu/documents/processors/docling_processor.py`（Doc input/caption 变更）
3. **交叉验证**：与 fresh aggregate validation artifact 和 Controller validation 交叉验证。

## 4. Findings

### 未发现实质性问题

完整审查 Topic 1-7 的组合行为、LLM-facing 传播、semantic ownership、跨 slice 交互、correctness/stability/maintainability/security/over-coupling、测试真实性、README 一致性与 residual ownership 后，未发现需要 Controller 裁决的 material code/design finding。

## 5. Adversarial Failure Pass

### 5.1 Topic 1: Doc Input Budgets

**审查点**：`DocResourceBudget.max_source_bytes` 和 `max_directory_entries` 是否完全移除。

**结论**：PASS。`docling_processor.py` 和 `source_snapshot.py` 的 diff 确认：
- `_normalize_label` 从 `hasattr`/`getattr` 模式改为 `isinstance` + 直接 `.value` 访问（`docling_processor.py:1055-1075`）。
- `_extract_table_caption` 从 `getattr(table_item, "caption", None)` 改为使用 Docling 正式 API `caption_ref.resolve(document)`（`docling_processor.py:1174-1207`）。
- 无 `DocResourceBudget`、`source_budget_exceeded`、`directory_entry_limit`、`source_limit`、`skipped_oversized_files` 残留。

### 5.2 Topic 2: Web Policy

**审查点**：private/custom-port/browser/proxy/DNS 策略分离、storage-state lifecycle 移除。

**结论**：PASS。`web_tools.py` diff 确认：
- `allow_private_network_url`、`allow_custom_port_url`、`browser_enabled` 从默认值参数改为显式必需参数。
- `browser_enabled` 独立于 `allow_private_network_url`（`web_tools.py` 中 `browser_enabled and not transport_policy.dns_peer_proof_enabled`）。
- `playwright_storage_state_dir` 从默认空字符串改为显式必需参数。
- `applied_storage_state_cookie_count` 从 diagnostics 中移除。

### 5.3 Topic 3: Host LLM-Safe Arguments

**审查点**：`llm_safe_replay_arguments` 和黑名单修复是否完全移除。

**结论**：PASS。`accepted_result_projection.py`（新增 768 行）确认：
- 无 `llm_safe_replay_arguments`、`arguments_summary_unsafe` 残留。
- query 投影从 `AcceptedToolResultQueryState.SEMANTIC_QUERY` 或 `ARGUMENTS_SUMMARY` 产生，不依赖字段名黑名单。
- source 投影使用 `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 常量，不猜测 opaque ref。

### 5.4 Topic 4: OpaqueEvidenceRef

**审查点**：`_INTERNAL_SOURCE_REF_KINDS` 和未知 kind `kind:id` 渲染是否移除。

**结论**：PASS。`evidence.py` diff 确认：
- `_readable_source_text_from_refs` 和 `_require_opaque_evidence_ref_tuple` 已移除。
- `OpaqueEvidenceRef` 类型保留用于 EventLog/audit/internal provenance。
- `accepted_result_projection.py` 使用 `business_source_unavailable` diagnostic reason。
- 测试确认 `OpaqueEvidenceRef` 不进入 RunInput/Memory/Compact/LLM trace 作为 business source。

### 5.5 Topic 5: Wait Poller

**审查点**：observation timeout 是否只 release/backoff 而非 terminalize as LOST。

**结论**：PASS。`wait_adapter.py:1072-1085` 确认：
- `WaitObservationTimedOut` 处理路径调用 `_release_with_backoff()`，不调用 `_resolve_claimed_wait()`。
- `_release_with_backoff()`（`wait_adapter.py:1455-1495`）只释放 claim、写入 durable backoff、记录 `ADAPTER_ERROR` outcome。
- `_resolve_claimed_wait()` 只在 `WaitPollReady` 或 `WaitPollLost` 时调用（`wait_adapter.py:1113`）。
- `WaitObservationRunner`（`_wait_observation.py`）提供 token invalidation、capacity limiting、close/drain 机制。
- `WaitPollerRuntimePolicy` 验证（`open_host.py`）确认所有字段必须显式提供，无 `None` fallback 或模块默认值。

### 5.6 Topic 6: Fins Contracts

**审查点**：transaction ownership、source publication、provenance、financial/XBRL contracts、direct stream terminal、HKEX discovery、filesystem containment。

**结论**：PASS。

- **6.1 Batch ownership**：`fs_batching_repository.py` 参数从 `token` 重命名为 `batch`，语义更清晰。未引入 `ContextVar` ambient authority。
- **6.2 Source publication**：`_fs_source_document_core.py` 确认 `ingest_complete` 在 final upsert 时强制为 `True`，不再有 `ingest_complete=False` 的 staging acknowledgement。
- **6.3 Provenance**：`document_models.py` 中 `ingest_complete` 从默认 `True` 改为必需字段。
- **6.4 Financial/XBRL contracts**：新增 `financial_result_contract.py`（535 行）和 `xbrl_result_contract.py`（488 行），定义封闭业务类型、校验器和投影规则。`FinancialStatementReason` 只保留 7 个业务原因，不含 implementation diagnostics。`XbrlFactsResult` 只暴露 `facts` 和 `data_quality`，不含 raw total + deduped count 双计数。
- **6.5 Direct stream terminal**：`direct_events.py` 新增 `ValidatedFinsEventStream`（223 行），独占"恰好一个 RESULT"判定。`FinsDirectStreamProtocolError` 提供 typed 错误分类（`MISSING_RESULT`、`DUPLICATE_RESULT`、`EVENT_AFTER_RESULT`）。Service 和 CLI 只消费同一 validated stream。
- **6.6 HKEX discovery**：`hkexnews_downloader.py` 实现官方 cumulative `rowRange` continuation。解析 `hasNextRow`、`loadedRecord`、`recordCnt` 官方字段。每次响应是 cumulative snapshot，只使用最终响应。字段矛盾时返回 typed provider-protocol failure。
- **6.7 Filesystem containment**：`_fs_identity.py` 保持 path containment。opaque domain ID 到 internal key 的映射在 storage owner 内完成。

### 5.7 Topic 7: Public Entrypoints/Init

**审查点**：`upload_filings_from` 完整实现、placeholder 包移除、init 对齐 OLD。

**结论**：PASS。

- **7.1 upload_filings_from**：新增 `upload_script.py`（364 行），提供平台 renderer（POSIX `.sh` / Windows `.cmd`）和安全 publisher（containment、symlink rejection、atomic replace）。`commands/fins.py` 消费 Fins batch plan 生成脚本，不再输出 `{schema_version: 1, commands: [argv...]}` JSON。
- **7.2 Placeholder packages**：`main.py` 中 `dayu-web`、`dayu-wechat`、`dayu-render` 占位入口已移除。
- **7.3 Init**：`commands/init.py` 新增 `_select_model()` 和 `_run_init_prewarm()`。`init_catalog.py` 提供 provider/model catalog。`init_environment.py` 处理 API key 配置。`init_workspace.py` 处理 config tree staging/swap/rollback。

### 5.8 Topic 8: Engine 240 Chars

**审查点**：是否维持 no-code decision。

**结论**：PASS。`engine/agent.py` 和 `engine/contracts/error_codes.py` 在 `ffbf48c2..HEAD` 范围内零 diff。240 字符截断和 sensitive-value redaction 保持原样。

### 5.9 Topic 9: Tool Security Wording

**审查点**：是否维持 design-only clarification，不实现统一 authorization framework。

**结论**：PASS。`tool/design.md` §10 和 `host/design.md` 记录了防御性安全边界和未来 Host authority 方向。无 unified tool authorization framework 代码。

## 6. Semantic Ownership Drift Pass

### 6.1 LLM-facing 文本传播

**审查点**：tool schema、prompt、Host/Engine/Tool projection 是否符合 AGENTS.md LLM-facing 文本约束。

**结论**：PASS。
- `accepted_result_projection.py` 的 query/source projection 只产生业务可读文本，不暴露 `tool_call_id`、`event_id`、`payload_ref`、digest、cursor 等内部治理标识。
- `financial_result_contract.py` 的 `FinancialStatementReason` 只包含业务可理解原因。
- `xbrl_result_contract.py` 的 `XbrlQueryReason` 只包含业务可理解原因。
- `direct_events.py` 的 event text 使用业务可读描述。

### 6.2 Cross-slice 交互

**审查点**：Topic 1-7 之间是否存在语义冲突或 ownership 漂移。

**结论**：PASS。
- Topic 1（Doc budgets）和 Topic 3（LLM-safe arguments）无交叉：Doc tools 处理输入文件，Host projection 处理工具结果。
- Topic 4（OpaqueEvidenceRef）和 Topic 5（Wait poller）无交叉：evidence 投影和 wait 观察是独立路径。
- Topic 6（Fins contracts）和 Topic 7（CLI/init）通过 `upload_filings_from` 交互：Fins 拥有 batch plan，CLI 拥有脚本渲染。边界清晰。

### 6.3 Fallback / 特例 / hasattr / getattr 残留

**审查点**：是否有下游通过 fallback、特例、`hasattr`/`getattr` 补救上游 contract。

**结论**：PASS。
- `docling_processor.py` 中剩余 `getattr` 调用（`export_to_markdown`、`data`、`text`、`self_ref`、`get_ref`、`parent`）是访问 Docling 可选 API 特性的合理模式，不是补救上游 contract。
- `sec_form_section_common.py` 中 `getattr(section_obj, "part", None)` 等调用是访问 DataFrame 行对象可选字段的合理模式。
- 无 `hasattr` 残留。

## 7. Security Pass

### 7.1 API Key / Secret 泄露

**审查点**：Tool Trace、audit、public、LLM-facing、logs、outputs、diff、reviews 中是否有明文 API key/secret。

**结论**：PASS。
- Config 与 Host internal SQLite/EventLog 属于 trusted local domain，API key/header 可在其中出现。
- `accepted_result_projection.py` 不暴露 `tool_call_id`、`event_id`、`payload_ref` 等内部标识给 LLM。
- `tool_trace.py` diff 无 API key/secret 泄露。
- Fresh aggregate validation 的 configured-value scan 确认 `SCAN_VERDICT=PASS`。

### 7.2 Path Containment

**审查点**：filesystem 路径逃逸防护。

**结论**：PASS。
- `_fs_identity.py` 保持 lexical/resolved containment 和 symlink rejection。
- `upload_script.py` 的 `UploadScriptPublishError` 拒绝不安全 ticker。
- `init_workspace.py` 保持 init mutation 的 containment/symlink 规则。

### 7.3 Web Egress

**审查点**：Web 工具网络策略。

**结论**：PASS。
- private/custom-port/DNS/proxy 策略全部配置化，默认 allow/off。
- `browser_enabled` 独立于 `allow_private_network_url`。
- storage-state lifecycle 移除，只保留配置输入路径。

## 8. Deferred / No-Code Ledger

| 项目 | 状态 | Owner / Destination |
| --- | --- | --- |
| AR-F06 Host scheduler/lifecycle | RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX | future Host scheduler/lifecycle owner |
| AR-F07 Windows release blocker | PENDING_RELEASE_BLOCKER | Windows CI |
| Issue #142 Workspace migration | NOT_IMPLEMENTED | GitHub Issue #142 |
| Issue #151 Write/assets | NOT_IMPLEMENTED | GitHub Issue #151 |
| Issue #175 Fins Docling process isolation | NOT_IMPLEMENTED | GitHub Issue #175 |
| Issue #177 Doc TruncationManager connection | NOT_IMPLEMENTED | GitHub Issue #177 |
| Issue #178 Browser storage-state lifecycle | NOT_IMPLEMENTED | GitHub Issue #178 |
| Topic 8 Engine 240 chars | NO_CODE_ACCEPTED | docs/engine/design.md |
| Topic 9 Unified tool authorization | NO_CODE_ACCEPTED | docs/host/design.md, docs/tool/design.md |
| Web/WeChat/render trackers | NOT_IMPLEMENTED | Issues #84, #147, independent render tracker |
| Gemini quota/provider adherence | NO_CODE / NON_BLOCKING | test account residual |

## 9. Test Authenticity

### 9.1 Fresh Aggregate Validation Evidence

Fresh aggregate validation（AgentCodex artifact）确认：
- Canonical suite：5260 passed / 10 skipped / 5 deselected / 0 failed。
- Coverage：219/219 >=80.00%，最低 `dayu/fins/storage/_fs_identity.py` = 80.00%。
- Full pyright：0 errors, 0 warnings, 0 informations。
- Ruff：142 immutable findings，ADDED=0。
- Wheel/sdist build：成功。
- 六组 source/propagation scans：全部 PASS。
- Smokes：Web CI、public awaiting、R03 deterministic、public compact、Fins upload/download/process、HKEX、CLI POSIX/init、live browser cleanup、configured-secret sentinels 全部 PASS。

### 9.2 Controller Independent Validation

Controller validation 确认：
- AR-F01—AR-F05：CLOSED。
- AR-F06：RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX。
- AR-F07：PENDING_RELEASE_BLOCKER。
- 新 product/test/README defect：0。
- accepted/open local finding：0。

### 9.3 测试真实性判断

- 测试断言 owner-level contract 行为，不固化偶然行为。
- OpaqueEvidenceRef 测试确认任意、misspelled、internal opaque refs 不进入 LLM-facing material。
- Wait observation timeout 测试确认只 release/backoff，不 terminalize。
- Direct stream terminal 测试确认恰好一个 RESULT 的 typed protocol error。
- HKEX cumulative discovery 测试使用 accepted fixture evidence，未新增 HKEX GET。

## 10. Residual Risk

### 10.1 AR-F06: Host Scheduler/Lifecycle

当前 Host scheduler 的 `wake_queue_promotion` 使用 tracked async promotion task。该 node 在 canonical suite 中真实执行通过，但 coverage 中被排除（唯一排除 node）。Residual 保持 RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX。Future Host scheduler/lifecycle owner 不变。

### 10.2 AR-F07: Windows Release Blocker

Darwin skip 不作为 Windows success。CLI POSIX upload/init 测试中有 5 项 Darwin 上 Windows-only skip。PENDING_RELEASE_BLOCKER 状态不变。

### 10.3 Gemini Quota / Provider Adherence

Gemini 是低预算测试账号。本 gate 没有发新 provider 请求，也没有改 config/model/key/retry/quota/budget。状态保持 NO_CODE / NON_BLOCKING。

### 10.4 Issue Trackers

Issues #142、#151、#175、#177、#178 和 Web/WeChat/render trackers 保持既有 owner/destination，未实施。

## 11. Verdict

**PASS / NO_MATERIAL_FINDING / READY_FOR_CONTROLLER_ADJUDICATION**

完整审查 Topic 1-7 的组合行为、LLM-facing 传播、semantic ownership、跨 slice 交互、correctness/stability/maintainability/security/over-coupling、测试真实性、README 一致性与 residual ownership 后，未发现需要 Controller 裁决的 material code/design finding。

所有 Topic 的实现符合 Controller discussion 的最终产品裁决。Fresh aggregate validation 证据确认 219/219 production Python 文件 >=80% coverage，canonical suite 0 failed，pyright 0 errors。

## 12. Artifact SHA

Artifact final SHA 由 Controller 外部计算，不自嵌以避免自引用。

## 13. Immutable Hashes 验证

| 项目 | 值 |
| --- | --- |
| HEAD | 85aa7184a694448a5b27da7cca52f753f84d6e20 |
| tree | 0db1c91f92dca594cf77c74bbde8f5b4fc42710d |
| staged | empty |
| review range | b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184a694448a5b27da7cca52f753f84d6e20 |
