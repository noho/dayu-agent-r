# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4 remediation plan Controller validation

## Inputs and content lock

- baseline：`54e2dcbf653fb8c37b0206bd7aabbbf329ef040e`。
- plan：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`，528 lines，SHA-256 `a290f4184b42ce841f7002f7fab179b12caa42c70ca41e5ee8c60c03c3ee2cf6`。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-ar-f07-win4-remediation-plan-codex.md`，80 lines，SHA-256 `4cff2eeb1bed842a796be5ac6cea974c2d2116fd6f0df2c1be5b3b714786cf71`。
- fourth Windows evidence adjudication：`docs/reviews/wu-semantic-ownership-01-ar-f07-fourth-windows-evidence-controller-adjudication.md`。
- staged tree：empty；plan gate没有产品、测试、workflow或README diff。
- `git diff --check`：PASS。

## Controller independent fact checks

### WIN4-F01

Controller 直接读取 R11 artifact 的 `cli-generated-upload.cmd`：真实业务命令包含 `upload_filing`、`--action create`、ticker/file/fiscal fields，但没有 `--company-name`。source artifact SHA-256 是 `7473d33d2b53e02753e0f52f82ac57f72a653e0d3cdd513e25f95d34943a96e6`；仓库 LF fixture SHA-256 是 `24a830a0f1256e371d36a1f7f72e5e85a38037d1de2f6f966eb8457db42ff6d6`。

`dayu/fins/pipelines/upload_company_meta.py::upsert_company_meta_for_upload()` 是 fresh create/update company-meta要求的唯一 owner；没有 current resolver-version existing meta 时，`_require_company_meta_field(..., "--company-name")` 明确 fail closed。既有 POSIX real workflow显式传 `Apple Inc.` 并通过。AgentCodex又以真实 R11 source复现，并从现有 pipeline owner result取得缺 company-name原因；LF/CRLF direct Docling两者都成功。因此计划把 F01 收窄为 Windows real-smoke input/oracle fix、保持 Fins production zero-diff是正确裁决；当前不需要 speculative diagnostic schema。

### WIN4-F02

Controller 扫描 `dayu/cli/init_environment.py::_persist_windows_environment()`：当前 `subprocess.run` 使用 `capture_output=True, text=False`，后续只读取 `completed.returncode`，stdout/stderr没有任何消费者，也没有 direct native timeout。R12 evidence在 outer Popen `returncode=1` 后仍卡在 stdout reader EOF，证明无消费者 pipe lifetime 是错误 contract，且 outer 180秒测试预算不能替代产品 native-command bound。

计划把 setx stdio改为 DEVNULL、保留 argument tuple与`setx` registry authority、增加 direct timeout并以 names-only typed failure收口，改在正确 owner。它没有 retry、shell、PowerShell、winreg/reg.exe fallback、process-tree framework或更长 outer timeout。

### WIN4-F03

R12 JUnit证明 `subprocess.run(input=...)` 的 secret-bearing input进入 stdlib `_communicate` frame并被pytest展开。最终计划不再让 secret值进入 `communicate(input=...)`：以匿名 temporary files承载 stdin/stdout/stderr，Popen只接收 handles，wait helper不接收 input，timeout renderer只保留 category/timeout/returncode-at-timeout/cleanup facts并用`pytrace=False` fail。这个 owner在test helper，不污染production/JUnit plugin/workflow。

## Slice and boundary judgment

三 slices沿真实 owner与依赖切分：S1单独校正 R11输入；S2修改production setx native stdio/timeout；S3在S2后修改outer test evidence projection并统一更新tests README。它们不是按文件数机械拆分：S1可独立验证并从R12 embedded-R11中消除污染，S2的production contract必须先由owner tests锁定，S3不能替代S2。每个slice有allowlist、negative cases、stop condition和后续真实Windows gate。

明确保持：

- Fins company-name fail-closed、storage/Docling/direct schema零改动；
- setx作为Windows persistence authority，不换registry实现；
- strict UTF-8与real Windows nodes不skip、不xfail、不增加outer timeout；
- Config/Host internal SQLite/EventLog trusted-local与Tool Trace/audit secret plaintext-zero裁决不变；
- 无统一authorization、secret infrastructure或Issue 142/151/175/177/178、Web/WeChat/render实现。

## Mandatory reviewer challenges

1. Windows上anonymous temporary file handles作为Popen stdio、`close_fds=True`与child handle duplication是否在Python 3.11 contract内，cleanup是否不会再次等待descendant pipe。
2. 30秒setx owner timeout是否足够有界且不伪装回滚；`TimeoutExpired`任何argv/value都不会传播或进入result/repr/log。
3. F01生成脚本oracle是否能区分regeneration comment和真正业务command，避免简单字符串计数、loose parser或从结果倒推输入。
4. S3是否保留ordinary nonzero、timeout时已退出1、尚未退出、cleanup timeout和strict UTF-8 decode的互斥真实事实，且没有把post-kill returncode伪装成deadline时状态。
5. “清空本地变量”只能用于降低failure-frame持有，不得被写成内存擦除保证；安全acceptance是sentinel不进入JUnit/workflow/review evidence。

## Decision

结论：`PASS_WITH_MANDATORY_CHALLENGES / READY_FOR_DUAL_COMPLETE_PLAN_REVIEW / IMPLEMENTATION_NOT_AUTHORIZED`。

下一 gate 由AgentMiMo/AgentDS并发完整plan review。所有accepted plan findings必须由AgentCodex修复后再并发re-review；在plan accepted commit前不授权implementation、stage、commit、push或workflow dispatch。
