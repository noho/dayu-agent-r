# `WU-CLI-DOWNLOAD-03-DL-F15` Plan Review Fix

## 1. Artifact 状态

- Work unit：`WU-CLI-DOWNLOAD-03-DL-F15`
- Gate：`fix`（plan review 后）
- 日期：2026-08-10
- Reviewed plan：`docs/gateflow/wu-cli-download-03-dl-f15-plan-20260810.md`
- Adjudication：`docs/gateflow/wu-cli-download-03-dl-f15-plan-review-adjudication-20260810.md`
- Changed files：
  - `docs/gateflow/wu-cli-download-03-dl-f15-plan-20260810.md`
  - `docs/gateflow/wu-cli-download-03-dl-f15-plan-review-fix-20260810.md`
- Artifact path：`docs/gateflow/wu-cli-download-03-dl-f15-plan-review-fix-20260810.md`
- Completion status：`fix complete`；下一未完成 gate 为 MiMo/DS `re-review`。
- 本 fix 未实施产品代码或测试，未运行 implementation validation/真实 CLI，未 stage/commit。

## 2. Scope 与裁决落实

本 fix 只落实总控裁决 PR-F1～PR-F4，不改变已确认 goal、semantic owner、单一 Slice S1、allowed implementation files、公开契约或 fake converter 测试边界。

| Finding | 裁决 | 修复映射 | 最终状态 |
|---|---|---|---|
| PR-F1 代码行号引用偏差 | accepted | plan §4.2 将 `run_docling_pdf_conversion` 直接证据从 `538-602` 更正为 `510-602` | 已修复 |
| PR-F2 coverage cases 过度强制、80% 可达性未先测 | accepted-in-part | plan §8.5 改为“核心 tests 后先测 baseline -> 按 missing lines 从有界 inventory 一次选择最小 case -> 每轮重测 -> 达到 80% 立即停止”；§9.2 固定 baseline/增量/最终门禁命令；§10/§11 明确 allowed boundary 内不可达即 stop/回总控，禁止扩产品、降阈值或 bypass | 已修复 |
| PR-F3 真实 download 可能引入非目标差异 | accepted-in-part | plan §9.4 保留 production `dayu-cli download`，但 verdict 只绑定 0700 Q3 或替代 0066 Q2；非目标 failure/分类差异只登记，不扩修、不改变 target verdict；阻断目标闭链则标 external evidence gap并停止 | 已修复 |
| PR-F4 deterministic test 使用 fake converter | rejected-with-reason | plan §8.4 完全保留 factory-only fake converter 边界：真实 planner/runner/callback 仍在路径中，真实 converter 组合由 production CLI evidence 覆盖；未引入重型 deterministic conversion | 已修复 |

Open questions 裁决也已落实：正式真实 run 明确限定在 accepted implementation commit 的 detached HEAD clean environment；coverage 只补达到 80% 所需的最小候选；非目标 observation 不参与 DL-F15 target verdict。

## 3. Validation

- 文档级核对：plan 仍只有 Slice S1；allowed implementation files 不变；fake converter 描述与两项核心 owner tests 不变。
- Scope 核对：本 fix 只修改 reviewed plan 并新增本 artifact；没有产品、测试、README 修改。
- 冻结输入：`docs/cli_ci.md`、WU-01 adjudication 与 goal artifact 保持只读。
- 尚未执行：implementation tests、coverage、pyright、Ruff、compileall、真实 CLI；这些属于后续 accepted plan 的 implementation/validation。

## 4. Docs decision

plan 的 README 决策不变：后续 implementation 仅按既定边界最小更新 `tests/README.md`；本 fix 不修改 README。

## 5. Residual risks / uncovered areas

- 真实首 attempt 直接成功：`requiring explicit user decision` evidence gap。
- provider 不返回两个目标样本，或非目标错误阻断目标闭链：`requiring explicit user decision` external evidence gap。
- 核心 tests 加有界 coverage 候选仍无法达到 80%：stop/回总控；不得扩大产品或测试边界、放宽阈值或绕过 coverage。
- 其它分类/provider/storage/runner observation：不属于本 WU，只登记直接证据并停止扩面。

Blocking open questions：无。

## 6. Decision / next entry point

总控 required fixes 已全部映射为“已修复”。当前 gate decision 为 `fix complete`；next entry point 是 MiMo/DS 双路 `re-review`，不是 implementation 或 accepted plan commit。
