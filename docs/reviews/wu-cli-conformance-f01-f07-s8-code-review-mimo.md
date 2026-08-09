# Code Review — WU-CLI-CONFORMANCE-F01-F07 S8 Gate

## Scope

- Mode: S8 gate evidence/code review (PR 190)
- Target commit: `9fec164715bc6af7a4a7d7446cb45d49593ec64f`
- Base: `cd6344c0`
- Bundle path: `/Users/leo/workspace/.dayu-cli-ci/pr190-wu-cli-conformance-f01-f07-s8-20260803T022326Z-9fec164715bc/bundle`
- Bundle digest: `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72`
- Review timestamp: `20260803-110502`
- Intended S8 files: `README.md`, `dayu/config/README.md`, `dayu/host/README.md`, `tests/README.md`, `docs/reviews/wu-cli-conformance-f01-f07-s8-implementation-codex.md`
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## 核验详情

### 1. Bundle Digest 与只读封存

- `bundle-digest.txt` 内容为 `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72`，与用户声明一致。
- `sha256sum -c SHA256SUMS` 全部 OK（444 行）。
- `sha256sum SHA256SUMS` 自身 digest 为 `7a80d9bcfb97bb7c8a80df8d2f10016d6f98577e01294f540a7ba2d9cea33b72`，与 bundle-digest.txt 精确匹配。
- `bundle-index.json` 记录 443 个 entries，与 SHA256SUMS 行数（443 data + 1 trailing）一致。
- `run-manifest.json` 中 `git_operations: {committed: false, staged: false, pushed: false}`，确认 bundle 是独立不可变封存。

### 2. Target Commit 与 Frozen Inputs

- `run-manifest.json.target_commit` = `9fec164715bc6af7a4a7d7446cb45d49593ec64f`，与用户声明一致。
- `metadata/frozen-input-hashes.json` 记录三份 frozen docs 的 SHA-256：
  - `docs/cli_ci.md`: `a241182d4d09e8843ea647947777bc7f6f71c5532fa148e2abb87ede3e748b82` ✓
  - `docs/cli_ci_oracles.json`: `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` ✓
  - `docs/cli_ci_scenarios.json`: `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` ✓
- 与 S8 implementation doc 第 2 节声明完全一致。

### 3. F01-F07 Oracle 交叉核验

所有七个 owner matrices 的 `status` 均为 `pass`，且每个 finding 均有独立证据链：

| Oracle | Matrix 状态 | 关键证据 | Adversarial 核验 |
|---|---|---|---|
| F01 | pass | help 4 份均 `--config` occurrence=0；parser 81 个 actions 无 config；7 条 rejection 均 exit 2；source scan 0 命中 | help 输出实物已读取确认无 `--config`；exit-code 文件内容为 `2` |
| F02 | pass | 3 lanes 均 runs=0, attempts=0, terminal_restored=true；draft_occurrences ≥ 1 | command-result.json 实物确认 exit_code=0, draft_occurrences=1 |
| F03 | pass | 7 条 frozen prompt/escape lanes 均 conforms=true, exit=0；3 条 preaccept escape 均 exit=0（cancel 后 REPL 正常退出）；3 条 double SIGINT 均 exit=130, cancel_requested=1, run_cancelled=1 | prompt-preaccept-escape terminal.txt 显示 "Cancelled."；command-result.json 确认 exit_code=130 |
| F04 | pass | final_run_count=2, read_only_rejections=2, runs_during_read_only=[0,0]；timeline 完整 | request_ids 互不相同，确认 fresh attachment |
| F05 | pass | real_provider=true, succeeded_run_count=3；effective tool schema 不含 `start_fins_preprocess`；canonical requested tools 含 download/list/read | 与 S8 doc 声明的工具链一致 |
| F06 | pass | 4 条 dispatch manifests 均 trigger=`context_governance_resolved`；3× CONTEXT_COMPACTED + 1× CONTEXT_COMPACTION_FAILED | event_sequence 顺序正确（terminal < manifest） |
| F07 | pass | deterministic matrix 711 passed/1 skipped；real invalid exhaust: rejected_count=2, failed_terminal=1, fallback_action=dispatch；real success: 3 compacts, 1 repair；post_compact_followups 3 runs 均 succeeded | followup answers 内容与 compact 后连续性一致（OLD_AAPL_NET_SALES 保留，第三轮按新 scope 计算 operating margin = 31.97%） |

### 4. Secret Scan 与 Provider 真实性

- `metadata/final-secret-scan.json`: scanned=442, finding=0, status=pass。
- `run-manifest.json`: `fake_provider_used=false`, `real_provider=true`, `provider_used=mimo`, `model_used=mimo-v2.5-pro`。
- S8 doc 声明 "本轮没有用 fake provider 替代 full-real"，与 manifest 一致。
- 41 个 redaction placeholders 来自 Host SQLite durable snapshot 中的真实 credential 脱敏，属于允许行为。

### 5. 完整验证结果

- `summary.json` 与 `validation-results.json` 一致：
  - Full pytest: 6603 passed, 10 skipped, 6 deselected ✓
  - Full pyright: 0 errors, 0 warnings ✓
  - S7 owner matrix: 711 passed, 1 skipped ✓
  - Affected coverage: composer 89%, run_keys 93%, session_execution 85%, aggregate 87% ✓（均 ≥ 80%）
  - Changed ruff: pass ✓
  - JSON tool: pass ✓
  - Target diff check: pass ✓
  - Controller worktree diff check: pass ✓
- S7 owner matrix 首次并发 timeout 已在串行 rerun 通过，classification 为 "non-governing test-environment interference"，有三条日志证据。

### 6. README 变更准确性

四份 README 的 dirty diff 与实现变更一致：

- **README.md**: 移除所有 `--config` 引用（与 F01 删除全局配置参数一致）；更新 session resume 配置读取说明（从所选工作区 `config/` 读取）；添加 interactive 不执行预处理的说明（与 F05 interactive 不含 preprocess 工具一致）；更新 Analyzer 输入发现说明。
- **dayu/config/README.md**: 将 interactive scene 工具标签从含 `fins-preprocess` 收窄为仅 `fins-read` + `fins-download`（与 F05 effective tool schema 不含 preprocess 一致）；新增 v2 compaction input/output schema 文档。
- **dayu/host/README.md**: 新增 `CompactAcceptedTruthV2` accept barrier 文档；新增 `context_governance_resolved` trigger 语义（与 F06 dispatch manifest 一致）；更新 `CONTEXT_COMPACTED` Memory 投影为 v2 schema + represented/dropped coverage（与 F07 实现一致）；收紧 Memory-to-compact 单向不变量。
- **tests/README.md**: 新增 F01-F05 owner coverage 描述和 F06-F07 Context Governance conformance 描述；明确 owner tests 不替代 real oracle smoke。

### 7. 三份历史失败 Bundle

S8 doc 第 6 节列出三份历史失败 bundle 及其 digest 和失败原因。`metadata/historical-failure-bundles.json` 确认三条记录保留。失败原因分别为：F03 pre-accept Escape failure、redacted supplemental failure evidence、double POSIX SIGINT lacked self-exit 130。与 commit history 中的修复链（`016d834a` → `63fca270` → `9fec1647`）一致。

### 8. Adversarial 检查

- **CLI 自报当 owner truth**: owner matrices 使用 EventLog、Host Run/Attempt、Tool Trace、SQLite payload projection 交叉核验，不依赖 CLI stdout 自报。F02 明确声明 "没有用 CLI 自报替代 durable owner"。✓
- **Exit code 当唯一证据**: 每个 exit code 均有 terminal output、command-result.json 和/或 owner projection 补充。F01 的 7 条 rejection 同时有 stderr 内容确认 argparse 错误。✓
- **Mock/fake provider**: `run-manifest.json.fake_provider_used=false`，所有 F05/F07 的 provider/model 字段均为 `mimo`/`mimo-v2.5-pro`。S8 doc 明确声明 "deterministic malformed candidate 只用于 owner tests；所有 provider 行为结论来自真实 Mimo"。✓
- **下游 projection 当 truth**: Memory 投影严格消费 committed canonical facts，不从 operation 内存对象反推。host/README.md diff 明确 "Memory 不消费 operation 内存对象"。F07 post_compact_followup 验证了 Memory 在 compact 后正确保留旧事实并使用新工具结果。✓
- **Bundle 可篡改性**: SHA256SUMS 自身 digest = bundle-digest.txt = 用户声明 digest，形成完整校验链。Python mode-bit 复核 writable paths=0（S8 doc 声明）。✓

## Open Questions

无。

## Residual Risk

- 真实 provider 输出具有模型非确定性，但本轮同时具备 deterministic owner matrix（711 passed）+ 真实 invalid/exhaust + 真实 accepted repair + 真实 artifact/Memory follow-up 的完整 conjunction。
- F06 matrix 中 tool-await lane 的 attempt terminal 为 `suspended` 而非 `cancelled`（canonical_attempt_cancelled_events=0），S8 doc 解释为 "等待态取消由唯一 RUN_CANCELLED 收口，不伪造第二个 ATTEMPT_CANCELLED"。该解释与 f03-matrix.json 数据一致，但该语义差异值得 controller 确认是否符合预期。
- S7 owner matrix 首次并发 timeout 的 classification 为 "non-governing test-environment interference"，无稳定 reproduction。如未来 CI 环境变更可能复现。

## Gate Conclusion

**READY-FOR-CONTROLLER-ADJUDICATION**

Bundle 验证通过，F01-F07 owner matrices 全部 PASS 且有独立证据链，secret scan 通过，frozen inputs 未变更，README 变更与实现准确对应，历史失败 bundle 已保留，无实质性 findings。
