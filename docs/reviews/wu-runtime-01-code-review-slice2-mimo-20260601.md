# WU-RUNTIME-01 Slice 2 Code Review

**Reviewer**: AgentMiMo
**Date**: 2026-06-01
**Review target**: Workspace diff relative to HEAD (Slice 2)
**Implementation artifact**: `docs/reviews/wu-runtime-01-implementation-slice2-codex-20260601.md`
**Accepted plan**: `docs/host/wu-runtime-01-filelock-contraction-plan.md`

---

## Conclusion

**pass-with-fixes**

Slice 2 实现了 plan 要求的核心目标：在 Host audit/tool trace 测试中覆盖 explicit `lock_path` 的调用面，证明 runtime contract 收缩不破坏生产调用路径。测试通过，pyright 通过，断言最小且稳定。

存在一个 non-blocking finding：AGENTS.md 和 CLAUDE.md 的 scope 外变更未在 implementation artifact 中报告。

---

## Findings

### F1: Scope creep — AGENTS.md / CLAUDE.md 修改 (non-blocking)

**Severity**: informational
**Evidence**: `git diff HEAD --stat` 显示 AGENTS.md 和 CLAUDE.md 各增加一行："不做过度设计，以最小化满足需求为标准。"
**Risk**: 低。该约束是合理的架构指导，但不在 Slice 2 plan 的 allowed files 中。
**Required fix**: Implementation artifact 应报告这两个文件的变更，即使它们与 Slice 2 核心目标无关。
**Blocking**: no

### F2: Implementation artifact 报告不完整 (non-blocking)

**Severity**: informational
**Evidence**: Artifact "Changed Files" 部分只列出 3 个文件，但 `git diff HEAD --stat` 显示 5 个文件被修改（包括 AGENTS.md 和 CLAUDE.md）。
**Risk**: 低。不影响代码质量，但影响 review 可追溯性。
**Required fix**: 更新 artifact 的 "Changed Files" 部分，包含所有被修改的文件。
**Blocking**: no

---

## Checklist Pass/Fail

| 检查项 | 结果 | 说明 |
|--------|------|------|
| 只改 tests 和 artifact，未改 Host production source | **pass** | `dayu/host/audit.py` 和 `dayu/host/tool_trace.py` 未被修改 |
| 覆盖 explicit lock_path 的 audit JSONL append 调用面 | **pass** | `test_jsonl_line_contains_required_audit_fields` 使用 `lock_path=lock_path` |
| 覆盖 explicit lock_path 的 tool trace cold JSONL append 调用面 | **pass** | `test_tool_call_chain_projects_hot_rows_and_cold_lines` 使用 `lock_path=lock_path` |
| 没有导入第三方 filelock | **pass** | 两个测试文件均无 `import filelock` |
| 没有读取 token 状态 | **pass** | 无 `token.released` 或类似断言 |
| 没有 mock runtime internals | **pass** | 无 `unittest.mock` 或 `_active_token` 相关操作 |
| lock marker exists 断言证明 runtime marker restore | **pass** | `assert lock_path.exists()` 直接验证 marker 文件 |
| checkpoint 断言复用现有测试事实 | **pass** | `checkpoint.checkpoint_event_sequence == preview_event.event_sequence` 使用已有 checkpoint 机制 |
| 没有过度设计或测试膨胀 | **pass** | 只在现有测试中增加参数和断言，未新增测试函数 |
| README 不更新决策合理 | **pass** | `tests/README.md` 未提及 `released` / `_active_token`，无需更新 |

---

## Overdesign Check

无过度设计。变更范围最小化：
- `_run_audit_once` 和 `_run_trace_once` 增加 `lock_path` keyword-only 参数
- 两个核心测试使用 explicit `lock_path` 并断言 marker 存在
- 增加 checkpoint 断言以验证 projection 推进
- 未引入新的测试函数、fixture 或抽象层

---

## Residual Risk

- **Lock marker 不是 Host durable truth**: `lock_path.exists()` 只证明 runtime marker restore 工作，不代表 Host 状态机正确性。这是 plan 中已接受的 residual risk。
- **AGENTS.md / CLAUDE.md scope 外变更**: 架构约束变更是合理的，但应在 implementation artifact 中明确报告。

---

## Validation

- `source .venv/bin/activate && pytest tests/host/test_audit_sink.py tests/host/test_tool_trace_projection.py -q`: **pass** (13 passed in 0.31s)
- `source .venv/bin/activate && pyright`: **pass** (0 errors, 0 warnings, 0 informations)
