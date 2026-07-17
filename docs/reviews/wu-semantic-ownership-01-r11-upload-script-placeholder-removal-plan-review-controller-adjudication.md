# WU-SEMANTIC-OWNERSHIP-01 / R11 initial plan review Controller adjudication

## 1. Review target 与 verdict

- immutable plan：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，
  711 lines / SHA-256 `c2c5700561cf8ad48f774aba79d792e775d7419de821efda4162f3d7411038d5`。
- AgentMiMo review：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-mimo.md`，
  289 lines / SHA-256 `b7eb5e1e3652dc148e0299e19b3a06cd37761d2c35db3d7350b0931bd079bf37`。
- AgentDS review：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-ds.md`，
  308 lines / SHA-256 `2e1c1847f8faa60a0771b2049054e360a742afb371543ec2bd017fda92019abd`。
- Controller verdict：`PLAN FIX REQUIRED / 6 ACCEPTED FINDINGS / 0 BLOCKER`。

Reviewer verdict 不授权 implementation。下一 gate 只允许 AgentCodex 修复以下 accepted plan findings；
计划保持未接受，R11 implementation、commit、R12、push/PR 均未授权。

## 2. Accepted findings

### R11-PR-F01 — S2 发现 S1 owner contract gap 的回返路径

- 来源：DS-F02。
- 裁决：接受，但不新增 adapter、compatibility seam 或额外 slice。
- 直接理由：S1 typed plan 是 S2 current-grammar builder 的 producer contract；尽管 plan 已逐字段描述，
  首个真实 consumer 仍可能暴露 owner contract 缺口。当前 §9.1 只写 checkpoint failure 禁止下一 slice，
  没有明确 S2 已开始后如何回到 S1 owner。
- 必修：在 S1 checkpoint 增加 S2 consumer mapping checklist；若 S2 发现 typed fact 不足或枚举/optional
  ownership不匹配，立即 stop，由 Controller 只授权 S1 owner targeted fix，随后重跑 S1+S2 cumulative
  validation。严禁在 S2 adapter/renderer/fixture 补事实，且不创建新 sub-WU/slice/commit。

### R11-PR-F02 — symlink 拒绝范围必须停在 workspace boundary

- 来源：DS-F04。
- 裁决：接受。
- 直接理由：`workspace/output 任一级 symlink` 可被误读为拒绝 workspace root 外部祖先；macOS
  `/tmp -> /private/tmp` 是直接反例。安全 owner 需要拒绝 workspace root 自身是 symlink，以及从 root
  到 output target 的内部组件/candidate symlink；不应治理 root 外部 OS ancestor。
- 必修：精确写出 lexical/resolved containment、root-self 与 root-inside component 检查，并新增
  external-ancestor-symlink allowed / root-self-symlink rejected / internal-symlink rejected tests。Fins source
  boundary 同样不得扫描 caller root 外部祖先。

### R11-PR-F03 — `--overwrite` / `--infer` grammar 与 publisher 语义消歧

- 来源：DS-F05、MiMo-06、MiMo-07。
- 裁决：接受 narrow clarification。
- 必修：明确 `--overwrite` 是 `store_true`、default false，只传播为每条 direct upload 的 storage
  overwrite fact；它不控制脚本 target replacement，也不引入 `--force-output`。Publisher 的 existing-target
  atomic replacement policy 由 output contract 独立拥有。明确 `--infer` 是 `store_true`、default false，
  未传时零 env/resolver access，传入时只调用一次 existing resolver public method。Help text/test matrix
  必须锁定这两个 contract。

### R11-PR-F04 — wheel archive 与 RECORD exact negative oracle

- 来源：MiMo-09、DS-F06。
- 裁决：接受合并 finding。
- 直接理由：plan prose 要求 archive 零 `dayu/web|wechat|render`，但列出的 executable commands 只直接
  检查 METADATA、entry_points 与 importability；package-data 残留缺少 exact path oracle。
- 必修：在 extracted wheel/zip name 上加入确定性的 package-directory zero assertion，并对
  `.dist-info/RECORD` 加同一 placeholder-path zero assertion；命令必须明确 expected exit/output，不依赖
  shell wildcard 偶然行为。无需单独治理 untracked `__pycache__` 或合法 `top_level.txt=dayu`。

### R11-PR-F05 — POSIX real smoke fixture 必须锁定现有路径

- 来源：MiMo-11 / Q2。
- 裁决：接受。
- 直接证据：tracked fixture 为
  `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`。
- 必修：plan 必须写出该 exact read-only fixture path、复制到 `workspace/tmp` 后的 OLD-recognizable filing/
  material names，以及不得修改 tracked fixture / 不从网络下载 fixture 的规则。

### R11-PR-F06 — zero-filing call cap 与 Ruff baseline version oracle

- 来源：DS-Q02、DS-Q03。
- 裁决：接受两个同属 validation-closure 的窄补充。
- 必修：明确 filtered recognized filing count 为零时 `EARNINGS_CALL` cap 也为零，所有 call candidates
  进入 typed skipped，并增加 owner test；不得擅自 minimum-one。Controller 锁 Ruff baseline 时同时记录
  `python -m ruff --version`，implementation/aggregate 必须版本一致，否则 stop 并重新锁 baseline，不能
  把版本规则漂移算 current finding。

## 3. Rejected / no-action candidates

### Windows algorithm / `list2cmdline`

- MiMo-02/Q1 与 DS-F01 要求 plan 预先给出候选算法家族、iteration count，MiMo 还建议允许
  `subprocess.list2cmdline` baseline。
- 拒绝。Controller discussion 与 accepted umbrella plan 已裁决 Windows outcome/invariants 必须由真实
  `cmd.exe` 反证后定型，默认算法不能在无 runner evidence 时猜；用户又明确禁止 `list2cmdline` 作为
  batch owner、fallback 或 shim。Plan 已把 real recorder/CLI smoke、single owner、no-fallback 与失败即
  release blocker 写清。任意 N 次迭代阈值没有真源，反而是新的 magic policy。

### OLD behavior 与 compatibility

- MiMo-01 要求保留旧 `create` default 或增加 compatibility notice：拒绝。用户明确裁决三个 upload
  grammar default 为 `auto` 且禁止 compatibility branch；README 已必须说明 current user behavior。
- MiMo-05 要求删除 structured auto-recursion：拒绝。它是已接受 OLD-aligned workflow 规则，不是 reviewer
  可重开产品裁决的对象；S1 tests/skip/containment 限制其影响。

### 已充分闭合或非 finding

- MiMo-03 precise workflow paths 是 closed allowlist 的有意约束；实现时 exact coverage 已是 mandatory。
- MiMo-04 自己证明 auto omission 与 parser default 自洽。
- MiMo-08 POSIX `shlex` 由真实 `/bin/sh` recorder 闭合。
- MiMo-10 无需在 plan 枚举所有既有 test function 名；current file/read diff 与 package artifact 是 owner proof。
- MiMo-12 coverage `>=80%` 是 AGENTS hard gate，不能降级。
- MiMo-13 untracked `__pycache__` 不是 product/package contract；wheel archive oracle 已闭合 tracked build。
- MiMo-14 plan 已明确 unexpected rename 立即 stop。
- MiMo-15 positive `DisableDelayedExpansion` scan 与 behavior tests组合成立。
- DS-F03 已被 plan 明确定义为一次 public resolver method call、不承诺内部 HTTP hops；不改 resolver owner。
- DS-Q01 已由 plan 的“实际 OS 决定”锁定为 local-platform generation；不新增 `--platform` 或 cross-build
  product contract。
- DS-R01—R07 全部维持 reviewer no-action。

## 4. Fix gate 与 re-review要求

AgentCodex 只可修改：

- `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`
- 新增一个 R11 plan-fix evidence artifact。

不得修改 control、review artifacts、代码、测试、README、design、CI，不得 stage/commit。Fix 后 Controller
必须重锁 plan hash、逐项验证 R11-PR-F01—F06 全部关闭且 rejected candidates 未实现，再对完整 fixed plan
并发执行 AgentMiMo / AgentDS re-review。

## 5. Gate state

- accepted plan findings：6。
- accepted open：6。
- rejected/no-action：MiMo 12 类 / DS 9 类合并裁决如上。
- blocker：0。
- next gate：AgentCodex plan-only fix。
- implementation、accepted-plan commit、R12、push/PR：未授权。
