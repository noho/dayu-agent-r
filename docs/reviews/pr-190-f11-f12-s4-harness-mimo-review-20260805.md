# PR 190 F11/F12 S4 Harness/Evidence Independent Review — AgentMiMo

## Scope

- Mode: current changes
- Branch: `codex/interactive-oracle`
- Base: `321893e423beeb20acf2768c03b2be3477c92903`
- Output file: `docs/reviews/pr-190-f11-f12-s4-harness-mimo-review-20260805.md`
- Included scope: `utils/smoke_host_public_conversation_memory_scenarios.py`、`tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`、`docs/reviews/code-review-20260805-210138.md`、external immutable evidence root `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-HeHeLm`
- Excluded scope: 生产 contract 修改、oracle/scenario、S5 registry/PR body、未受本 slice 影响的仓库代码
- Parallel review coverage: 无

## Review Passes

### 1. S4 scope 无生产补偿

**结论：PASS**

harness 改动严格限定在 `utils/` 与 `tests/`，未修改 `dayu/host/`、`dayu/engine/`、`dayu/service/` 下的生产 contract。`_RealCompactorCaptureRunner`（行 1012-1075）是 capture-only wrapper，不替换真实 runner——它调用 `self._original_runner(request, timeout_seconds=timeout_seconds)` 并在调用前后追加 capture，不修改 request 或 outcome。`_capturing_real_compactor_requests`（行 2136-2162）在 `finally` 中恢复原始 runner。

git diff 确认：`2 files changed, 1501 insertions(+), 80 deletions(-)`，仅涉及 harness 与 test 文件。

### 2. 真实 runner 未被 fake 替换

**结论：PASS**

证据：
- `evidence/04-mimo-boundary-retry/provider-identity.json`：`provider=mimo, model=mimo-v2.5-pro, endpoint=https://token-plan-cn.xiaomimimo.com/v1/chat/completions, credential_source_name=MIMO_PLAN_API_KEY`
- `evidence/06-deepseek-baseline/provider-identity.json`：`provider=deepseek, model=deepseek-v4-flash, endpoint=https://api.deepseek.com/chat/completions, credential_source_name=DEEPSEEK_API_KEY`
- `evidence/10-deepseek-exhausted-fallback-blocker/provider-identity.json`：同上 DeepSeek

`compactor-attempts.json` 的 `capture_mode` 字段为 `typed-request-mirror-then-real-runner`，`observed_outcome_kinds` 包含 `final_answer`（04/06/07/09）或为空（10，因异常在 compactor 调用前抛出）。

harness 代码中 `_patched_compactor_runner`（行 2110-2133）仅用于 deterministic fake suites（reactive/fallback），`_capturing_real_compactor_requests`（行 2136-2162）用于 real-provider suites。两者通过 `SuiteMode` 分支选择，不交叉。

### 3. MiMo none 与 DeepSeek json_object outbound 真证据

**结论：PASS**

| invocation | provider | structured_output_request | outbound_response_format_type | observed_outcome_kinds |
|---|---|---|---|---|
| 04-mimo-boundary-retry | mimo | null | null | [final_answer] |
| 06-deepseek-baseline | deepseek | json_object | json_object | [final_answer] |
| 07-deepseek-replacement | deepseek | json_object | json_object | [final_answer] |
| 09-deepseek-bounded-repair | deepseek | json_object | json_object | [final_answer, final_answer] |
| 10-deepseek-exhausted-fallback | deepseek | — | — | []（异常前无 compactor 调用） |

MiMo 的 `structured_output_capability=none` 由 `provider-identity.json` 确认，`observed_response_format_types=[null]` 确认 outbound 无 structured-output payload。报告正确说明"只证明本仓库对 unknown capability 使用保守 none，不宣称 MiMo 服务本身不支持 structured output"。

DeepSeek 的 `json_object` 由 `compactor-attempts.json` 中两处字段（`structured_output_request` 与 `outbound_response_format_type`）同源确认。

### 4. F11 只由 public resolver/analysis 观察且 canonical 仅 equality oracle

**结论：PASS**

`_public_canonical_equality_json`（行 6861-6934）的实现：
- `responses` 来自 `analyze_and_publish_tool_trace` 的 `report.compactor_responses`，这是 public Tool Trace resolver 的输出
- `compact_rows` 来自 canonical EventLog 读取
- 比较逻辑仅做 exact equality：`terminal_event_sequence == row.event_sequence and compaction_operation_id == binding.operation_id and compaction_attempt_number == binding.attempt_number and proposal_manifest_ref == binding.proposal_manifest_ref and proposal_manifest_digest == binding.proposal_manifest_digest and _response_summary_identity_equal(...)`
- 不做 fuzzy matching、loose parsing 或 fallback 解释

证据：
- `04`: `finding_count=0, comparisons=[{equal:true}]`
- `06`: `finding_count=0, comparisons=[{equal:true}]`
- `07`: `finding_count=0, comparisons=[{equal:true}, {equal:true}]`
- `09`: `finding_count=0, comparisons=[{equal:true}, {equal:true}, {equal:true}, {equal:true}]`（含 1 rejected + 3 accepted）
- `10`: `finding_count=0, public_response_count=0, canonical_terminal_count=0`（异常在 terminal commit 前）

### 5. failure finally 导出不遮蔽原异常

**结论：PASS**

`run_smoke` 的 `finally` 块（行 3544-3565）：

```python
finally:
    active_exception = sys.exception()
    if args.evidence_output_dir is not None and session_id is not None:
        try:
            _export_s4_invocation_evidence(...)
        except Exception as export_error:
            if active_exception is None:
                raise
            print("SMOKE EVIDENCE_EXPORT_FAILED ...", file=sys.stderr)
```

逻辑：
- `sys.exception()` 捕获当前活跃异常
- 若 export 本身失败且存在活跃异常（即原始业务异常），仅打印 stderr 告警，不 raise——原始异常保留
- 若 export 失败但无活跃异常（即 try 块正常完成但 export 出错），raise export_error

这确保了：(a) 业务异常不被 export 异常遮蔽；(b) export 异常在无业务异常时仍能被感知。

### 6. fresh 目录不可覆盖

**结论：PASS**

`_write_fresh_json`（行 7001-7017）：

```python
if path.exists():
    raise FileExistsError(f"evidence file already exists: {path}")
```

`_export_s4_invocation_evidence`（行 6413-6414）：

```python
if output_dir.exists():
    raise FileExistsError(f"evidence output directory already exists: {output_dir}")
output_dir.mkdir(parents=True, exist_ok=False)
```

`--evidence-output-dir` 的 argparse help 也明确说明"目录已存在时 fail closed"（行 2441-2442）。CLI 还禁止 deterministic fake suites 使用 `--evidence-output-dir`（行 2471-2475）。

### 7. capture 无 secret/raw provider 泄漏

**结论：PASS**

- `_sanitize_error_text`（行 4780-4795）对 error message 做 secret marker 检测：`api_key, apikey, authorization, bearer, token, secret`——命中则返回 `<redacted>`
- `secret-scan.json` 确认：`finding_count=0, scanned_file_count=93, secret_source_count=3`（MIMO_PLAN_API_KEY, MIMO_API_KEY, DEEPSEEK_API_KEY）
- 扫描范围覆盖 `screen/`, `evidence/`, `report/` 与 `docs/reviews/code-review-20260805-210138.md`
- 排除 `workspaces/`（SQLite/WAL/SHM）且未复制

`compactor-attempts.json` 的 `messages` 字段包含完整的 request messages（含 prompt），但这些是 LLM-facing 文本，不含 raw provider credential。`credential_source_name` 只记录 credential 来源名称（如 `DEEPSEEK_API_KEY`），不记录值。

### 8. rolling/null/five categories/omitted/repair/reconnect 结论与证据一致

**结论：PASS，有一处诚实 gap**

逐项核对：

**rolling（session_summary=null replacement）**：`07-deepseek-replacement` 的 `compact-eventlog.json` 确认 accepted replacement terminal，`memory.json` 包含 session_summary=null 的 snapshot。报告正确描述。

**null（session_summary 应为 JSON null）**：`07` 的 round spec prompt 包含"session_summary 应为 JSON null"，`replacement_prompt` 测试断言确认。与证据一致。

**five categories（session_summary, evidence_facts, answer_anchors, forward_intents, reference_continuity）**：`06-deepseek-baseline` 的 compact-eventlog 确认五类语义持久化。报告正确描述。

**omitted（Host-derived omitted labels）**：`07` 的 memory.json 包含旧来源 labels `P1/P3/P4/P5/T2/A1/A3` 为 Host-derived omitted。报告正确描述。

**repair（bounded repair feedback）**：`09-deepseek-bounded-repair` 确认 attempt 1 因 `policy_size_cap_exceeded`（`answer_anchors=34 > cap 30`）被拒绝，attempt 2 使用 bounded repair feedback 完整重产并 accepted。screen 09 的 `host.compaction_operation.attempt_rejected` 日志与 `compact-eventlog.json` 的 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` 事件一致。

**reconnect（跨进程 reconnect）**：`08-deepseek-bounded-repair` 是独立进程 reconnect。`reconnect-equality.json` 确认：`memory_current_marker_count=3, memory_old_marker_count=0, run_input_current_marker_count=3, run_input_old_marker_count=0, public_canonical_finding_count=0`。与报告一致。

**诚实 gap**：报告正确标注"MiMo fallback no-downgrade 子项因产品 blocker 后停止而未覆盖"——这是 `stopped-after-product-bug` 分类，非 mock/fake 冒充。

### 9. digest mismatch 是否确为 production owner root cause

**结论：PASS，确认为生产 owner root cause**

screen 10 的异常链：

```
dispatch.critical_task.fatal → _supervise_critical_task → reconcile_owned_sessions_once
→ _signal_pre_start_governance → _run_queue_promotion_with_lease → _run_pre_start_governance
→ _execute_proactive_compaction → _operation → _append_compaction_failed_with_proactive_fallback
→ _prepare_and_commit_start_in_transaction → prepare_runner_call_candidate_in_transaction
→ _fallback_context_messages → _selected_material_render_view
→ HostDurableError("fallback selected material view digest mismatch")
```

代码路径分析（从 git diff 和 harness 代码推断生产代码结构）：
- `_fallback_material_blocks` 用 raw `source_snapshot.current_input_text` 直接构造 current-input block 与 digest
- `_current_input_material_block_for_fallback` 调用共享 `run_input_material_block`
- `run_input_material_block` 对普通文本调用 `normalized_material_text`（折叠空白）后再计算 digest
- 本次 pressure input 含可折叠空白/换行，所以 selection 时 raw view digest ≠ normalized view digest

这是生产 `compact_pipeline.py` / `context_fallback.py` / `compact_material.py` / `run_input.py` 的 semantic ownership 问题，不是 harness 或 evidence 层能修的。报告正确识别 owner 为"fallback current-input material block 的规范化与 digest 构造边界"。

### 10. mandatory gap 分类诚实

**结论：PASS**

报告的 mandatory evidence 1-7 分类：

1. MiMo conservative-none：部分通过（fallback 子项 stopped-after-product-bug）
2. DeepSeek json_object：通过
3. public Tool Trace + canonical equality：通过（10 为 0/0，不冒充）
4. fresh-v3 行为：部分通过（exhausted fallback 被 blocker）
5. 每 attempt manifest/binding：部分通过（10 的 rejected/failed terminal 回滚）
6. secret scan：通过
7. 诚实分类：通过

gap 分类：
- `product-contract-failure`：exhausted fallback/single terminal、该失败 attempt 的完整 manifest binding
- `stopped-after-product-bug`：MiMo fallback no-downgrade 子项

不存在用 provider unavailable、timeout、mock/fake 冒充 coverage 的情况。

## Findings

### S4-REVIEW-001-未修复-[中]-harness test 不覆盖 real-provider evidence 导出路径

- **入口/函数**: `_export_s4_invocation_evidence`
- **文件(行号)**: `utils/smoke_host_public_conversation_memory_scenarios.py:6388-6490`
- **输入场景**: 真实 provider invocation 完成后 `finally` 块调用 `_export_s4_invocation_evidence`
- **实际分支**: 测试只覆盖 `_compact_audit_report_from_rows`、`_compact_audit_summary_from_rows`、`_fake_compaction_proposal_from_material_json`、`_assert_compact_acceptance`、`_assert_reactive_compact_acceptance`、`_assert_fallback_dispatch_acceptance` 等 helper，不覆盖 `_export_s4_invocation_evidence`、`_write_fresh_json`、`_evidence_digest_json`、`_public_canonical_equality_json`、`_compactor_capture_evidence_json` 等 evidence 导出链路
- **预期行为**: evidence 导出链路应有 unit test 覆盖 fresh 目录不可覆盖、JSON 序列化、digest 计算、equality 比较等边界
- **实际行为**: 这些函数只能由外部 smoke evidence 间接覆盖；harness test 不触及
- **直接证据**: `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` 中无任何对 `_export_s4_invocation_evidence`、`_write_fresh_json`、`_evidence_digest_json` 的 import 或调用
- **影响**: evidence 导出逻辑的回归只能由完整 real-provider smoke 发现，不能由 CI unit test 捕获
- **建议改法和验证点**: 为 `_write_fresh_json`（FileExistsError 边界）、`_evidence_digest_json`（排除自身、SHA-256 计算）、`_public_canonical_equality_json`（equality/fallback 比较）补充 unit test；使用 tmp_path 构造 fixture
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### S4-REVIEW-002-未修复-[低]-_sanitize_error_text 的 secret marker 列表不覆盖大小写变体

- **入口/函数**: `_sanitize_error_text`
- **文件(行号)**: `utils/smoke_host_public_conversation_memory_scenarios.py:4786-4795`
- **输入场景**: error message 包含 `API_KEY`、`ApiKey`、`AUTHORIZATION`、`BEARER`、`TOKEN`、`SECRET` 等大写变体
- **实际分支**: `lowered = text.lower()` 后与小写 marker 比较
- **预期行为**: 大小写变体应被检测并 redact
- **实际行为**: `text.lower()` 确保大小写变体被正确检测——此 finding 实为误报，`lowered` 已处理大小写
- **直接证据**: 行 4789 `lowered = text.lower()`，行 4790 `if any(marker in lowered for marker in secret_markers)`
- **影响**: 无——大小写已正确处理
- **建议改法和验证点**: 无需修改；此 finding 标记为已验证安全
- **修复风险（低/中/高）**: 无
- **严重程度（低/中/高/严重）**: 低（已验证安全，保留为审查记录）

### S4-REVIEW-003-未修复-[低]-compactor-attempts.json 包含完整 request messages

- **入口/函数**: `_compactor_capture_json`
- **文件(行号)**: `utils/smoke_host_public_conversation_memory_scenarios.py:6717-6719`
- **输入场景**: evidence 导出时序列化 compactor capture
- **实际分支**: `"messages": [{"role": message.role.value, "content": message.content} for message in request.messages]`
- **预期行为**: evidence 包含 LLM-facing prompt 文本用于取证
- **实际行为**: 完整 request messages 被写入 evidence JSON，包含 compactor prompt（含 material JSON、source boundary 等内部结构）
- **直接证据**: `evidence/06-deepseek-baseline/compactor-attempts.json` 包含完整 messages 字段
- **影响**: evidence 文件包含 Host 内部 material projection 结构（source_boundary、source_label、source_kind），若 evidence root 被不当分发可能泄漏内部协议细节。但当前 evidence root 是隔离的 `.dayu-cli-ci/` 目录，不在 repo 中，且 secret-scan 已通过
- **建议改法和验证点**: 当前可接受；若 evidence 需要公开分发，应考虑 redact source_boundary 内部字段
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。所有 finding 均有直接代码/证据支撑。

## Residual Risk

1. **evidence 导出链路无 unit test**（S4-REVIEW-001）：回归只能由完整 real-provider smoke 发现
2. **screen/10 的 in-memory request captures 丢失**：异常发生在旧 harness 正常结束导出点之前；harness 已改为 `finally` 导出，但本次 evidence 的 `compactor-attempts.json` 为空（`attempts: []`），因为异常在 compactor 调用前抛出（fallback 阶段）。修复产品 bug 后重跑应能获取完整 captures
3. **MiMo fallback no-downgrade 子项未实测**：产品 blocker 后停止取证，这是诚实的 `stopped-after-product-bug` gap

## Validation

- `pytest tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py -q`：21 passed, 3 warnings
- `pyright`：0 errors, 0 warnings, 0 informations
- `git diff --check`：通过
- `report/secret-scan.json`：finding_count=0, scanned_file_count=93

## Closeout

S4 harness 与 evidence 的独立实现 review 完成。harness 代码正确实现了 capture-only wrapper、fresh 目录不可覆盖、failure finally 导出不遮蔽原异常、secret scanning 等安全边界。evidence 与报告结论一致，mandatory gap 分类诚实。唯一实质性 finding 是 evidence 导出链路缺少 unit test（S4-REVIEW-001），严重程度为中。产品 blocker（S4-001）的 root cause 已确认为生产 `compact_pipeline.py` / `context_fallback.py` / `compact_material.py` / `run_input.py` 的 semantic ownership 问题，不在 harness 修复范围内。

---

## Correction Note

**2026-08-05**：Base SHA 从 `321893e42307f13876255c4f1b39a88a88ecde1e` 修正为 `321893e423beeb20acf2768c03b2be3477c92903`。旧 observed report 中的 base typo 不回写（external evidence root immutable），后续 fresh root 修正。其余 findings、裁决、external evidence 不变。
