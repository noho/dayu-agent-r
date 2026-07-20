# WU-SEMANTIC-OWNERSHIP-01 Aggregate Deepreview Re-review — AgentMiMo

## 1. Scope、Immutable Baseline 与 Verdict

- Umbrella WU：WU-SEMANTIC-OWNERSHIP-01；未新建 WU。
- Gate：aggregate deepreview re-review only；不做代码修改，不 stage/commit/push/PR。
- 唯一可写：本 artifact。
- Verdict：**PASS / NO_NEW_MATERIAL_FINDING / CONFIRMED**。
- DS-01/02/03 裁决全部确认为 `REJECTED_NOT_A_DEFECT / NO_FIX`，zero-change 未错误实施。
- Initial review 范围仍成立；Topic 1-7 组合树、安全/deferred/no-code/residual ledger 无漂移。

### Immutable Baseline 验证

| 项目 | 预期值 | Fresh 验证 |
| --- | --- | --- |
| branch | phaseflow/host-issues-control | ✓ |
| HEAD | 85aa7184a694448a5b27da7cca52f753f84d6e20 | ✓ |
| tree | 0db1c91f92dca594cf77c74bbde8f5b4fc42710d | ✓ |
| review range | b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184 | ✓ |
| changed production Python | 222 (aggregate parent 精确 219) | ✓ |
| staged | empty | ✓ |
| commits in range | 312 | ✓ |

### Dirty Paths（Controller-owned，全部 immutable）

| 路径 | 状态 | Fresh SHA-256 |
| --- | --- | --- |
| docs/host/issues-implementation-control.md | M | 6711eb4aede95ba9339e295be12b68efa70a69d6526834dd59388233b9c0939e |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-authorization.md | ?? | 4d6953b26fe81abf32c66cb9b62e4dee47f159e23ae8a3826b5479d8cf9fe48e |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-adjudication.md | ?? | 6f6264ac3079038832f6f565a282e9f00007c3e53223ebe9212152bb93d75607 |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-ds.md | ?? | 3afb417dcc8dee839a98d69099615b4fd5091fde6e8b97a1b639244cdbb74ffc |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-mimo.md | ?? | 9bb5168bfd4eb9bbb8ae5a74ded5d8c6eba0ceb77c948ce45164af0308e66107 |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-codex.md | ?? | ac8193fbdb103f9fb9400f530abca81cbe796e4780982ad60612ffffbbef3a31 |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-controller-authorization.md | ?? | 1a97049298bc231a68cbb5ab6c2179e445d0fba7237a7907bbd6081d109aa293 |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-controller-validation.md | ?? | 7ac0c9385053f8f2ea97a8ef2dfe4578ddf857632ef8b3ccc69eb367042c4dcf |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-codex.md | ?? | b06cf2831655db530303a20e1edb45ebf1709d3f6d7673bfffe2e33897720710 |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-authorization.md | ?? | c6d368b6274605ceb86cde8393f2bab5f94a01c1f775b9cc52ed3c5b5dfb7c58 |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-final-validation-controller-validation.md | ?? | 6d2b76b42515a7eccb14d0546196ed475e8c7cd758b29e0f824523b653abbc34 |
| docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-accepted-commit-controller-validation.md | ?? | 2b1704bead5baf7e03a13be8d48655d46225df9f390704f496c72d2e58c796fc |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-rereview-controller-authorization.md | ?? | 110ee5ee7f58a8e31f2e33532f18b6339d7519c6031d6a73d58f20b2491fccf2 |

注：`docs/host/issues-implementation-control.md` 和 `fix-controller-validation.md` 的 SHA-256 与 Codex disposition 锁定值不同，系 Controller 在 disposition 至本 re-review 之间的正常 gate 传播，非 review target 代码变更。

## 2. 已完整读取的真源

| 文件 | 用途 |
| --- | --- |
| AGENTS.md | 项目最高约束、语义所有权、LLM-facing 文本约束、架构硬约束 |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-authorization.md | Controller re-review 授权 |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-controller-adjudication.md | Controller 裁决（DS-01/02/03） |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-mimo.md | Initial MiMo review |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-ds.md | Initial DS review |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-codex.md | Codex zero-change disposition |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-controller-authorization.md | Zero-change authorization |
| docs/reviews/wu-semantic-ownership-01-aggregate-deepreview-fix-controller-validation.md | Controller fix validation |

未读取 AgentDS final re-review artifact（按授权要求）。

## 3. Topic 1-7 组合树 Re-verification

### 3.1 Topic 1: Doc Input Budgets

**验证点**：`max_source_bytes`、`max_directory_entries`、`source_budget_exceeded`、`directory_entry_limit` 是否完全移除。

**结论**：PASS。`rg` 在整个 `dayu/` 目录下零命中。`docling_processor.py` 中 `_normalize_label` 使用 `isinstance` + `.value` 访问（非 `hasattr`/`getattr`），`_extract_table_caption` 使用 Docling 正式 API `caption_ref.resolve(document)`。

### 3.2 Topic 2: Web Policy

**验证点**：`allow_private_network_url`、`allow_custom_port_url`、`browser_enabled` 是否为显式必需参数且独立配置。

**结论**：PASS。`web_tools.py` 确认三者均为显式 `bool` 字段，`browser_enabled` 独立于 `allow_private_network_url`。`playwright_storage_state_dir` 为显式必需参数。`applied_storage_state_cookie_count` 已从 diagnostics 移除。

### 3.3 Topic 3: Host LLM-Safe Arguments

**验证点**：`llm_safe_replay_arguments`、`arguments_summary_unsafe`、`_INTERNAL_EVIDENCE_SOURCE_PREFIXES`、`_llm_facing_evidence_source_text` 是否完全移除。

**结论**：PASS。`rg` 在整个 `dayu/` 目录下零命中。`accepted_result_projection.py` 使用 `AcceptedToolResultQueryState.SEMANTIC_QUERY` 或 `ARGUMENTS_SUMMARY` 投影 query，不依赖字段名黑名单。source 投影使用 `ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT` 常量。

### 3.4 Topic 4: OpaqueEvidenceRef

**验证点**：`_INTERNAL_SOURCE_REF_KINDS`、`_readable_source_text_from_refs`、`_require_opaque_evidence_ref_tuple` 是否移除；`OpaqueEvidenceRef` 是否仅用于 EventLog/audit/internal provenance。

**结论**：PASS。`rg` 在 `dayu/host/evidence.py` 中零命中。`accepted_result_projection.py` 使用 `business_source_unavailable` diagnostic reason。`OpaqueEvidenceRef` 类型保留用于内部 provenance，不进入 LLM-facing material。

### 3.5 Topic 5: Wait Poller

**验证点**：`WaitObservationTimedOut` 是否只 release/backoff 而非 terminalize as LOST。

**结论**：PASS。`wait_adapter.py` diff 确认 `WaitObservationTimedOut` 处理路径调用 `_release_with_backoff()`，不调用 `_resolve_claimed_wait()`。`WaitPollerRuntimePolicy` 所有字段为 required（无默认值）。

### 3.6 Topic 6: Fins Contracts

**验证点**：`ValidatedFinsEventStream`、`FinsDirectStreamProtocolError`、HKEX cumulative discovery、`FinancialStatementReason`、`XbrlFactsResult` 是否完整。

**结论**：PASS。
- `direct_events.py`：`ValidatedFinsEventStream` 独占"恰好一个 RESULT"判定；`FinsDirectStreamProtocolError` 提供 `MISSING_RESULT`、`DUPLICATE_RESULT`、`EVENT_AFTER_RESULT` 三类 typed 错误。
- `hkexnews_downloader.py`：实现官方 `rowRange` cumulative continuation，解析 `hasNextRow`、`loadedRecord`、`recordCnt`。
- `financial_result_contract.py`：`FinancialStatementReason` 只保留 7 个业务原因。
- `xbrl_result_contract.py`：`XbrlFactsResult` 只暴露 `facts` 和 `data_quality`。

### 3.7 Topic 7: Public Entrypoints/Init

**验证点**：`dayu-web`、`dayu-wechat`、`dayu-render` 占位包是否移除；`upload_filings_from` 是否完整实现。

**结论**：PASS。`rg 'dayu-web|dayu-wechat|dayu-render' pyproject.toml` 零命中。`upload_script.py` 提供 POSIX `.sh` / Windows `.cmd` 平台 renderer。`current_upload_script_platform()` 按 `os.name == "nt"` 分派。

## 4. DS-01/02/03 裁决确认

### DS-01 — Evidence block text exact-match

**Controller 裁决**：`REJECTED_NOT_A_DEFECT / NO_FIX`

**Re-review 确认**：PASS。

`compact_material.py` diff 确认 `RunInputMaterialBlock.__post_init__()` 中的校验：
```python
if self.text != render_accepted_tool_evidence_for_llm(self.accepted_tool_evidence):
    raise ValueError("accepted evidence block text must use shared renderer")
```

直接代码证据：
- `render_accepted_tool_evidence_for_llm()` 是唯一 renderer（`dayu/host/evidence.py:158-177`）。
- 生产构造链通过 `run_input_material_block()` helper 直接以 renderer 输出构造 `text`。
- Dataclass exact-match 是阻止 `text` 与 typed material 分叉的 fail-closed invariant，不是第二文本真源。
- renderer 变更时同一运行时函数同时产生和校验文本。

### DS-02 — `mark_ready()` / `report_fatal()` 时序

**Controller 裁决**：`REJECTED_NOT_A_DEFECT / NO_FIX`

**Re-review 确认**：PASS。

`_execution_health.py` diff 确认：
- 模块 docstring（行 1-5）声明"opener event loop 拥有的单一 gate"。
- `mark_ready()` 是同步、无 `await` 的状态检查/写入（行 120-132）。
- `report_fatal()` 在 `async with self._admission_lock` 内执行（行 169-193）。
- 同一 event loop 内 `mark_ready()` 的 read/check/write 不会被 `report_fatal()` 抢占。
- 若 critical task 在此前报告 fatal，state 已置为 UNAVAILABLE；`mark_ready()` 第一分支抛出 typed error。

Controller 裁决理由完全成立：不添加"不可从异步上下文调用" docstring 是正确决定。

### DS-03 — Compact/memory event-ref consistency

**Controller 裁决**：`REJECTED_NOT_A_DEFECT / NO_FIX`

**Re-review 确认**：PASS。

`run_input.py` diff 确认 `_require_compact_memory_event_ref_consistency()` 逻辑：
- `compact_ref is None and memory_ref is None` → 正常放行（行 3073-3074）。
- `compact_ref is not None and memory_ref == compact_ref` → 正常放行（行 3075-3076）。
- 一方有 ref、另一方无 ref，或 ref 不同 → `MemoryProjectionRepairRequired`。

该行为是同一业务事实从同一真源传播的 owner invariant，不能放宽。测试覆盖双 `None`、同 ref、compact-only、memory-only、不同 ref 五种场景。

## 5. Adversarial Failure Pass

### 5.1 Topic-by-Topic 对抗验证

| Topic | 对抗维度 | 结论 |
| --- | --- | --- |
| 1 Doc budgets | 残留 budget 字段/逻辑 | PASS — rg 零命中 |
| 2 Web policy | private/port/DNS/browser/proxy 策略混合 | PASS — 全部独立 typed 字段 |
| 3 LLM-safe args | 黑名单残留、source 过滤残留 | PASS — rg 零命中 |
| 4 OpaqueEvidenceRef | opaque ref 泄露到 LLM-facing | PASS — 使用 unavailable 文案 |
| 5 Wait poller | observation timeout terminalize | PASS — 只 release/backoff |
| 6 Fins contracts | dual RESULT、HKEX 协议违规、raw field 暴露 | PASS — typed validator + official protocol |
| 7 CLI/init | 占位包残留、unsafe script publish | PASS — 全部移除 + containment |

### 5.2 Cross-Slice 交互

| 交互 | 状态 |
| --- | --- |
| Topic 3/4 → evidence → compact → memory | `AcceptedToolEvidenceLLMMaterial` 单一投影链，无重复解析 |
| Topic 5/6 → wait_adapter → fins_wait_adapter | Host 端口与 Service 适配器分离 |
| Topic 6/7 → fins batch plan → upload_script | Fins 拥有 batch classification，CLI 拥有 script rendering |

无新 drift。

### 5.3 Security Boundaries

| Boundary | Owner | Status |
| --- | --- | --- |
| API key/header Config internal SQLite/EventLog | trusted-local domain | PASS — 不进入 Tool Trace/audit/LLM-facing |
| Path containment | `_fs_identity.py`, `init_workspace.py`, `upload_script.py` | PASS — lexical/resolved + symlink rejection |
| Web egress | `web_egress_policy.py` | PASS — config-controlled |
| Sensitive header filtering | `web_diagnostics.py` | PASS — `_SENSITIVE_HEADER_FRAGMENTS` |

### 5.4 Unauthorized Implementation Leak Check

| Issue | Status |
| --- | --- |
| #177 TruncationManager | PASS — 无 leak |
| #178 storage-state lifecycle | PASS — 仅保留 config path |
| #142 workspace migration | PASS — 仅 init lock |
| #151 write/assets | PASS — 无 `dayu/assets` 导入 |
| #175 Docling process isolation | PASS — 无新增 Docling process 代码 |
| #84/#147 Web/WeChat | PASS — 占位入口已删除 |

## 6. Semantic Ownership Drift Pass

完整重新审查 Topic 1-7 的 semantic ownership 后，确认：

- LLM-facing 文本只包含业务可读语义，不暴露 `tool_call_id`、`event_id`、`payload_ref`、digest、cursor 等内部治理标识。
- 无 fallback、特例、`hasattr`/`getattr`、loose parsing、兼容 shim 补救上游 contract。
- 无下游消费者从 raw fields、内部字段、日志、字符串、时间戳、偶然顺序或历史行为反推语义。
- Durable state、trace、memory、audit、LLM-facing material 中同一业务事实从同一真源派生。
- 测试断言 owner-level contract 行为，不固化偶然行为。

Initial review 范围仍成立，无漂移。

## 7. Deferred / No-Code / Residual Ledger

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

与 initial review、Controller adjudication、Codex disposition 完全一致，无漂移。

## 8. Test Authenticity

Fresh aggregate validation evidence（AgentCodex artifact）确认：
- Canonical suite：5260 passed / 10 skipped / 5 deselected / 0 failed。
- Coverage：219/219 >=80.00%。
- Full pyright：0 errors, 0 warnings, 0 informations。
- Ruff：142 immutable findings，ADDED=0。

本轮 re-review 未重新运行测试（tree 未变），既有 accepted aggregate validation 证据保持不变。

## 9. Open Questions

无。

## 10. Residual Risk

与 initial review 一致：
- AR-F06：`wake_queue_promotion` 使用 tracked async promotion task，coverage 中被排除。
- AR-F07：Darwin skip 不作为 Windows success。
- Gemini：低 budget 测试账号，本 gate 无新 provider 请求。
- Issue trackers：保持既有 owner/destination，未实施。

## 11. Final Verdict

**PASS / NO_NEW_MATERIAL_FINDING / CONFIRMED**

完整重新审查 Topic 1-7 组合树、DS-01/02/03 裁决、semantic ownership drift、security boundaries、deferred/residual ledger 后，确认：

1. Initial review 完整范围仍成立，Topic 1-7 组合与安全/deferred/no-code/residual ledger 无漂移。
2. DS-01/02/03 Controller 裁决有直接代码证据且 zero-change 未错误实施。
3. 没有新 material finding / needs-evidence。
4. Config/Host internal trusted-local、projection plaintext-zero、Gemini no-code、AR-F06/AR-F07、Issues 142/151/175/177/178 与 Topic 8/9 状态准确。
5. HEAD/tree/staged 和全部 protected dirty hashes 不变（Controller-owned 文件的 SHA-256 变化属正常 gate 传播）。

## 12. Immutable Hashes 验证

| 项目 | 值 |
| --- | --- |
| HEAD | 85aa7184a694448a5b27da7cca52f753f84d6e20 |
| tree | 0db1c91f92dca594cf77c74bbde8f5b4fc42710d |
| staged | empty |
| review range | b1a0631f397967e7530b676a90ef7467d83a1817^..85aa7184a694448a5b27da7cca52f753f84d6e20 |

## 13. Artifact Integrity

Artifact final SHA 由 Controller 外部计算，不自嵌以避免自引用。
