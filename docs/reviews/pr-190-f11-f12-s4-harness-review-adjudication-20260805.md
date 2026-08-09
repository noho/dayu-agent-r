# PR 190 F11/F12 S4 Harness Review 裁决

## Scope

- Branch: `codex/interactive-oracle`
- Actual base: `321893e423beeb20acf2768c03b2be3477c92903`
- Inputs:
  - `docs/reviews/code-review-20260805-210138.md`
  - `docs/reviews/pr-190-f11-f12-s4-harness-mimo-review-20260805.md`
  - `docs/reviews/pr-190-f11-f12-s4-harness-ds-review-20260805.md`
  - `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-HeHeLm/`
- 本裁决只处理 S4 harness/evidence gate；生产 blocker `S4-001` 进入独立 owner slice。

## Finding 裁决

| Finding | 裁决 | 依据与动作 |
|---|---|---|
| `S4-001` | 接受，独立生产 slice 修复 | selection 使用 raw current-input text，而 replay 使用 `run_input_material_block` 的 normalized text；两条路径生成不同 digest，真实 exhausted fallback 在 durable commit 前失败。必须在 fallback current-input material construction/digest owner 收口，harness 不补偿。 |
| `S4-REVIEW-001` | 接受 | evidence export、fresh-write、digest、public/canonical mismatch 均是本次新增 harness contract；补 owner-level deterministic tests。 |
| `S4-REVIEW-002` | 不成立 | `_sanitize_error_text` 先执行 `text.lower()`；大小写变体已经覆盖，不修改。 |
| `S4-REVIEW-003` | 接受为已知低风险，不改实现 | 完整 LLM request messages 是本次私有 immutable evidence 的必要输入证据；bundle 不进入仓库，secret scan 必须继续为 0。若将来公开分发，另由 evidence 发布 owner 决定脱敏 contract。 |
| `DS-001` | 暂不接受为代码 finding，转为重跑验证项 | 现有 screen 能证明 Host 执行两次 compaction attempt，但不足以证明当时运行的 capture wrapper 版本、生命周期或 append 状态；三个推测均无直接证据。产品修复后从全新 root 重跑，要求 `compactor-attempts.json` 与 canonical attempt 数量一致；若仍复现，再按直接证据定位。禁止加入临时 debug 噪声冒充修复。 |
| `DS-002` | 接受 | real-provider suite 的用途就是产生不可覆盖 evidence；缺少 `--evidence-output-dir` 时静默运行会丢失唯一正式产物。parser 应 fail closed，并给出可操作错误。 |
| `DS-003` | 接受，与 `DS-002` 同修 | 将 pressure-mode 与 evidence-dir 两个 CLI 约束拆成独立断言，避免测试由错误分支偶然通过。 |
| `DS-004` | 不采纳 | smoke cold-start 的低毫秒级开销不构成 correctness/stability finding；当前二分搜索复用 Host estimator owner，改成依赖 estimator 当前算术实现反而增加语义耦合。 |
| Review/report base SHA | 接受为 gate artifact 准确性 finding | 三份 review artifact与 Codex review 误写 base SHA，应由各自 owner 修为实际 `321893e423beeb20acf2768c03b2be3477c92903`。external bundle 已声明 immutable，不得回写；该 bundle 保留原样并因 metadata typo 与产品 blocker 归档为 superseded partial evidence，新 root 必须写入正确 base。 |

## Harness fix gate acceptance

Harness fix/re-review 必须证明：

1. real-provider suites 缺少 `--evidence-output-dir` 时 fail closed；pressure-mode 与 evidence-dir 分别测试。
2. fresh path、digest self-exclusion/content digest、public/canonical equal 与 mismatch、failure export 关键边界有 deterministic tests。
3. 仓库内 gate/review artifact 的 base SHA 精确；旧 external bundle 不修改，新 evidence root 的报告写入正确 base，secret scan finding 为 0 且生成独立 digest。
4. `S4-001` 仍明确归 production owner slice，不得在 harness/renderer/fixture 补偿。
5. 新 evidence root 重跑时再验证 capture 数量；旧 bundle 保持 immutable，不回写 metadata、观察事实、secret scan 或 digest。

## Gate 状态

`ACCEPTED`。

- AgentMiMo re-review：`docs/reviews/pr-190-f11-f12-s4-harness-mimo-rereview-20260805.md`，PASS，无 finding。
- AgentDS re-review：`docs/reviews/pr-190-f11-f12-s4-harness-ds-rereview-20260805.md`，PASS，无 finding。
- 定向测试：36 passed，3 个既有依赖 warning。
- 全仓 pyright：0 errors。
- 下一入口：提交 S4 harness accepted checkpoint，然后进入 `S4-001` production owner slice。
