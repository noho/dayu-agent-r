# WU-SEMANTIC-OWNERSHIP-01 / R11 plan-boundary fix Controller validation

## 1. Verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- finding：`R11-IMP-BF01 — producer/consumer checkpoint 不能形成合法中间 tree`。
- amended plan：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，
  848 lines / 70,036 bytes，SHA-256
  `9d46ecfc74ced43b6f4868405fbee426523cee754456f0f2131aa3c4dd917be0`。
- AgentCodex fix evidence：
  `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-boundary-fix-codex.md`，
  190 lines / 12,301 bytes，SHA-256
  `4d91a4be8b37cc78246cccf81df38ae15bc23317534ba91b48eb0c76bc323e21`。
- Controller verdict：`PASS / READY_FOR_DUAL_COMPLETE_AMENDED_PLAN_REVIEW`。

本 verdict 表示 plan-only fix 已完整落入计划文本，可以进入双路 complete re-review；不提前关闭 finding，不接受 amended
plan，不授权 implementation、stage/commit、R12、push 或 PR。

## 2. 完整读取与 root cause

Controller 已完整读取 848 行 amended plan、190 行 fix evidence，并重读 CURRENT Fins producer 与 CLI consumer。
CURRENT CLI 静态 import generic `UploadBatchPlanEntry`，读取 `plan.entries`、`entry.command_name`、`entry.files`；因此原
producer-only S1 无法在 no-compat、full pyright=0 下形成合法 checkpoint。`R11-IMP-BF01` 直接成立，修复 owner 是 plan
state machine，不是 Fins/CLI 产品 owner 或下游 adapter。

## 3. Controller amendment requirements closure

1. **两 slices**：§2.4、§4、§9.1 和 checklist 都固定
   `R11-I1 atomic Fins+CLI cutover -> R11-I2 packaging/README/Windows gate`。
2. **ordered work packages**：§5 WP-A 与 §6 WP-B 共享一个 merged slice allowlist；二者之间无 checkpoint、
   acceptance、commit、full validation、handoff 或 next-slice transition。
3. **atomic validation**：WP-A+WP-B 一起 cutover 后才运行 owner/CLI focused tests、filesystem/POSIX real smokes、
   changed-file coverage、full pyright、scoped/full-baseline Ruff、diff/scans；I1 checkpoint 只在全部通过后发生。
4. **owner correction**：consumer 暴露 typed gap 时，状态保持在 I1，只允许 Fins owner 两路径 targeted correction，
   CLI 继续机械消费；随后重跑全部 producer+consumer cumulative gates。
5. **全篇传播**：§1、§2.4、§4—§10 已改写；原 packaging 内容仍独立在 I2，未扩产品或 path scope。
6. **review/commit**：两个 slices 后才有一次 cumulative dual code review/fix/re-review 与一个 accepted implementation
   commit；work-package/slice 中间 commit仍禁止。
7. **保留 gates**：Windows `PENDING_RELEASE_BLOCKER`、coverage `>=80.00`、full pyright 0、Ruff
   `0.15.11` / 144-finding baseline、security/deferred/no-touch/no-push 均保留。

上述七项全部 plan-text closed；双路 review 仍须独立验证其可实施性与无矛盾性。

## 4. Legacy state 与 rejected alternatives scan

Legacy scan 对 `R11-S1/R11-S2/R11-S3`、三-slice、旧 S1/S2/S3 checkpoint/transition 精确零命中；唯一 bare
`S1` 是 line 12 的历史 Controller authorization/stop/adjudication artifact 专名，不是 current state-machine node。

Plan 没有引入或允许：

- generic legacy type/property/alias/wrapper 或 old/new dual surface；
- CLI loose parsing、`hasattr/getattr`、fallback、重算或 downstream repair；
- transient broken tree 作为 validation/checkpoint/handoff truth；
- 放宽 full pyright、coverage、Ruff baseline 或安全扫描；
- Service/storage/runtime/FMP/ticker/design/constraints 修改、新 sub-WU、第三 slice 或 packaging 扩 scope。

## 5. Owner、allowlist 与 validation preservation

- Fins 仍唯一拥有 discovery/fiscal/material/priority/dedup/caps/skips；CLI 仍只拥有 input、一次 public FMP
  resolve、typed projection、renderer/publisher/summary。
- I1 精确 union 原 Fins 两路径与原 CLI 六路径；I2 精确保留原 packaging/CI/deletion/test/README paths；cumulative
  allowlist 无新增或删除。
- POSIX recorder、真实 CLI→Service→Fins→temp storage、wheel 五层 oracle、真实 Windows `cmd.exe` release gate均保留。
- Issue 142、151、175、177、178、R12、真实 Web/WeChat/render、Topic 8/9、统一 auth仍为 no-touch。
- containment、symlink、atomic replacement、argv injection 与 secret non-persistence仍是局部安全 contract，不被描述为
  统一 authorization。

## 6. Dual review focus

双路 complete re-review 不是 delta review，必须重点挑战：

1. I1 merged context 是否确实是最小合法 atomic cutover，能否在一次 coordinated patch set 后形成 full-pyright-clean tree；
2. “WP-A/WP-B 之间无 stop”是否只禁止持久中间 state，而不掩盖 material preflight/allowlist blocker；
3. I1/I2 test 与 README/package consumers 是否仍按依赖切分，不会产生第二个 broken checkpoint；
4. owner correction loop是否只改 Fins owner且必然重跑 combined validation；
5. full validation、Ruff baseline、Windows release blocker、security/deferred gates是否没有被合并语义弱化；
6. 全文是否仍有旧三-slice、提前 review/commit/acceptance 或 packaging scope漂移。

## 7. Workspace/gate state

- product/test/README/design/CI diff：empty。
- Agent write scope：amended plan + fix evidence only；Controller-owned dirty/untracked artifacts未被覆盖。
- staged tree：empty。
- `git diff --check`：pass。
- accepted/open：`R11-IMP-BF01` 仍为 1，等待 dual complete re-review；blocker 仍为 plan gate blocker；residual 0。
- next gate：AgentMiMo / AgentDS 并发完整 amended-plan re-review。

READY_FOR_DUAL_COMPLETE_AMENDED_PLAN_REVIEW
