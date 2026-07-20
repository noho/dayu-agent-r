# WU-SEMANTIC-OWNERSHIP-01 P2-D Plan Re-Review — AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P2-D`
- Gate: plan re-review (fixed plan verification)
- Reviewed artifacts:
  - Fixed plan: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-codex.md`
  - Plan fix: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-fix-codex.md`
  - Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-review-controller-adjudication.md`
  - MiMo review: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-review-mimo.md`
  - Original DS review: `docs/reviews/wu-semantic-ownership-01-p2-d-plan-review-ds.md`
- Agent: AgentDS

## Conclusion

**PASS**

全部 3 个 accepted findings 已正确关闭。无新 plan drift、过度 scope、下游补丁或测试夹具掩盖风险。Fixed plan 可进入 implementation gate。

---

## Finding Closure Verification

### P2D-PLAN-F01: Consumer inventory must include durable memory projection

- 来源：AgentDS `DS-F01`，severity MEDIUM，controller accepted。
- 要求：plan 把 `dayu/host/durable/memory.py` 纳入 affected production modules / consumer inventory，并说明它直接消费 `projection.source.text` 写 `evidence_source_text`，预计无需行为修改但必须验证。

**验证结果：已关闭。**

Fixed plan §"Affected Files / Modules" Production 列表已新增：

```
- `dayu/host/durable/memory.py`
  - 直接消费 `projection.source.text` 并写入 `_MemoryProjectionPayloadView.evidence_source_text`。
  - 预计无需行为修改；必须验证 source-unavailable projection 后 memory 投影继续与 accepted-result projection 同源一致。
  - implementation 必须检查并按需更新 memory projection `evidence_source_text` docstring，说明 accepted-result 正常路径由 projection owner 保证非空 source text；字段整体仍可保留 `str | None`，用于覆盖非 accepted-result、初始构造或 fallback 路径。
```

条目完整覆盖了 controller 要求的三个要素：(1) 文件列入，(2) 直接消费关系说明，(3) no-behavior-change 但必须验证的约束。

### P2D-PLAN-F02: Memory source docstring sync must be explicit

- 来源：AgentMiMo `F-01`，severity LOW，controller accepted。
- 要求：plan 显式要求 implementation 检查并按需更新 memory projection `evidence_source_text` docstring，说明 accepted-result 正常路径由 projection owner 保证非空 source text，字段整体仍可为 `str | None`。

**验证结果：已关闭。**

Fixed plan 在两处覆盖了此要求：

1. Affected Files / Modules — durable memory bullet（行 125-126）：
   > "implementation 必须检查并按需更新 memory projection `evidence_source_text` docstring，说明 accepted-result 正常路径由 projection owner 保证非空 source text；字段整体仍可保留 `str | None`，用于覆盖非 accepted-result、初始构造或 fallback 路径。"

2. Implementation Slices — Slice P2-D-S1（行 168-169）：
   > "仅当 docstring 同步需要时允许最小触碰 `dayu/host/durable/memory.py` 的 memory projection `evidence_source_text` 说明，不做行为修改。"

两处约束一致，明确区分了 docstring sync（允许）与行为修改（禁止）。

### P2D-PLAN-F03: Source-leak scan must include tests that assert the contract

- 来源：AgentDS `DS-F03`，severity LOW，controller accepted。
- 要求：scan guidance 覆盖 `dayu/host/accepted_result_projection.py` 和 `tests/host/test_accepted_result_projection.py`。

**验证结果：已关闭。**

Fixed plan 的 scan 小节已从原 "Optional source scan" 升级为 "Required source-leak scan"（行 194），rg 命令覆盖两个文件：

```
rg -n "event_id|payload_ref|payload_digest|cursor|policy|ToolRuntime|Host governance|digest" \
  dayu/host/accepted_result_projection.py tests/host/test_accepted_result_projection.py
```

并显式说明（行 200）：
> "该扫描必须覆盖 `dayu/host/accepted_result_projection.py` 和 `tests/host/test_accepted_result_projection.py`，防止 production 文案或测试期望意外认可内部 refs。"

scan 仍正确标注为辅助审查信号，最终以 LLM-facing 输出断言为准——与 controller 的 "not a mechanical pass/fail" 意图一致。

---

## New Issues Check

### Plan drift

无。核心方案（projection owner 处收紧 `AcceptedToolResultSourceProjection.text: str | None → str`，新增 source-unavailable 常量）未变。所有新增内容均为 additive patch，不修改原方案决策。

### Over-scope

无。新增内容严格限制在 controller 要求的范围内：
- 新增 affected file 条目（memory.py），标注 no-behavior-change。
- 新增 docstring sync 要求，约束为"检查并按需更新"。
- 升级 scan 为 required 并扩展覆盖文件。

未引入新抽象层、新模块、新 schema、新 public API、新 migration、新 configuration。

### Downstream patch risk

无。Fixed plan 继续明确拒绝在 compact material、RunInputBuilder、Memory、Tool Trace 或测试 fixture 中用特例分支补默认 source。Implementation Slice 对 memory.py 的触碰严格约束为 docstring-only，不允许行为修改。

### Test fixture masking

无。Fixed plan 继续明确拒绝修改 test fixture 绕过 source-unavailable。Targeted public compact smoke 保留原样，用于证明真实 residual 已被 owner 修复。

### Non-blocking notes follow-through

Controller adjudication 将 MiMo `F-02`（文案措辞）和 DS `DS-F02`（README 补充）归类为 non-blocking implementation notes。这两个 findings 不需要在 plan gate 关闭——fixed plan 的 §"README / Docs Decision" 和 §"Risks / Open Questions" 已充分覆盖这些注意事项，implementation closeout 时再最终裁决。AgentDS 对此无异议。

---

## Reviewer Signature

- Agent: AgentDS
- Review type: plan re-review (fixed plan verification)
- Conclusion: PASS
- Date: 2026-07-09
