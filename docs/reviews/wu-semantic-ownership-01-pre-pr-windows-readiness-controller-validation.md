# WU-SEMANTIC-OWNERSHIP-01 pre-PR / Windows readiness controller validation

## 结论

`LOCAL_READY / EXTERNAL_AUTHORIZATION_REQUIRED / AR-F07_PENDING_RELEASE_BLOCKER`

本地 remediation、aggregate validation、aggregate deepreview 和 accepted evidence commit 均已完成。唯一尚不能由本地证据关闭的 release blocker 是 AR-F07：必须在 GitHub Windows runner 上取得两条现有 workflow 的非跳过成功结果及 artifact。

## 当前 Git / workflow 事实

- branch：`phaseflow/host-issues-control`
- current HEAD：`8aeb67be017f1f4b9c56bcc51bc297fedab55a12`
- accepted product head：`85aa7184a694448a5b27da7cca52f753f84d6e20`
- 当前 branch 无 upstream；remote `github` 为 `https://github.com/noho/dayu-agent-r.git`。
- `git ls-remote --heads github phaseflow/host-issues-control` 无结果，说明该 remote branch 尚不存在。
- `.github/workflows/r12-init-windows.yml` 与 `.github/workflows/r11-upload-script-windows.yml` 自 `ed9bfa9f` 后无改动；两者均支持 `workflow_dispatch`，使用 `windows-latest`、Python 3.11 和 locked constraints，并上传各自的 Windows 验证 artifact。
- 本地 POSIX/可运行验证、full suite、coverage、pyright、Ruff 基线、build、source/propagation/security scans 已通过；Windows-only tests 的本地 skip 不是 Windows success evidence。

## 获得明确远端授权后的固定顺序

1. 非强制 push 当前同名 branch 到 `github`，不得改写历史。
2. 对该 branch 分别触发 `r12-init-windows.yml` 与 `r11-upload-script-windows.yml`。
3. 验证两条 run 均为 `windows-latest`、checkout SHA 包含既有 `ed9bfa9f` workflow 基线及本 WU fix/evidence commits、Python 3.11 locked constraints 生效、job 未 skip/cancel 且测试零失败。
4. 下载并核对 `r12-init-windows-*` 与 `r11-windows-upload-script-*` artifacts，包括 cmd invocation、生成脚本、hash/count、JUnit 与记录文件；只有证据完整才关闭 AR-F07。
5. 随后创建 draft PR，执行双路 PR review、accepted finding fix、re-review、final push、draft-PR-pass 和 final closeout。

## PR 与 residual boundary

- `WU-SEMANTIC-OWNERSHIP-01` 没有记录一个可由本 PR 自动关闭的独立 GitHub issue；PR body 不得用 closing keyword 关闭 Issue 142、151、175、177、178 或 Web/WeChat/render trackers。
- AR-F06 继续由未来 Host scheduler/lifecycle owner 承接；AR-F07 是当前唯一外部 release blocker。
- Gemini 是低预算测试账号；quota/provider adherence 为 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，不得增加真实调用，也不得修改 provider/model/key/retry/quota/budget 配置。
- Config 与 Host 内部 SQLite/EventLog 属于同一可信本地域；API Key/headers 在此域内不新增泄露面。Tool Trace、audit、公开输出、LLM-facing、日志、diff 和 review artifact 保持明文零泄露。
- 保留 allowed paths、filesystem containment、symlink guard、Web DNS/peer/private/proxy/redirect/resource budgets、atomic write/swap/rollback、process fencing 与 wait late-publication fence；未设计或实现统一 tool authorization framework。
- Topic 8 的 Engine generic exception 240 字符硬编码、脱敏与截断后缀保持不变；所有 deferred issue 能力均未偷带实现。

## Blocker

Push、workflow dispatch、artifact 下载和 draft PR 都会改变或使用远端状态，当前没有明确外部授权。Controller 已穷尽本地可完成工作；在收到授权前必须停在 AR-F07，不得以 waiver、Linux/POSIX 结果或本地 Windows skip 替代。
