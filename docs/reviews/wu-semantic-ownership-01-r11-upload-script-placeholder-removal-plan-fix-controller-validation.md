# WU-SEMANTIC-OWNERSHIP-01 / R11 plan-review finding fix Controller validation

## 1. Verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；R11 只是内部 remediation sub-WU。
- fixed plan：`docs/host/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan.md`，773 lines / 61,810 bytes，
  SHA-256 `48bcfbaa648500d16a5148d4d0e4dba34db572a64c90e29ab8083242bd97d025`。
- fix evidence：`docs/reviews/wu-semantic-ownership-01-r11-upload-script-placeholder-removal-plan-fix-codex.md`，
  219 lines / 15,754 bytes，SHA-256
  `efb3eec7345564caa6cd002fa2210404e755b20689ad63eea2e109cf6586cf40`。
- baseline：branch `phaseflow/host-issues-control`；HEAD
  `2b14b2fbc89654267e3d33daa2ae410ceff45e68`；staged tree empty。
- Controller verdict：`PASS / READY_FOR_DUAL_COMPLETE_FIXED_PLAN_REVIEW`。

本 verdict 只授权 AgentMiMo / AgentDS 对上述固定 plan 做并发完整 re-review；不接受 plan，不授权
implementation、stage/commit、R12、push 或 PR。

## 2. R11-PR-F01：S2 consumer 发现 S1 owner gap

已关闭。Plan §5.3 逐字段固定 entry type、ticker、action、file、fiscal、amended、dates、company、
overwrite、material 与 skips 的 S1 owner contract 和 S2 消费映射。Plan §9.1 只允许在真实 consumer
证明 typed fact/enum/optional ownership gap 时由 Controller 授权回到原 S1 owner 文件，随后从 S1 checkpoint
重跑；明确禁止 adapter/renderer/fixture fallback、重算、兼容 seam、新 sub-WU、新 slice 或中间 commit。

## 3. R11-PR-F02：symlink 防护边界

已关闭。Plan 将检查边界固定为 workspace/source root 自身及 root 内 candidate/output components：root
自身为 symlink、root 内路径 component 或 target 为 symlink 均拒绝，同时要求 lexical 与 resolved containment。
它明确不向 root 外祖先传播策略，因此 `/tmp -> /private/tmp` 一类 external ancestor symlink 被允许，不会把
主机目录布局误判成产品输入。

## 4. R11-PR-F03：`--infer` / `--overwrite` 语义

已关闭。两者都精确为 `action="store_true"`、`default=False`，并要求自解释 help、default-false / explicit-true
grammar tests。`--infer` 只触发一次既有 FMP public resolver method，缺少 key 时失败，未传时零 provider access；
`--overwrite` 只投影为每 entry 的 storage fact。Publisher 对既有普通 target 的 atomic replacement 独立于
storage overwrite，不新增 `--force-output` 或另一权限开关。

## 5. R11-PR-F04：wheel archive 与 RECORD oracle

已关闭。Plan 对 wheel 和 dist-info 都要求 exact-one selection；对 extracted archive path 与 `RECORD` 分别执行
零 `dayu/web`、`dayu/wechat`、`dayu/render` oracle，并要求四个 negative oracle exit 0、打印固定 zero marker。
命中、缺少或多个 wheel/dist-info 都以 assertion 非零退出；不依赖 shell wildcard 展开。

## 6. R11-PR-F05：真实 fixture lock

已关闭。Plan 固定唯一源 fixture：
`tests/fins/fixtures/aapl_xbrl/fil_0000320193-24-000123/aapl-20240928.htm`，大小 1,503,780 bytes，
SHA-256 `24a830a0f1256e371d36a1f7f72e5e85a38037d1de2f6f966eb8457db42ff6d6`；只复制到
`workspace/tmp/r11-posix-real/source/2024FY_AAPL_Annual_Report.htm` 与同目录 transcript 名称，不修改 fixture，
且 smoke 禁止网络。

## 7. R11-PR-F06：zero-filing call cap 与 Ruff baseline

已关闭。Fins owner contract 明确 zero recognized/filtered filings 时 call cap 为 0、所有 call typed skipped，
并有 owner test。Ruff baseline 在 accepted-plan parent 上同时锁 `python -m ruff --version` verbatim oracle 与
full JSON baseline；implementation/aggregate 必须在 delta 前逐字匹配版本，漂移即 stop，由 Controller 在同一
输入树重锁二者，禁止将规则漂移算作 current finding 或用 baseline 更新掩盖 finding。

## 8. Rejected candidates 与边界保持

- 没有保留旧 `create` default；current direct 与 batch grammar 都以 `auto` 为产品 contract。
- 没有使用 `subprocess.list2cmdline` 作为实现、安全证明或 fallback；Windows algorithm 保留给真实
  `cmd.exe` evidence-driven 反证。
- 没有删除 OLD structured auto-recursion，也没有预猜 Windows iteration count。
- 没有新增 cross-platform `--platform`、`--force-output`、兼容 branch、旧 JSON protocol 或 test shim。
- FMP 仍是一次既有 public resolver method 调用，不把内部 HTTP hop count 当业务 contract。
- Windows 本地未运行时只能是 `PENDING_RELEASE_BLOCKER`，不得转 residual 或冒充 closed。

## 9. 完整计划与 scope 复核

Controller 已完整读取 773 行 fixed plan。三 slice 数量、依赖和 owner 未漂移：S1 Fins typed classification；
S2 current CLI grammar、单次 FMP resolve、POSIX/Windows renderer/publisher；S3 placeholder/public packaging 删除、
README 与真实 Windows gate。验证仍覆盖 affected/full tests、changed-file coverage `>=80%`、full pyright、
同版本 Ruff、diff check、README、source/propagation/security/deferred scans、POSIX real smoke、wheel smoke 和
release-blocking real Windows evidence。

Issue 142、151、175、177、178、R12、真实 Web/WeChat/render、Topic 8/9 和统一 authorization framework
仍为 no-touch。保留并验证 containment、symlink、atomic replacement、argv injection 与 secret non-persistence；
没有把这些局部安全机制升级成统一权限框架。

## 10. Workspace 与 gate state

- plan/fix 范围只有 R11 plan 与 evidence；Controller protected control artifact 未被 Agent 覆盖。
- `git diff --cached --name-only`：empty。
- `git diff --check`：pass。
- accepted/open plan finding：0（等待 complete fixed-plan re-review）。
- blocker：0。
- next gate：AgentMiMo / AgentDS 并发完整 fixed-plan re-review。
- implementation、accepted-plan commit、R12、push/PR：未授权。

READY_FOR_DUAL_COMPLETE_FIXED_PLAN_REVIEW
