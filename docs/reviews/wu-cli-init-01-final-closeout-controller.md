# WU-CLI-INIT-01 Final Closeout

## Gate

- Work unit：`WU-CLI-INIT-01`
- Gate：`final closeout`
- Controller：AgentController
- 日期：2026-07-30
- Draft PR：[#188](https://github.com/noho/dayu-agent-r/pull/188)
- PR 状态：`OPEN`、`draft`
- PR base：`main`（`3bfbd7f9`）
- 已通过 PR review 的 head：`19716827`

## What changed

1. 第一轮 CLI CI 被定义为真实运行、完整观察、用户裁决、冻结 oracle 的校准流程，
   而不是依据既有 contract 直接判定产品正确性。
2. `dayu-cli init` 的 accepted oracle 已写入
   `docs/cli_ci_oracles.json`，覆盖 workspace resolution、完整 publication、
   模型默认值与单次 override、secret handling、交互退出码、
   FIRST/PRESERVE/OVERWRITE/RESET/repair 和真实 provider 验证。
3. 裸 `init` 默认使用 `./workspace`；`init --config` 不存在；Agent 命令的公开
   单次模型参数为 `--model/-m`，旧 `--model-name` 不存在。
4. `init` 选择的普通/思考模型投影到对应全部 scene；`conversation_compaction`
   使用相同 provider/model family。单次 `--model/-m` 只覆盖主 Run，
   不改 workspace，也不改变 compactor。
5. 未执行 `init` 时，package ordinary 与 compactor 默认配置使用同一 Mimo Token Plan
   family，不要求用户同时提供两家默认 provider credential。
6. 交互输入的可恢复错误在原步骤重试；parser misuse=`2`、未完成时 EOF=`1`、
   SIGINT=`130`；RESET 默认 No 取消后 workspace 不变并返回 `0`。
7. workspace publication oracle 冻结为 5 个受管目录、43 个受管文件和
   16 个 model pointer，并通过版本化 manifest 和内容摘要判定。
8. 15 个 model choice 的真实 provider matrix 已完成一次 retained run；
   provider 不可用、缺 credential、拒绝或限流保持为真实环境观察，
   不被伪装成产品成功。
9. init-owned config 只保存 credential ref/template。Host SQLite/WAL 保存 resolved
   credential 明文是用户接受的 Host durable execution snapshot 行为；屏幕、日志、
   Tool Trace、报告、LLM-facing 内容及其它非 Host artifact 仍不得泄露该值。

## Validation

- init/model/Service focused suite：`740 passed, 5 skipped, 3 warnings`。
- 目标 owner coverage：每个文件不低于 80%，aggregate 88%。
- PR review 暴露并修复 7 个真实 assembly fixture 的 credential migration 漏项：
  修复前 45 个节点因 `missing env MIMO_PLAN_API_KEY` 失败。
- 7 个受影响测试文件定向复跑：`105 passed, 3 warnings`。
- CLI/runtime/service + combined tools：`1589 passed, 7 skipped, 3 warnings`。
- MiMo tools-inclusive re-review：`1940 passed, 8 skipped`。
- DS 全仓 re-review：`5960 passed, 0 failures`。
- 完整 pyright：`0 errors, 0 warnings, 0 informations`。
- workspace manifest SHA-256：
  `a4865273f11ce059aaabaf9d91ee1154a7f5c1f26794828c343a20e0e73cea88`。
- retained provider report：15/15 internal contract valid、15/15 canonical
  no-fallback valid、overall exit 0、0 persistence violation。
- aggregate deepreview、aggregate fix re-review、PR review fix re-review：
  AgentMiMo 与 AgentDS 最终均为 `PASS`。

三条 warning 均为既有 `edgar` deprecation warning，不是本 work unit 引入。

## Docs updates

- `docs/cli_ci.md`
- `docs/cli_ci_oracles.json`
- `docs/cli_init_workspace_manifest_v1.json`
- 根 `README.md`
- `dayu/config/README.md`
- `dayu/service/README.md`
- `tests/README.md`
- `docs/host/ui-implementation-control.md`
- `docs/reviews/wu-cli-init-01-*.md` Gateflow artifacts

## Finding status

1. 所有 plan、slice code review、aggregate deepreview 和 PR review 的 blocking
   findings 均已修复并通过双路 re-review。
2. PR-F3（S3 后 7 个测试 fixture 缺少 Mimo compactor credential）已在正确测试
   input owner 修复；生产代码、ConfigLoader 和全局环境没有 fallback 或兼容分支。
3. PR body 未逐文件点名 `session_execution.py` 与 Host UI control 文档的两条
   informational observation 已 `rejected-with-reason`：PR summary 已准确覆盖对应
   用户语义，不要求列举每个变更文件。
4. 没有未裁决、未分类或 deferred blocking finding。

## Remaining risks and owners

1. 外部 provider availability 是 retained run 的时点事实。
   - 分类：`assigned to environment/provider owner`
   - 缓解：内部 contract 与 no-fallback 15/15 有效，不依赖全部 provider 可用。
2. 真实 Windows junction/reparse 与 `setx` 路径未在本地 Darwin 验证。
   - 分类：`tracked by existing issue`
   - Owner：GitHub Issue #184。
3. 测试模块当前各自拥有完整 assembly env helper；未来若 fixture 架构统一，
   应在对应测试 hardening work unit 中评估共享 owner。
   - 分类：`assigned to later hardening work unit`
   - 当前状态：无 correctness failure，full suite 与类型检查均通过。

## Draft PR and issue status

- Draft PR：[#188](https://github.com/noho/dayu-agent-r/pull/188)
- 当前 work unit 不是 GitHub issue，因此 PR body 不使用 closing keyword，
  也不需要 issue closeout comment。
- PR 保持 draft；本 Gateflow 未执行 approve、mark ready、request reviewers 或 merge。

## Completion

- Work unit status：`completed`
- Gateflow status：`final closeout pass`
- 用户合并 draft PR #188 后的下一入口：继续第一轮 CLI oracle 校准，
  按一个命令一个命令的顺序运行并裁决下一个 CLI 命令；`init` 不再作为阻塞项。
