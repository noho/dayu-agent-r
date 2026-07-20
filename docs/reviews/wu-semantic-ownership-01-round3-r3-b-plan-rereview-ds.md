# R3-B Plan Re-Review — AgentDS

## Re-Review Scope

- **Target**: `docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`（plan-fix 后）
- **Review gate**: plan re-review（plan-fix 后的 adversarial re-review）
- **Baseline reviews**:
  - AgentMiMo: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-mimo.md` — 2 findings (1 中, 1 低)
  - AgentDS: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-ds.md` — 3 findings (均低)
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-controller-adjudication.md` — 5 accepted (PF-01..PF-05)
- **Plan-fix artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-fix-codex.md`
- **Date**: 2026-07-12

## Re-Review Focus（per 用户指令）

1. PF-01..PF-05 是否落实到具体 implementation decisions / assertions / negative matrix / validation commands
2. 是否保持 3 slices，未扩大 scope，未改变 7/1/2 source finding 裁决
3. 是否没有引入 Host 下游补救、compat shim、provider capability profile、通用 JSON Schema engine
4. Validation commands 是否可执行

## PF Verification Matrix

| PF | 裁决来源 | 严重度 | Plan 落实位置 | 验证 |
|---|---|---|---|---|
| PF-01 | AgentMiMo F01 | 中 | S1 decision #5 (line 108-109), S1 assertions (line 174-175), S1 validation commands (line 185) | ✅ 5 个 post-done 反例测试名、测试驱动方法（anext + request_cancel）、五路预期行为、validation commands 含精确 node ids |
| PF-02 | AgentMiMo F02 | 低 | S2 decision #7 (line 127), S2 validation commands (line 254, 259), aggregate validation (line 353, 360) | ✅ 语义级 FinishReason.TOOL_CALLS scan、逐项人工分类审计要求、三个 exact scans 保留（arguments coercion、direct forcing、partial merge） |
| PF-03 | AgentDS F1 | 低 | S2 decision #4 (line 124), S2 decision #5 (line 125), S2 negative matrix (line 238-239), S2 validation commands (line 249) | ✅ 三种 routing signal 统一声明、position positive continuation 保留、position-routed conflict 反例描述、单点测试 id |
| PF-04 | AgentDS F2 | 低 | S1 decision #8 (line 111), S1 decision #9 (line 112), S1 assertions (line 177), S1 validation commands (line 185, 190) | ✅ 所有 failure_candidate 写入强制通过 first-candidate helper、agent.py 唯一赋值 scan、exception+cancel 并发规则、first-candidate 保留测试 |
| PF-05 | AgentDS F3 | 低 | S1 decision #10 (line 113), S1 assertions (line 178), S1 validation commands (line 185, 189) | ✅ 删除 or STOP、_consume_runner_event 前验证 finish_reason、cast(None) malformed 测试、or STOP deletion scan |

## PF 逐项深度检查

### PF-01: post-done cancellation rejection test matrix

- **S1 decision #5** (line 108) 明确测试方法：手动 `anext()` → `ITERATION_COMPLETED` → `token.request_cancel()` → 继续迭代。禁止 Runner 自取消 helper（因其时点歧义）。✅
- **S1 assertions** (line 174) 列出 5 个精确测试名覆盖全部五路。✅
- **S1 assertions** (line 175) 定义预期：前四类→原 terminal（FINAL_ANSWER/RUN_FAILED），tool-call→先 batch-ready/requested 再 handshake。✅
- **S1 validation commands** (line 185) 含 8 个 focused test node ids，覆盖 post-done（5 路）、first-candidate 保留、exception+cancel 并发、malformed finish_reason。✅
- **Done 前取消** (line 176) 继续要求 RUN_CANCELLED，不倒置旧语义。✅

### PF-02: finish_reason forcing semantic guard

- **S2 decision #7** (line 127) 明确禁止 parser 直接赋值 FinishReason.TOOL_CALLS；只允许 `_choice_policy` wire fact、比较/诊断分支、fail-closed terminal policy。✅
- **S2 validation commands** 保留三个 exact scans（line 252-255），新增 `FinishReason.TOOL_CALLS` 语义级 scan（line 254），且要求逐项分类审计（line 259）。✅
- **Aggregate validation** (line 353, 360) 同步加入同一语义 scan。✅
- **Completion rule** (line 259) 明确 helper 重命名不能替代人工审计。✅

### PF-03: position routing identity conflicts

- **S2 decision #4** (line 124) 声明 index/id/position 是三种 routing signal，统一进入 identity-binding validator。✅
- **S2 decision #5** (line 125) 保留合法 position continuation（无歧义 partial 追加）。✅
- **S2 negative matrix** (line 238-239) 含 position positive continuation 与 position-routed conflict 反例，具体场景：A(index 0)+B(synthetic)→B 声明 index 0→fatal。✅
- **S2 validation commands** (line 249) 含精确 test id `test_position_routed_conflict_fails_closed_without_merge`。✅
- **Aggregate re-review** (line 336) 要求验证 position-routed fragment 遇到 occupied target fatal。✅

### PF-04: runner exception first-candidate helper

- **S1 decision #8** (line 111) 强制所有 `failure_candidate` 写入通过 helper；`agent.py` 除 helper 内部赋值外禁止直接写。✅
- **S1 decision #9** (line 112) 定义 exception + cancel + no-done 并发 = pre-done `run_cancelled`；未取消且无已有 candidate = `runner_exception`。✅
- **S1 assertions** (line 177) 含 first-candidate 保留测试与 exception+cancel 并发测试。✅
- **S1 validation commands** (line 185) 含 `test_runner_exception_preserves_first_failure_candidate` 与 `test_runner_exception_and_cancel_without_done_prefers_cancel`。✅
- **S1 scan** (line 190) `state.failure_candidate =` 预期只命中 helper 内部唯一赋值。✅

### PF-05: Agent finish_reason fallback fail closed

- **S1 decision #10** (line 113) 删除 `or FinishReason.STOP`，不保留过渡默认值。✅
- **S1 decision #10** `_consume_runner_event()` 在接受前验证 finish_reason；非法值不写 runner_done、不产出 ITERATION_COMPLETED。✅
- **S1 decision #10** `_classify_iteration()` 在 runner_done is None 走既有 fail-closed；non-None 时直接读 typed field。✅
- **S1 assertions** (line 178) `cast(FinishReason, None)` malformed 注入 → `RUNNER_ABNORMAL_STOP` diagnostic，不得进入 FINAL_ANSWER/tool-call。✅
- **S1 validation commands** (line 185, 189) 含 `test_runner_done_with_invalid_finish_reason_fails_closed` 与 `or FinishReason.STOP` deletion scan。✅

## Invariant Verification

| Invariant | 状态 | 证据 |
|---|---|---|
| 3 slices 不变 | ✅ | Plan line 10, 410; S1/S2/S3 边界未变 |
| 7 accepted / 1 narrowed / 2 rejected 不变 | ✅ | Plan line 72, 409 |
| 无 Host 下游补救 | ✅ | Plan line 39, 45, 53, 403 均禁止声明 |
| 无 compat shim / feature flag / loose parsing | ✅ | S1 #8 无兼容分支；S2 #9 不保留 flag |
| 无 provider capability profile | ✅ | Plan line 45 明确禁止 |
| 无通用 JSON Schema engine | ✅ | S3 #2 限定四个 bounds + enum |
| Runner identity / error marker 仍 rejected | ✅ | Plan line 69-70, 397 |
| README/design triggers 不变 | ✅ | Plan line 364-374 与初版一致 |

## Validation Commands Executability

针对用户指定的四条检查路径：

1. **post-done cancellation**: S1 validation commands (line 185) 的 5 个 post-done 测试 node ids 可直接执行；每个测试的驱动方法（anext + request_cancel）在 S1 decision #5 中明确。✅
2. **position-routed conflict**: S2 validation commands (line 249) 的 `test_position_routed_conflict_fails_closed_without_merge` 可直接执行；反例场景在 negative matrix (line 239) 中详细描述。✅
3. **first-candidate 唯一赋值**: S1 scan (line 190) `state.failure_candidate\s*=` 捕获所有赋值点；assertion (line 177) 的两个测试覆盖保留与并发。✅
4. **finish_reason typed fail-closed**: S1 scan (line 189) `or FinishReason\.STOP` 确认删除；S2 scan (line 254) `FinishReason\.TOOL_CALLS` 语义级 + 人工分类审计；aggregate 同一 scan (line 353)。✅

## Residual Risks（无新增）

原 plan 中的 4 项 residual risks 未变化：
- 非规范 provider dict arguments → fail-closed
- Synthetic index delta preview → accepted current design
- Context overflow marker → rejected finding
- Runner identity delimiter → rejected finding

PF-01..PF-05 修复未引入新的 residual risk。

## Findings

无。所有 5 项 PF 均已完整落实到 plan 的 frozen decisions、assertions、negative matrix 和 validation commands 中。未发现 material issue。

## Plan Re-Review Conclusion

**Pass** — 所有 PF-01..PF-05 修复均已落实，invariants 保持完整，validation commands 可执行。

- **status**: pass
- **artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-rereview-ds.md`
- **findings**: 0
- **blocking questions**: 0
