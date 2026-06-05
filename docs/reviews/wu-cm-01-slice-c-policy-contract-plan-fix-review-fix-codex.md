# WU-CM-01 Slice C Policy Contract Plan Fix Review-Fix - Codex

## Gate Status 与 Scope

- Gate: Slice C policy contract plan fix review-fix
- Work unit: WU-CM-01
- Branch: `phaseflow/wu-cm-01`
- Design source: `docs/host/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Input plan fix: `docs/host/wu-cm-01-conversation-memory-plan.md`
- Reviewed artifacts:
  - `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-mimo.md`
  - `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-ds.md`
- Status: completed
- Artifact path: `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-fix-codex.md`

本 gate 只修 plan 边界和 review artifact typo；未修改生产代码、测试、README 实体文件、design source 或 control source。

## 修复摘要

- 在 `docs/host/wu-cm-01-conversation-memory-plan.md` 的 Slice C allowed files / 实现边界中补充 `dayu/config/README.md` 同步约束：若 Slice C 修改 `dayu/config/execution_profiles.json.memory_projection_policy` 字段，必须同 slice 检查并按配置说明手册职责更新 `dayu/config/README.md`。
- 在 Slice D docs closure 中补充 `dayu/config/README.md` re-check 边界：Slice D 只复核是否残留旧 memory policy 字段、旧术语或配置入口不一致说明，不承接本应由 Slice C 同步完成的配置说明更新。
- 在 README / Doc Sync Triggers 中补充 `dayu/config/execution_profiles.json.memory_projection_policy` -> `dayu/config/README.md` 的触发规则，避免 implementation agent 把 AGENTS.md 触发项遗漏或只推迟到 Slice D。
- 在 `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-codex.md` 中将“一性原理判断”修正为“第一性原理判断”。

## Accepted Findings 关闭情况

- DS F7 `dayu/config/README.md` 触发未显式列入：已修复。plan 现在明确 Slice C 修改 packaged config 的 `memory_projection_policy` 字段时必须同 slice 检查 / 更新 `dayu/config/README.md`，并允许 Slice D 后续 re-check 残留旧术语。
- DS F8 Codex artifact 措辞小瑕：已修复。原 artifact typo 已更正为“第一性原理判断”。

Mimo review 无 blocking finding；DS review verdict 为 PASS，F7/F8 均为 observation / low-severity plan quality fix，本 gate 未扩大到 re-review。

## Validation

- 未运行 pytest：本 gate 只修改 docs plan / review artifact，不修改生产代码或测试；pytest 不能验证本次 plan 边界修复，且会引入与当前 gate 无关的旧 memory contract 噪音。
- 未运行 pyright：本 gate 不改 Python 代码；pyright 不能验证文档触发规则修复。
- 运行轻量文档校验：`git diff --check` 通过。

## Residual Risks

- 后续 Slice C implementation 仍需实际修改 `dayu/config/execution_profiles.json.memory_projection_policy` 时同步检查 / 更新 `dayu/config/README.md`；分类为 covered by later approved slice，owner 是 Slice C implementation gate。
- Slice D 仍需 re-check `dayu/config/README.md` 是否残留旧 memory policy 术语；分类为 covered by later approved slice，owner 是 Slice D docs closure。
- 本 gate 不执行 pytest / pyright，后续 implementation gate 必须按 plan 的受影响测试与 full pyright 验证。

## Git Status 摘要

`git status --short` 摘要：

- `M docs/host/wu-cm-01-conversation-memory-plan.md`
- `?? docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-codex.md`
- `?? docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-ds.md`
- `?? docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-fix-codex.md`
- `?? docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-mimo.md`

本 gate 实际修改 / 新增的文件仅限：

- `docs/host/wu-cm-01-conversation-memory-plan.md`
- `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-codex.md`
- `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-fix-codex.md`

`docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-ds.md` 与 `docs/reviews/wu-cm-01-slice-c-policy-contract-plan-fix-review-mimo.md` 是输入 review artifact，本 gate 只读未改。

## Completion Status

Completed. Stop condition reached: 仅完成窄修复，不 commit / push / PR / merge，不进入 re-review。
