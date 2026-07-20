# WU-SEMANTIC-OWNERSHIP-01 / R11 accepted plan findings fix evidence — AgentCodex

## 1. Gate、target 与 source locks

- gate：同一 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R11 plan-only accepted-finding fix；不是新 WU，不进入
  implementation。
- fix truth：
  `docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-controller-adjudication.md`
  是唯一裁决真源；其 verdict 为 `PLAN FIX REQUIRED / 6 ACCEPTED FINDINGS / 0 BLOCKER`。
- immutable before plan：
  `docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，711 lines，SHA-256
  `c2c5700561cf8ad48f774aba79d792e775d7419de821efda4162f3d7411038d5`。
- fixed plan：同一路径，773 lines，SHA-256
  `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`。
- MiMo review lock：289 lines，SHA-256
  `b7eb5e1e3652dc148e0299e19b3a06cd37761d2c35db3d7350b0931bd079bf37`。
- DS review lock：308 lines，SHA-256
  `2e1c1847f8faa60a0771b2049054e360a742afb371543ec2bd017fda92019abd`。
- evidence timestamp：`2026-07-17T21:52:56+0800`，来自本机 `date`。
- 本 gate 唯一写范围：修改 fixed plan，并新增本 evidence。未修改 control、既有 review artifacts、代码、测试、
  README、design 或 CI；未 stage、commit、push 或创建 PR。

## 2. 动机与 adversarial lenses 复核

六项 accepted findings 均成立，严重性没有被高估：它们分别暴露 producer/consumer contract 的回返缺口、路径安全边界
越界、两个 CLI flag 的语义歧义、wheel artifact negative oracle 缺口、real smoke 输入真源未锁，以及 empty-state / tool
version oracle 未闭合。修复均位于 plan 中对应语义 owner 或验证 owner 的边界，没有下游止血。

- Architecture boundary：S1 继续拥有 typed facts，S2 只消费明确映射；路径 owner 只治理 root self 与 root 内组件；
  resolver HTTP owner、Service/storage owner 均不变。
- Best-practice：lexical/resolved containment 同时保留，同时允许 root 外合法 OS ancestor；wheel 以 extracted path 与
  RECORD 两个确定性 artifact oracle 验收。
- Optimal solution：用现有 `--overwrite` / publisher 两个独立 contract 闭合歧义，不增加 `--force-output`；用现有
  fixture 复制完成 smoke，不创建新 fixture 或网络依赖。
- Overengineering：未预猜 Windows algorithm、iteration magic 或跨平台生成 contract；未治理 untracked
  `__pycache__` / 合法 `top_level.txt=dayu`。
- Overcoupling：S2→S1 回返仍由 Controller 精确授权，既不增加 slice/commit，也不让 S2 adapter 与 S1 owner 耦合。

## 3. Accepted finding closure

### R11-PR-F01-已关闭-S2 发现 S1 owner contract gap 的回返路径

- **Before section**：immutable plan §5.3 只要求 S1 checkpoint 通过后进入 S2；§9.1 只规定 checkpoint failure
  禁止下一 slice。没有 S2 consumer field/enum/optional-to-current-flag checklist，也没有 S2 已开始后返回 S1 owner
  的状态迁移。
- **After section**：fixed plan §5.3 增加逐字段 checklist；§9.1 增加唯一 owner 回返路径。
- **Direct evidence**：Controller adjudication lines 18—27 明确要求 checklist、S2 immediate stop、Controller-only S1
  targeted fix、S1+S2 cumulative validation，并禁止 S2 补事实和新 slice/commit。
- **修复内容**：
  - entry type→command、ticker/aliases→`--ticker` CSV、action enum→省略或 `--action`、file→`--files`；
  - fiscal、amended、dates、company、overwrite 与 material-only fields 的 optional-to-flag 规则；
  - skipped path/reason 只进入 human summary；
  - S2 发现 typed fact/enum/optional ownership gap 时立即 stop，由 Controller 只授权 S1 production/test owner
    targeted fix，重跑 S1 checkpoint 与 S1+S2 全部 cumulative validation。
- **Rejected non-implementation**：未增加 adapter、fallback、compatibility seam、sub-WU、第四 slice或中间 commit；
  未让 S2 renderer/fixture 重算 S1 事实。
- **New plan line / SHA**：lines 291—309、705—711；SHA-256
  `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`。

### R11-PR-F02-已关闭-symlink 拒绝范围停在 workspace/source boundary

- **Before section**：immutable plan §5.2.1 对 source root 的 lexical/resolved 关系不够精确；§6.3 写
  `workspace/output 任一级 symlink 均拒绝`，可能把 `/tmp -> /private/tmp` 等 root 外祖先误纳入拒绝范围。
- **After section**：fixed plan §5.2.1、§5.3、§6.3、§6.6 与 §8.3 明确 source/output 的 lexical 与 resolved
  containment、root-self 检查、root 内组件/candidate/target 检查及 external ancestor 允许规则。
- **Direct evidence**：Controller adjudication lines 29—38 给出 `/tmp` 反例并把安全 owner 限定为 root self 与 root
  内组件；Fins source boundary 同样不得向外扫描 caller root 祖先。
- **修复内容**：
  - source candidate 同时满足 lexical-root 与 resolved-root containment；root self 与 root→candidate 内部 symlink
    拒绝，root 外祖先不检查；
  - output target 同时满足 lexical workspace 与 resolved workspace containment；root self、root 内 output component
    与已有 target symlink 拒绝；
  - 测试矩阵锁定 external-ancestor allowed、root-self rejected、internal component/candidate/target rejected 和 escape
    rejected。
- **Rejected non-implementation**：未扩为统一 authorization、workspace trust 或 shell sandbox；未拒绝 root 外 OS
  ancestor，也未修改 storage/source resolver。
- **New plan line / SHA**：lines 229—238、275—280、383—389、441—446、682—685；SHA-256
  `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`。

### R11-PR-F03-已关闭-`--overwrite` / `--infer` grammar 与 publisher 消歧

- **Before section**：immutable plan §6.2.4/6 要求 infer once 与新增 overwrite，但未锁两个 flag 的 argparse
  action/default/help；§6.3 未显式声明 publisher replacement 与 storage overwrite 相互独立。
- **After section**：fixed plan §6.2.4/6 锁定 grammar、help 与 owner；§6.3 锁定 existing target 原子替换；§6.6
  锁定 help/parser/propagation/replacement tests。
- **Direct evidence**：Controller adjudication lines 40—48 要求两个 flag 都是 `store_true/default false`，overwrite
  只传播 direct upload storage fact，publisher replacement 独立且不增加 `--force-output`；infer 未传零访问，传入只
  调一次 existing resolver public method。
- **修复内容**：
  - `--infer`：`action="store_true"`、`default=False`，help 自解释 FMP 补全与 `FMP_API_KEY`；
  - `--overwrite`：`action="store_true"`、`default=False`，help 明确 storage overwrite 且不控制脚本替换；
  - publisher 对 valid contained non-symlink existing regular target 始终按自身 contract 原子替换；测试证明
    overwrite true/false 不改变此策略。
- **Rejected non-implementation**：未增加 `--force-output`；未把 overwrite 设成双重语义；未修改 resolver HTTP
  owner；未恢复旧 `create` default 或兼容分支。
- **New plan line / SHA**：lines 355—369、383—389、441—446；SHA-256
  `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`。

### R11-PR-F04-已关闭-wheel extracted names 与 RECORD exact-zero oracle

- **Before section**：immutable plan §7.3 prose 要求 archive 零 placeholder path，但 executable commands 只直接检查
  METADATA、entry_points 与 importability；wheel/dist-info 依赖 shell wildcard 选择，RECORD 没有 exact path oracle。
- **After section**：fixed plan §7.3 以 Python exact-one selection 解压/安装 wheel，并分别校验 METADATA、entry_points、
  extracted relative names 与 `.dist-info/RECORD`。
- **Direct evidence**：Controller adjudication lines 50—58 要求 extracted wheel/zip name 与 RECORD 使用同一
  placeholder-path zero assertion，明确 expected exit/output，不依赖 shell wildcard，且不治理 untracked pycache 或合法
  top-level metadata。
- **修复内容**：
  - extracted tree 对 `dayu/web`、`dayu/wechat`、`dayu/render` exact prefix 命中必须为零；
  - CSV 解析 RECORD 第一列并执行相同 exact prefix assertion；
  - 四个 Python negative oracle 成功必须 exit 0，stdout 分别输出固定 `...: 0`；命中或 wheel/dist-info 数量不是一
    时 assertion 非零并打印 hits；
  - wheel 与 dist-info 由 Python `glob` + exact-one assertion 选择，shell 不做 wildcard 展开。
- **Rejected non-implementation**：未删除或治理 working tree untracked `__pycache__`；未把合法
  `top_level.txt=dayu` 当残留；未扩展 placeholder 之外的 packaging cleanup。
- **New plan line / SHA**：lines 552—580；SHA-256
  `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`。

### R11-PR-F05-已关闭-POSIX real smoke fixture source lock

- **Before section**：immutable plan §6.6 只写“复制现有 AAPL HTML fixture”，没有 exact path、复制后名称或 network/
  mutation 禁令。
- **After section**：fixed plan §6.6 锁定 tracked read-only source、两个 `workspace/tmp` 目标名与 no-network/no-mutation
  规则。
- **Direct evidence**：Controller adjudication lines 60—67 给出唯一 fixture path；本 gate read-only 验证该文件存在，
  大小 `1503780` bytes，SHA-256
  `24a830a0f1256e371d36a1f7f72e5e85a38037d1de2f6f966eb8457db42ff6d6`。
- **修复内容**：源固定为
  `tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`；只复制为
  `workspace/tmp/r11-posix-real/source/2024FY_AAPL_Annual_Report.htm` 与
  `workspace/tmp/r11-posix-real/source/2024FY_AAPL_Earnings_Call_Transcript.htm`，分别由既有 OLD rule 识别为 filing/
  material。
- **Rejected non-implementation**：未修改 fixture；未下载、生成或更新 fixture；未为 smoke 增加分类特例；未写入
  tracked 路径。
- **New plan line / SHA**：lines 452—460；SHA-256
  `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`。

### R11-PR-F06-已关闭-zero-filing call cap 与 Ruff version oracle

- **Before section**：immutable plan §5.2.10 只写 call cap 等于 filtered recognized filing count，没有显式定义 count=0；
  §8.1 只有 Ruff finding JSON baseline，没有 version identity oracle。
- **After section**：fixed plan §5.2.10/§5.3 锁定 zero-filing empty-state 与 owner test；§8.1 锁定 baseline/current 使用
  同一 `python -m ruff --version` 及 drift stop/relock 流程。
- **Direct evidence**：Controller adjudication lines 69—76 要求零 filing 时 cap=0、全部 call candidates typed skipped、
  不得 minimum-one，并要求 Ruff version 一致，否则 stop/relock 且不得把 version rule drift 算 current finding。
- **修复内容**：
  - zero filtered filings 时所有 `EARNINGS_CALL` candidates 进入带 cap reason 的 typed skipped；owner test 明确覆盖；
  - Controller 在 accepted-plan parent 锁 baseline 时记录同一已激活 `.venv` 的命令原文；implementation/aggregate 在
    Ruff delta 前逐字比较；version drift 由 Controller 在同一 implementation input tree 同时重锁 version 与 full
    baseline。
- **Rejected non-implementation**：未增加 minimum-one；未硬编码 iteration/version magic；未用 baseline 更新、noqa 或
  exclusion 掩盖 current finding。
- **New plan line / SHA**：lines 256—280、591—617；SHA-256
  `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`。

## 4. Rejected / no-action preservation ledger

- Windows：fixed plan lines 414—427 仍只锁 outcome/invariants/real `cmd.exe` evidence；未新增候选算法家族、N 次
  iteration magic、`subprocess.list2cmdline`、fallback 或 shim。
- Compatibility / OLD：fixed plan lines 234—236 仍保留 structured auto-recursion；lines 349—351 仍锁三个 upload
  grammar default 为 `auto`，未兼容旧 `create` default。
- Platform：fixed plan lines 379—382 仍由实际生成 OS 决定格式；未新增 cross-platform `--platform`。
- Resolver：fixed plan lines 355—359 只约束一次 existing public method call，明确不治理内部 HTTP hop；未修改 resolver
  owner。
- Deferred scope：Issue 142/151/175/177/178、R12、真实 Web/WeChat/render、Topic 8/9、统一 authorization 仍是
  no-touch；没有新增 production/test/README/design/CI 修改。

## 5. Open questions 与 residual risks

- Open questions：本 fix gate 无；R11-PR-F01—F06 均已在 plan 文本层闭合，待 Controller validation 与双路 re-review。
- Residual risk：Windows quoting algorithm 仍需在 R11-S2 由真实 `cmd.exe` evidence 驱动收敛；这是 Controller 明确拒绝
  plan 预猜后的 implementation/release gate，不是本 fix gate 的 open finding。
- Tracking destination：Controller plan-fix validation；通过后对完整 fixed plan 并发 MiMo/DS re-review。implementation
  仍未授权。

## 6. Git status / diff-check evidence

Codex 开始前的 `git status --short` 已存在以下用户/Controller-owned 状态：

```text
 M docs/host/issues-implementation-control.md
?? docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-controller-validation.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-entry-controller-validation.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-ds.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-mimo.md
```

本次 recorded final status 只在上述状态上新增本 evidence path；control 与既有 review artifacts 保持不动：

```text
 M docs/host/issues-implementation-control.md
?? docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-controller-validation.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-entry-controller-validation.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-ds.md
?? docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-review-mimo.md
```

验证命令与 recorded oracle：

| Command | Expected / recorded result |
|---|---|
| `wc -l <fixed-plan>` | `773` |
| `shasum -a 256 <fixed-plan>` | `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025` |
| `git diff --check` | exit `0`，零输出 |
| `git diff --cached --name-only` | exit `0`，零输出，证明未 stage |
| `git diff --no-index --check /dev/null <fixed-plan>` | exit `1`（untracked file 与 `/dev/null` 有内容差异），零 whitespace-error 输出 |
| `git diff --no-index --check /dev/null <fix-evidence>` | exit `1`（new artifact），零 whitespace-error 输出 |

## 7. Fix conclusion

`pass`：六项 accepted findings 在 plan owner/validation boundary 全部关闭；Controller rejected candidates 均未实现；
没有新 material finding。fixed plan 的 gate marker 已更新为 `READY_FOR_CONTROLLER_PLAN_FIX_VALIDATION`。

READY_FOR_CONTROLLER_PLAN_FIX_VALIDATION
