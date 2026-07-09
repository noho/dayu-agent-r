# WU-SEMANTIC-OWNERSHIP-01 P2-D Plan Re-Review — AgentMiMo

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-D`
- Gate: plan re-review
- Fixed plan artifact: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-codex.md`
- Plan fix artifact: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-review-controller-adjudication.md`
- Original review: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-review-mimo.md`
- DS review: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-review-ds.md`

## Accepted Finding Closure Check

### P2D-PLAN-F01: consumer inventory 必须包含 durable memory projection

**检查项：** plan 是否把 `dayu/host/durable/memory.py` 纳入 affected production modules / consumer inventory，并说明它直接消费 `projection.source.text` 写 `evidence_source_text`，预计无需行为修改但必须验证。

**结果：通过。**

Fixed plan `Affected Files / Modules` Production 列表（第 124-126 行）新增：

> - `dayu/host/durable/memory.py`
>   - 直接消费 `projection.source.text` 并写入 `_MemoryProjectionPayloadView.evidence_source_text`。
>   - 预计无需行为修改；必须验证 source-unavailable projection 后 memory 投影继续与 accepted-result projection 同源一致。

与 controller adjudication P2D-PLAN-F01 要求完全一致。plan fix artifact 第 22-25 行确认已修复。

---

### P2D-PLAN-F02: memory source docstring 同步必须显式

**检查项：** plan 是否要求 implementation 检查并按需更新 memory projection `evidence_source_text` docstring，说明 accepted-result 正常路径由 projection owner 保证非空 source text，字段整体仍可为 `str | None`。

**结果：通过。**

Fixed plan 第 126 行新增 implementation 要求：

> implementation 必须检查并按需更新 memory projection `evidence_source_text` docstring，说明 accepted-result 正常路径由 projection owner 保证非空 source text；字段整体仍可保留 `str | None`，用于覆盖非 accepted-result、初始构造或 fallback 路径。

与 controller adjudication P2D-PLAN-F02 要求完全一致。plan fix artifact 第 28-32 行确认已修复，并明确 implementation slice 只允许为最小 docstring 同步触碰该文件，不得做行为修改。

---

### P2D-PLAN-F03: source-leak scan 必须覆盖测试文件

**检查项：** plan source-leak scan 是否覆盖 `dayu/host/accepted_result_projection.py` 和 `tests/host/test_accepted_result_projection.py`。

**结果：通过。**

Fixed plan `Validation Plan` 节（第 196-199 行）已将 scan 从 "Optional source scan" 改为 "Required source-leak scan"，命令明确包含两个文件：

```bash
rg -n "event_id|payload_ref|payload_digest|cursor|policy|ToolRuntime|Host governance|digest" dayu/host/accepted_result_projection.py tests/host/test_accepted_result_projection.py
```

并说明"该扫描必须覆盖 `dayu/host/accepted_result_projection.py` 和 `tests/host/test_accepted_result_projection.py`"。与 controller adjudication P2D-PLAN-F03 要求完全一致。plan fix artifact 第 35-39 行确认已修复。

---

## Plan Drift / Over-scope / Downstream Patch / Test Fixture Masking 风险

**结果：无新风险。**

逐项检查：

1. **Plan drift：** fixed plan 的改动仅限 controller adjudication 要求的三处，未引入新 scope、新目标或新 non-goal。
2. **Over-scope：** durable memory 的 production bullet 明确限定为"预计无需行为修改"和"最小 docstring 同步"，implementation slice 的 Allowed production files 也重申"仅当 docstring 同步需要时允许最小触碰 `dayu/host/durable/memory.py` 的 memory projection `evidence_source_text` 说明，不做行为修改"（第 168 行）。scope 收敛。
3. **Downstream patch：** 未在 compact material、RunInputBuilder、Memory、Tool Trace 或测试 fixture 内新增特例分支或 fallback helper。
4. **Test fixture masking：** plan 继续要求"不修改 fixtures 来绕过 source-unavailable"（第 170 行），targeted smoke 应证明真实 residual 已被 owner 修复。

## Conclusion

**Pass。**

三个 accepted findings（P2D-PLAN-F01、P2D-PLAN-F02、P2D-PLAN-F03）均已在 fixed plan 中正确关闭，与 controller adjudication 要求一致。未引入新 plan drift、过度 scope、下游补丁或测试夹具掩盖风险。

| Finding | Severity | 关闭状态 |
|---|---|---|
| P2D-PLAN-F01 | MEDIUM | 已关闭 |
| P2D-PLAN-F02 | LOW | 已关闭 |
| P2D-PLAN-F03 | LOW | 已关闭 |

plan 可进入 implementation gate。
