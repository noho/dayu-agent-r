# PR-A01 Re-Review: AgentMiMo Independent Verification

## Scope

- Mode: PR Review Re-Review (local fix diff)
- PR: [#190](https://github.com/noho/dayu-agent-r/pull/190)
- Reviewed remote head: `a4ff05db`
- Local HEAD: `a4ff05db`（未提交 diff）
- Fix artifact: `docs/reviews/gateflow-wu-cli-interactive-02-pr-review-fix-codex-20260802.md`
- Adjudication: `docs/reviews/gateflow-wu-cli-interactive-02-pr-review-adjudication-20260802.md`
- Initial review: `docs/reviews/pr-review-wu-cli-interactive-02-mimo-20260802.md`
- Output file: `docs/reviews/pr-rereview-wu-cli-interactive-02-mimo-20260802.md`
- Changed files: 4 (`63 insertions, 78 deletions`)

## Independent Verification Method

不依赖 Codex fix artifact 的验证结论；以下每项均从 workspace 当前 diff 和源文件独立读取。

## Finding Verification: PR-A01 / accepted-low / duplicate accepted-result required-field owners

### Adjudication Requirements Checklist

| 要求 | 验证结果 | 证据 |
|---|---|---|
| 在 `CompactionOperationResult` 上提供两个 required accessor | ✅ | `compaction_operation.py:516-546`：`required_successful_response_identity()` 和 `required_proposal_manifest_reference()` |
| 迁移两类 caller | ✅ | `dispatch.py:2551,2554` 调用 owner accessor；`engine_ingest.py:3121,3124` 调用 owner accessor |
| 删除四个 local helpers | ✅ | `grep -rn` 全仓零命中；dispatch.py 旧定义位置（原 6254-6289）现为 `_validate_proactive_resume_snapshot` 尾部；engine_ingest.py 旧定义位置（原 8815-8850）现为 `_required_accepted_attempt_number` 尾部 |
| existing guard test 移到 result owner | ✅ | `test_compaction_operation.py:958-962`：从 `dispatch._required_compactor_manifest_reference(result)` 改为 `result.required_proposal_manifest_reference()` |
| 补 response identity missing guard test | ✅ | `test_compaction_operation.py:965-988`：新增 `test_accepted_compaction_missing_successful_response_identity_guard_fails_closed` |
| 不得改变 dataclass fields | ✅ | 字段定义（行 507-514）未变：8 个字段、类型、顺序均保持 |
| 不得改变 operation result construction | ✅ | diff 未触及 `run_compaction_operation()` 或任何构造点 |
| 不得改变 wire/schema | ✅ | 无 schema、payload、event 格式变更 |
| 不得改变 terminal CAS | ✅ | 无 `compaction_terminal.py` 变更 |
| 不得改变 accepted/rejected behavior | ✅ | proactive path（dispatch:2550-2555）和 reactive path（engine_ingest:3120-3125）均机械替换为 owner accessor，逻辑分支不变 |
| 不得新增 compatibility wrapper 或 public re-export | ✅ | `__all__` 未变；无 wrapper 或 re-export |
| 不得改变错误文本 | ✅ | `RuntimeError` 消息逐字节一致："accepted compaction is missing successful response identity" 和 "accepted compaction is missing proposal manifest reference" |
| 不得改变错误类型 | ✅ | 两处均为 `RuntimeError`，未变为自定义异常 |

### Semantic Ownership Assessment

**修复前状态**：`dispatch._required_compactor_manifest_reference` 和 `engine_ingest._required_compactor_manifest_reference` 是两个内容完全相同的 local helper；`_required_successful_response_identity` 同理。两者从同一个 `CompactionOperationResult` optional field 产生相同 RuntimeError semantic。proactive 和 reactive caller 各自维护独立的校验与错误文本，同一 accepted-result presence invariant 存在两个 owner。

**修复后状态**：`CompactionOperationResult` 作为两个 optional field 的 typed owner，统一提供 `required_successful_response_identity()` 和 `required_proposal_manifest_reference()` 两个 accessor。proactive（dispatch.py:2551,2554）和 reactive（engine_ingest.py:3121,3124）caller 均机械调用 owner accessor，不再维护各自的 local helper。

**评估**：修复正确收口了 PR-A01 的 semantic ownership drift。owner 边界清晰，caller 只做机械消费，未引入新的 abstraction、wrapper 或泛化层。

### Scope Creep 检查

| 检查项 | 结果 |
|---|---|
| 修改文件是否超出 adjudication 允许的 4 个 | ✅ 仅 4 个文件 |
| 是否有 formatter-only churn | ✅ `git diff --stat` 与 `git diff -w --stat` 一致 |
| 是否引入新的类型、protocol 或 abstraction | ✅ 无 |
| 是否触及非 PR-A01 代码 | ✅ 无 |
| 是否修改 PR body、README、design 文档 | ✅ 无 |

### New Correctness / Security / Maintainability Findings

未发现实质性问题。

具体验证：

1. **异常语义保持**：两个 accessor 的 `RuntimeError` 消息与旧 helper 逐字节一致。`pytest.raises(match=...)` 断言同样逐字节匹配。
2. **typing 保持**：accessor 返回 `SuccessfulRunnerResponseIdentity` 和 `CompactorProposalManifestReference`（非 optional），与旧 helper 签名一致。
3. **CAS 保持**：未触及 `compaction_terminal.py` 或任何事务边界代码。
4. **测试 owner-level**：两个 guard test 均直接断言 `CompactionOperationResult` 实例的 accessor 行为，不依赖 dispatch 或 engine_ingest 模块。`import dayu.host.dispatch as dispatch` 已从 test file 移除。
5. **数据完整性**：两个 accessor 只读取各自 field 并做 None check，未修改 dataclass 状态。

### Codex Fix Artifact Cross-Check

Codex fix artifact 声称的所有验证结果均已独立复现：

- ✅ `git diff --stat HEAD` = `4 files changed, 63 insertions(+), 78 deletions(-)`
- ✅ 四个 local helper definition 和 call 全仓零命中
- ✅ test file 不再 import `dispatch` 模块
- ✅ 两个 new accessor 位于 `CompactionOperationResult` 类体（行 516-546）
- ✅ 旧 helper 删除位置（dispatch.py 原 6254-6289，engine_ingest.py 原 8815-8850）现在是相邻函数的自然尾部

### Validation Assessment

| 维度 | 评估 |
|---|---|
| Tests | Codex artifact 报告 33 passed（owner file）、283 passed（coverage session）。独立验证确认 test 结构正确；未能独立运行 pytest（re-review scope 限制） |
| Coverage | Codex artifact 报告 compaction_operation 86%、dispatch 84%、engine_ingest 85%。owner accessor 是 trivial None check，已被两个 guard test 覆盖 |
| Pyright | Codex artifact 报告 0 errors。accessor 签名返回非-optional 类型，typing 一致 |
| Diff/scope | 独立确认：4 文件、无 formatter churn、无 scope creep |
| Security | 无 credential/API key 添加；accessor 不涉及敏感数据 |

## Finding Status

| Finding | Status | 说明 |
|---|---|---|
| PR-A01 | ✅ **已修复** | 两个 accepted-result presence invariant 由 `CompactionOperationResult` 唯一拥有；四个重复 local helper 已完全移除 |

## Residual Risks

1. **Phase 5 integration baseline failures**（6 个）：`assigned to later work unit`。已有 S5 clean-base 与 S6 artifacts 跟踪，不由 PR-A01 owner fix 处理。
2. **五个 affected-file F401**（`dispatch.py` 4 个 context-budget import、`engine_ingest.py` 1 个 run-input import）：`assigned to repository hygiene / later work unit`。HEAD 可复现，本 fix 未新增或扩散。
3. **G01–G07 calibration、formal interactive scenarios、renderer target closure**：`assigned to later work unit`，沿用 PR adjudication 分类。
4. **GitHub 没有 reported checks**：外部 validation gap 保持不变。

## PASS/FAIL Verdict

**PASS。** PR-A01 修复正确：`CompactionOperationResult` 唯一拥有两个 accepted-result presence invariant，四个 local helper 完全移除，异常/typing/schema/CAS/behavior 均保持不变，测试为 owner-level，无 scope creep，无新 finding。Codex fix artifact 的所有声明均可独立复现。

## Next Gate

按 adjudication 流程，MiMo re-review 通过。下一 gate：AgentDS 独立 re-review 通过后，可进入 final push 或 draft-PR-pass。
