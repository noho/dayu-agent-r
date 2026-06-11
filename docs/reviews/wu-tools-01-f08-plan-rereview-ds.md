# WU-TOOLS-01-F08 Plan Fix Focused Re-Review (DS)

## 元信息

- Work unit：`WU-TOOLS-01-F08`
- Gate：plan re-review（focused，只核对 controller accepted findings 覆盖）
- 日期：2026-06-11
- Reviewer：AgentDS
- Reviewed artifacts：
  - `docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md`（plan，已修复）
  - `docs/reviews/wu-tools-01-f08-plan-review-controller-adjudication.md`（controller 裁决）
  - `docs/reviews/wu-tools-01-f08-plan-fix-codex.md`（plan fix 记录）

## Review Scope

本 re-review 只核对 controller accepted findings 是否已被 plan fix 覆盖。不做 implementation review，不修改代码，不 stage，不 commit，不 push。

## Verdict

**Pass**

All five accepted/deferred controller findings have been properly addressed in the plan. No blocking issues remain.

## Findings

None.

## Residual Risks

| ID | Risk | Severity | Owner |
|---|---|---|---|
| RR-01 | Fins test location exception（plan 行 139-141, 218）虽被 narrow evidence gate 约束，但 implementation agent 可能误读为"已有 focused 测试文件即可"。Controller adjudication 和 plan 的多处明确表述已提供充分防护，implementation re-review 应验证。 | Low | Implementation re-reviewer |
| RR-02 | Documents test（plan 行 145-148）仍断言完整 `list_processors()` 顺序。Controller 未要求修改此点，且 Documents 默认 registry 仅 3 个同 priority 条目，顺序断言在此场景是可接受的。但若未来新增 processor，需注意此断言可能成为维护负担。 | Low | Future WU owner |
| RR-03 | DS F3（full `tests/fins` 失败分类）在 controller 裁决中标记为 deferred-with-owner，plan 已写入 closeout 要求。实际执行质量依赖 implementation closeout agent 的判断，无法在 plan gate 完全验证。 | Low | Implementation closeout reviewer |

## Evidence

### Point 1 — Fins focused registry behavior test mandatory

- **Plan 行 136-141**：`tests/fins/test_processor_registry.py` 列为必选文件；例外条件为 "只有 implementation 前有直接代码证据证明已有 focused Fins registry 测试文件比新建该文件更适合承载该 contract test 时，才允许换位置"。Plan 明确 "不允许因为已有 pipeline tests 覆盖 Fins preprocess / SEC pipeline 而跳过"。
- **Plan 行 218**：Implementation slice 重申同一例外条件。
- **Controller 裁决 F08-PR-MIMO-01**：要求 plan "must require a focused Fins registry behavior test, not allow implementation to skip it"。
- **结论**：已满足。Fins focused registry behavior test 现在是 mandatory，例外仅限文件位置且需代码证据。

### Point 2 — Fins registry test strategy → name/class/priority mapping

- **Plan 行 154-156**："优先用 public `list_processors()` 构造 `name -> (class, priority)` 映射，并断言当前 Fins registry 仍包含既有 priority 层级"。
- **Plan 行 163**："不要硬编码完整 `list_processors()` 顺序，除非某段顺序本身就是被测行为"。
- **Plan 行 164**："不要优先读取 private `_items`；public `list_processors()` 已足够支持这些断言"。
- **Plan 行 316**："Fins registry 测试优先断言 `name -> (class, priority)` 映射和 priority bucket；只有顺序本身是目标行为时才断言完整顺序"。
- **Controller 裁决 F08-PR-MIMO-02**：要求 "prefer a `name -> (class, priority)` mapping / priority-bucket assertion"。
- **结论**：已满足。策略明确改为 name → class/priority mapping 与 priority bucket，避免完整列表顺序硬编码。

### Point 3 — docs/host old-name cleanup boundary

- **Plan 行 24**："本 WU 在 `docs/host/` 下的 old-name cleanup control target 只有 `docs/host/issues-implementation-control.md`"。
- **Plan 行 195**："`docs/host/` 下旧 plan artifact 属于过程历史时可以保留旧名；本 WU 的稳定 control cleanup 只针对 `docs/host/issues-implementation-control.md`"。
- **Controller 裁决 F08-PR-DS-01**：要求澄清 control target 边界。
- **结论**：已满足。边界明确，历史 plan artifact 可保留旧引用。

### Point 4 — focused registry tests 与 pipeline tests 关系

- **Plan 行 133**："这里的 focused registry tests 是 contract tests，直接锁定 documents 默认 registry 与 Fins registry overlay contract；既有 pipeline tests 是 integration coverage，证明 registry 被下游路径实际消费。两者互补，不能互相替代：pipeline tests 不能替代 focused registry contract tests，focused registry tests 也不替代相关包集成测试。"
- **Controller 裁决 F08-PR-DS-02**：要求澄清二者互补关系。
- **结论**：已满足。关系明确为 contract tests + integration coverage 互补。

### Point 5 — full tests/fins 失败时 closeout 分类要求

- **Plan 行 283**："若 full `tests/fins` 失败，implementation closeout 必须区分失败属于本次 rename regression，还是预存 heavy fixture / environment issue；focused registry tests 是本 WU 行为不变的主要证明。"
- **Plan 行 327-328**："full `tests/fins` 如因 heavy fixture / 环境问题失败，需在 closeout 中分类说明；这不自动推翻 focused registry contract tests 的行为证明，但若失败与 rename 相关则必须修复。"
- **Controller 裁决 F08-PR-DS-03**：deferred-with-owner，要求 implementation closeout 区分 rename regression 与预存 noise。
- **结论**：已满足。Closeout 分类要求已写入 plan 的验证命令和 residual risk 章节。

## Conclusion

Plan is ready for implementation gate. All five controller-required fix points have been addressed with concrete, testable plan text. No blocking findings remain.
