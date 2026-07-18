# WU-SEMANTIC-OWNERSHIP-01 / R12 S3 cumulative code review Controller 裁决

## 范围与固定证据

- 本裁决属于既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 的 R12 S3 complete cumulative code review；不是新 WU。
- 固定计划：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，SHA-256 `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`。
- implementation：`docs/reviews/wu-semantic-ownership-01-r12-s3-implementation-codex.md`，222 行 / 14,272 字节 / SHA-256 `4e0f8938a813b801bf2a5ff736df9d10190e44b8072ff8a53864201072394ae8`。
- Controller validation：`docs/reviews/wu-semantic-ownership-01-r12-s3-controller-validation.md`，120 行 / 9,296 字节 / SHA-256 `60aa02ccd607cba1b43984a9f2fdcdfa00b8a5beef0e8840c1e9e2a3896e7355`。
- AgentMiMo corrected review：`docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-mimo.md`，246 行 / 14,143 字节 / SHA-256 `be4253cbff6e844fc44d289946d57f2b33da8f8899085e200b93d8d686334b53`。
- AgentDS corrected review：`docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-ds.md`，288 行 / 27,553 字节 / SHA-256 `4e0cf14caf296cdb287c62fd2a079af304351d4a97d05ac7439fbe36121ebc4a`。
- 两路都完整覆盖固定 20-path target；Controller 再次复现 manifest digest `2835b3e137f0a7ddef150fb02b728cf73f3488abeccebb534d947bd60ded6f2d`，staged tree 为空，`git diff --check` 通过。

## Review 结论

AgentMiMo 在修正错误的 path-sort composite digest 后报告 `0` finding，全部 mandatory challenge PASS。AgentDS 报告三个候选，但其 Finding 01 和 Finding 03 的正文已分别证明当前行为正确且无需改动；Finding 02 没有给出当前可达故障或当前设计要求。Controller 逐项裁决如下。

## Finding 裁决

### MIMO

- `finding = 0`：接受 reviewer 的 no-material-finding 结论。
- 初始 manifest 假漂移已由同一任务 follow-up 用固定完整行排序命令纠正，最终 artifact 没有保留 finding/open question；这不是 product finding。

### DS-F01 — `rejected-with-reason` / no fix

DS 标题声称 Windows workflow 的 `if: always()` “could mask” init step failure，但正文直接证明相反：

- GitHub Actions job 的前序失败不会因为后续 `always()` step 成功而变成成功；job conclusion 仍保留失败真值。
- R11 两个真实节点是独立 release evidence，计划明确要求即使 init node 失败也尽可能继续产出；artifact upload 也必须在失败时执行，才能保留诊断。
- record step 先创建 name-safe evidence；upload 仍有 `if-no-files-found: error`，不会声称一个不存在的 artifact 已成功。

因此这是 workflow 正确语义的说明，不是 defect。新增 runbook 或修改 `if: always()` 会重复现有 workflow/Controller artifact 已明确的 job-level truth，并可能丢失独立 R11/失败诊断证据。裁决为拒绝、无需代码或文档 fix。

### DS-F02 — `rejected-with-reason` / no fix

DS 建议给 `_format_operation_error` 增加通用长度截断，但没有给出可达的 correctness/security/stability failure：

- `run_init_command` 只把闭合集合 `CliInitOperationError`、`InitCatalogError`、`EnvironmentPersistenceError`、`InitWorkspaceError`、`RuntimeFileLockError` 交给该 helper；不是任意外部异常入口。
- `InitWorkspaceError` 的 retained paths、public root states、stage、partial-deletion 和 durability truth 是恢复/审计所需的 owner-produced 有限 transaction 事实；无证据表明当前单 transaction 会生成无界列表。
- Topic 8 的 240 字符硬编码裁决只保留 Engine generic exception projection；它不是跨 CLI 的通用 truncation owner。把该数字或另一 magic bound复制到 init 会扩大明确 no-code decision，并可能截掉恢复路径真值。
- prewarm exception message 已明确不进入该 helper，只投影 class name 与固定摘要；secret value 仍不进入 CLI diagnostic。

因此当前没有接受 truncation fix 的直接动机；该建议是无当前 owner/需求的通用化，不实施、不 defer、不建新 issue。

### DS-F03 — `rejected-with-reason` / no fix

DS 自己的 expected/actual/evidence 已确认 Ollama 的 empty dynamic input 正确选择计划允许的 default，并由 owner tests 覆盖；标题中的“untested edge”与正文事实矛盾。stale prompt caller 已迁移到显式选择，没有 production implicit default fallback。裁决为无 defect、无需 fix。

## Open Questions 与 residual reconciliation

- **Windows real runner**：保留 `PENDING_RELEASE_BLOCKER`。本机 Darwin 的五个 Windows-only skip 不是成功；`.github/workflows/r12-init-windows.yml` 必须在真实 Windows runner 成功运行并产出 name-safe evidence，才能写 S3/R12/umbrella final pass。owner/destination 是 R12 Windows workflow release gate；这不是 deferred code finding。
- **DS coverage open question**：不是 blocker。AgentCodex 与 Controller 已分别运行固定测试/七文件 coverage/full pyright/Ruff；reviewer 不重复运行并不使两份独立验证失效。
- **Windows directory crash-durability、两 managed roots 非 single-syscall、RESET external writer、`setx` cross-variable non-transactionality**：均是 fixed plan §10.1 已分类的当前 contract/residual；README 没有扩大承诺。owner 分别是 R12 platform transaction contract、per-root rollback contract、RESET 前停止 active Dayu 的用户责任和 Windows environment store contract。
- **prewarm transitive import future drift**：future module change 必须由 current stop-condition smoke 捕获；不是当前 defect，也不引入 lifecycle/cache framework。
- **full Ruff 144 historical diagnostics**：repository owner 的 immutable baseline，R12 零新增/零移动已验证；不是 R12 accepted residual finding。

## 最终 finding ledger

| 来源 | 候选数 | accepted | rejected-with-reason | deferred | needs-more-evidence |
|---|---:|---:|---:|---:|---:|
| AgentMiMo | 0 | 0 | 0 | 0 | 0 |
| AgentDS | 3 | 0 | 3 | 0 | 0 |
| Controller direct | 0 | 0 | 0 | 0 | 0 |

- current accepted/open finding：`0`。
- local blocker：`0`。
- unclassified residual：`0`。
- external release blocker：`1`（真实 Windows workflow evidence）。

## Decision 与 next entry point

Code review decision 为 `PASS_WITH_ZERO_ACCEPTED_FINDING_AND_WINDOWS_RELEASE_BLOCKER`。按用户固定 gate sequence，下一步仍先由 AgentCodex 生成 zero-change fix/disposition artifact，证明三个 rejected/no-fix 候选未导致 product/test/README/workflow drift，并重跑 manifest/diff/staged boundary；随后进入 AgentMiMo / AgentDS 并发 complete cumulative re-review。只授权：

- 新增 `docs/reviews/wu-semantic-ownership-01-r12-s3-code-review-fix-codex.md`；
- 不得修改 20-path target、计划、既有 review/Controller artifacts、control、其它 product/test/docs/workflow；
- 不得 stage、commit、push、PR、aggregate 或关闭 S3/R12/umbrella。
