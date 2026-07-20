# P3-E Plan Re-Review (AgentMiMo)

## Review Target

- Plan: `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-e-plan-review-controller-adjudication.md`
- Prior review: `docs/reviews/plan-review-20260711-005941.md`

Gate: plan re-review. Verify P3-E-PF-01 through P3-E-PF-06 are fully fixed; check for new material defects.

## Prior Fix Item Disposition

### P3-E-PF-01 — `last_error_code` preservation outside LLM-facing hint — **CLOSED**

Plan S1 now explicitly requires:

1. 审计 `dayu/host/tool_runtime.py` 中每个 `last_error_code` 路径 (line 110-113)。
2. 分类为三类：已由 owner diagnostics/failure metadata/Tool Trace 保留；需要更新 `message` 使其自包含；超出 S1 范围因为是 durable wait-state 诊断。
3. 明确禁止编码入 LLM-facing `hint`，但要求保留在 `message`、owner diagnostics、failure metadata 或 Tool Trace (line 114)。
4. 对 `_accept_failure_outcome` 和 `_awaiting_accept_failure_outcome` 的 timeout 分支逐一说明处理方式 (lines 118-119)。
5. 测试要求：增加使用非空 `last_error_code` 的 accept timeout / ack-lost 测试，证明 code 保留在 `message`、owner diagnostics、`failure_metadata` 或 Tool Trace 中，同时 `hint is None`。测试必须在 `last_error_code` 仅从 hint 移除而无替代诊断路径时失败 (line 127)。

验证点：S1 validation `rg` 输出包含 `last_error_code`，并要求审查保留的匹配是否属于 owner diagnostics / durable wait state / tests（line 136-140）。

**结论**：修复充分。audit + classification + preservation + regression test 构成完整闭环。

### P3-E-PF-02 — hint helper 和常量的确定性清理 — **CLOSED**

Plan S1 now explicitly requires:

1. 引用扫描后确定性删除 `_hint_with_diagnostic_refs`。
2. 删除三个私有常量：`_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`、`_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`、`_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR`。
3. 删除 hint 清理后不再被 `error`、`message`、diagnostics 或 tests 引用的 accept reason 常量（如 `_TOOL_RUNTIME_ACCEPT_REJECTED_REASON`、`_TOOL_RUNTIME_ACCEPT_TIMEOUT_REASON`）(line 120)。

措辞从 "if it becomes unused" 改为 "deterministically delete... after reference scan"。

**结论**：修复充分。从条件性删除改为确定性删除，消除了 implementation agent 跳过清理的风险。

### P3-E-PF-03 — LOST vs UNKNOWN 语义区分与 `_result_payload(...)` 审计 — **CLOSED**

Plan S2 now explicitly requires:

1. 检查 `_result_payload(...)` 的每个 `result_payload=None` 出口 (line 181)。
2. 如果 payload unavailable diagnostics 存在，返回 `LOST`。
3. 如果 `_result_payload(...)` 审计发现 `result_payload=None` 出口没有对应诊断，在 projection owner 处修复 `_result_payload(...)` 发出诊断；不从 `raw_outcome is None` 推断 `LOST` (line 183)。
4. 如果 payload 可用但 typed status 字段缺失或空白，返回 `UNKNOWN`；追加 `accepted_status_unavailable` 诊断 (line 184)。
5. 明确语义区分："unavailable accepted result payload means `LOST`; available payload with missing / blank / unrecognized typed accepted status means `UNKNOWN`" (line 185)。
6. 增加 unavailable payload 测试 (line 195)。

**结论**：修复充分。语义区分清晰，`_result_payload(...)` 审计要求覆盖了从 `raw_outcome` 推断 `LOST` 的风险。

### P3-E-PF-04 — `UNKNOWN` status 下游 consumer 覆盖 — **CLOSED**

Plan S2 now explicitly requires consumer regression checks (lines 198-203):

1. `read_api`: activity state 保持 fail-closed，不 crash 或从 raw outcome 重分类。
2. `run_input` / evidence material: LLM-facing material 包含自解释的 unknown status 或明确省略。
3. memory projection: handle `UNKNOWN` without converting to completed/failed from raw outcome。
4. compact material: handle `UNKNOWN` consistently with projection status。

对无直接代码路径的 consumer，要求记录 no-op evidence with `rg` result (line 203)。

**结论**：修复充分。四个 consumer 均有显式覆盖或 no-op evidence 要求。

### P3-E-PF-05 — producer lifecycle 审计与 no-hang 验证 — **CLOSED**

Plan S3 now explicitly requires (lines 251-256):

1. 审计 `_DirectStreamProducerDone` lifecycle before implementing RESULT buffering。
2. 确认 normal producer completion puts exactly one sentinel。
3. 确认 producer exception paths put sentinel after surfacing exception。
4. 确认 every producer path that emits terminal `RESULT` returns or reaches sentinel promptly。
5. 确认 no producer relies on current early `break` after first `RESULT` for cleanup。
6. Record audit evidence with source line references。

Stop conditions (lines 308-311):
- lifecycle audit 无法证明 sentinel emission on normal/exception/terminal-result paths → stop。
- buffering 导致 hang → stop at Fins runtime owner；不加 downstream timeout hack。

Tests (line 285): no-hang validation test consuming normal direct stream through drain-until-sentinel path。

**结论**：修复充分。audit 在 buffering 之前执行，stop conditions 明确且 actionable，no-hang test 作为 regression guard。

### P3-E-PF-06 — `FinsDirectStreamProtocolError` 作为唯一 source of truth，CLI disposition — **CLOSED**

Plan S3 now explicitly requires (lines 272-275):

1. Fins-owned `FinsDirectStreamProtocolError` 是 direct stream protocol violation 的唯一 source of truth。
2. 删除 CLI-local `FinsDirectStreamContractViolation`（如果只表示 missing terminal result）。
3. CLI-local raises 替换为 `FinsDirectStreamProtocolError(MISSING_RESULT, ...)` 或让已 typed 的 Service/runtime error 传播。
4. CLI 如需 command-exit formatting，直接 catch/render `FinsDirectStreamProtocolError`，不引入第二个异常类型。

Allowed files include `dayu/cli/commands/fins.py` and `tests/cli/test_fins_commands.py` (lines 243-244)。

Validation (line 292): source scan 确认 `FinsDirectStreamContractViolation` 无 remaining production references。

**结论**：修复充分。CLI disposition 明确，验证覆盖完整。

## New Material Defects Introduced By Plan-Fix

扫描 plan-fix 引入的所有变更，检查是否引入新的 material plan defects：

1. **S1 `last_error_code` audit scope 是否足够**：plan 要求审计 "every `last_error_code` reference in `dayu/host/tool_runtime.py` accept / awaiting-accept paths" (line 110)。限定在 accept/awaiting-accept paths 是正确的，因为只有这些路径会将 `last_error_code` 编码入 `hint`。其它路径（如 durable wait state）的 `last_error_code` 使用不在 S1 scope 内，由 plan line 113 明确排除。**无新 defect。**

2. **S2 `_result_payload(...)` audit 是否充分**：plan 要求 "enumerate every exit that returns `result_payload=None` and prove it appends `result_payload_unavailable` or `event_payload_unavailable`" (line 181)。这是完整的——implementation agent 必须枚举每个出口。如果审计发现遗漏，plan 要求在 projection owner 处修复（line 183），不是在 `_accepted_status` 中推断。**无新 defect。**

3. **S2 LOST vs UNKNOWN 定义是否自相矛盾**：plan 说 "If payload unavailable diagnostics exist, return `LOST`" (line 183) 和 "If payload is available but neither typed status field exists or both are blank/unknown, return `UNKNOWN`" (line 184)。这两个条件互斥且穷尽（payload 要么 unavailable 要么 available）。**无新 defect。**

4. **S3 lifecycle audit 是否阻塞 RESULT buffering 实现**：plan 说 "Before implementing RESULT buffering, audit..." (line 251)。audit 是 buffering 的前置条件，不是可选步骤。**无新 defect。** 这正是 P3-E-PF-05 的核心要求。

5. **S3 CLI `FinsDirectStreamContractViolation` 删除是否过激**：plan 使用 "delete... if it only represents missing terminal result" (line 273)。这个条件性措辞是安全的——implementation agent 必须先确认 CLI exception 的语义范围再删除。如果它覆盖了非 protocol-violation 场景，agent 不应删除。**无新 defect。**

6. **S1/S2/S3 validation 是否有重叠或遗漏**：S1 validation 覆盖 hint 相关源码扫描；S2 validation 覆盖 accepted status 和 consumer 源码扫描；S3 validation 覆盖 Fins direct 和 CLI 源码扫描。Aggregate validation (lines 342-350) 将所有 source scan 合并。三个 slice 的 validation 无重叠遗漏。**无新 defect。**

**新 material defect 数量：0。**

## Open Questions

无 blocking open question。

## Residual Risks

1. **`_TOOL_RUNTIME_ACCEPT_REJECTED_REASON` 和 `_TOOL_RUNTIME_ACCEPT_TIMEOUT_REASON` 常量**：plan line 120 要求删除 hint 清理后不再被引用的 accept reason 常量，但未显式列出这两个常量名。plan 的 `rg` validation (line 136) 包含 `accept_rejected:` 模式，覆盖了残留检测。这是 implementation detail 级别的 residual，不构成 plan defect。

2. **S2 consumer no-op evidence 质量**：plan 允许 implementation agent 记录 no-op evidence 而非写测试（line 203）。controller 在 aggregate validation 时需确认 no-op evidence 是否充分（如 `rg` 结果确实证明 consumer 无 accepted status 代码路径）。这是 controller validation 职责，不是 plan defect。

3. **S3 `_direct_missing_result_event` 和 `_missing_result_event` 的 "if unused" 条件**：plan line 266 和 270 使用 "if unused" 措辞。与 P3-E-PF-02 修正的 S1 不同，S3 的 "if unused" 是安全的——因为 S3 已经要求 FinsDirectStreamProtocolError 替代 synthetic missing result path，这两个 helper 必然变为 unused。implementation agent 验证 `rg` 确认无引用后删除即可。

## Conclusion

**PASS**

Re-review 确认 P3-E-PF-01 到 P3-E-PF-06 全部修复充分。plan-fix 将 plan 从 "pass-with-risks" 提升到可直接交给 implementation agent。所有 6 个 prior fix item 均有明确的 implementation detail、validation scan 和 regression test 要求。plan-fix 未引入新的 material defect。

Plan 整体质量高：owner boundary 正确，3 个 slice 语义连贯，架构边界清晰，无过度设计，实现细节具体到文件和测试级别。

## Artifact Metadata

- reviewed target: `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md`
- scope: P3-E plan re-review (post plan-fix)
- prior fix items verified: 6 (P3-E-PF-01 through P3-E-PF-06)
- prior fix items closed: 6
- prior fix items still open: 0
- new material defects: 0
- conclusion: pass
- blocking questions: 0
