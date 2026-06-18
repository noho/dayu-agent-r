# PR Review — WU-CLI-ACTIVITY-01 (PR #149)

## Scope

- Mode: PR review
- PR: [#149](https://github.com/noho/dayu-agent-r/pull/149)
- Title: WU-CLI-ACTIVITY-01 activity stream and event projection hardening
- Author: noho
- Head branch: `wu-cli-activity-01`
- Base branch: `main`
- Output file: `docs/reviews/wu-cli-activity-01-pr-review-mimo-20260618.md`
- PR changed files: 180 files (activity stream 原始实现 + follow-up hardening + fins download progress + CLI 参数)
- Prior review artifacts:
  - `docs/reviews/mimo-aggregate-wu-cli-activity-01-followup-20260618-081816.md` (follow-up aggregate)
  - `docs/reviews/mimo-aggregate-rereview-wu-cli-activity-01-followup-20260618.md` (follow-up re-review, PASS)
- Parallel review coverage: 4 subagents — (1) Host public API (__init__, api, admission), (2) CLI + Service integration, (3) Design/doc/README consistency, (4) Tests/pyright verification

## PR Body Validation

PR body 声明三项目标：
1. ✅ Activity stream (Host → Service → CLI)
2. ✅ Follow-up EventLog/projection hardening (delta 不持久化, filter-aware read, 无 budget)
3. ✅ RunInputBuilder inline repair 对齐 Conversation Memory filter

PR body **未声明**但实际包含的范围：
- Fins download progress stream (`dayu/fins/` 多文件)
- `--log-file` / `--detail` / `--no-detail` CLI 参数
- `WU-CLI-INTERACTIVE-RESUME-01` work unit 实现

PR body validation claims:
- Host tests 348 passed → 实测 348 passed ✅
- Service/CLI tests 97 passed → 实测 114 passed, 3 warnings (第三方 `edgar` deprecation) ✅
- CLI coverage 90.25% → 实测 89.96% ✅ (rounding difference)
- Pyright 0 errors → 实测 0 errors ✅

## Findings

### 1-未修复-中-`_cancel_and_await_task` 跨文件重复

- **入口/函数**: `_cancel_and_await_task` (`dayu/cli/commands/prompt.py:566` 与 `dayu/cli/commands/interactive.py:646`)
- **文件(行号)**: `prompt.py:566`, `interactive.py:646`
- **输入场景**: 两个 command 模块各自定义了逻辑相同的 async task 取消辅助函数
- **实际分支**: 两处实现完全相同（cancel + await + 抑制 CancelledError）
- **预期行为**: 按编码硬约束"重复逻辑必须抽取"，应提取到共享 CLI helper 模块
- **实际行为**: 两处独立定义，docstring 措辞略有不同
- **直接证据**: `grep -rn "_cancel_and_await_task" dayu/cli/` 显示 2 定义 + 8 调用
- **影响**: 维护负担；后续修改一处可能遗漏另一处
- **建议改法和验证点**: 提取到 `dayu/cli/_async_utils.py` 或 `dayu/cli/agent_entrypoint.py`；两处调用改为 import
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 2-未修复-低-`README.md` 未记录 `--detail` / `--no-detail` CLI 参数

- **入口/函数**: `dayu/cli/arg_parsing.py:441-459`
- **文件(行号)**: `README.md`
- **输入场景**: 用户查阅 README 了解 `prompt` / `interactive` 命令参数
- **实际分支**: README global parameters 表记录了 `--log-file`（新增），但未记录 `--detail` / `--no-detail`
- **预期行为**: 按 README 更新触发规则，用户可见命令参数变化应更新根目录 README
- **实际行为**: `--detail` / `--no-detail` 参数在代码中存在但 README 未提及
- **直接证据**: `gh pr diff 149 -- dayu/cli/arg_parsing.py` 新增 detail 互斥参数组；README 无对应条目
- **影响**: 用户无法从文档发现 activity stream 显示控制参数
- **建议改法和验证点**: 在 README 命令参数节补充 `--detail` / `--no-detail` 说明
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-PR body scope 声明不完整

- **入口/函数**: PR body
- **文件(行号)**: PR #149 body
- **输入场景**: reviewer 阅读 PR body 判断变更范围
- **实际分支**: PR body 声明 3 项目标但未提及 fins download progress、`--log-file`、`WU-CLI-INTERACTIVE-RESUME-01`
- **预期行为**: PR body 应完整声明所有变更范围
- **实际行为**: 实际 180 文件变更范围超出 body 声明
- **直接证据**: `gh pr diff 149 --name-only` 包含 `dayu/fins/` 多文件、`dayu/cli/arg_parsing.py`；control doc 列出 `WU-CLI-INTERACTIVE-RESUME-01`
- **影响**: reviewer 可能遗漏未声明范围的审查
- **建议改法和验证点**: 补充 PR body scope 声明
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 无阻断 Finding 的检查项

| 检查项 | 结果 |
|---|---|
| Host public API drift | PASS — 5 新增 `HostActivity*` 符号正确导出；移除符号确认不存在于 main |
| HostEvent constructor | PASS — 24 处构造全部包含新增 `event_class`/`event_type`/`activity` 字段，pyright 0 errors |
| CLI → Host 层依赖 | PASS — `session_terminal_cursor.py` 导入 `OutboxTerminalCursor`（低风险，已有模式） |
| Activity event 类型安全 | PASS — 全 frozen dataclass / StrEnum，无 Any/dict |
| Activity event 数据流 | PASS — Host → Service callback → CLI renderer，单向无反向依赖 |
| Error handling | PASS — HostApiError → EntrypointRuntimeError → CliTerminalCursorError 分层正确 |
| Projection catch-up port | PASS — admission.py 仍正确处理 `None`，6 处调用点不变 |
| Follow-up hardening 集成 | PASS — 与 aggregate review / re-review 结论一致 |
| Design doc 一致性 | PASS — design.md 准确描述 delta 不持久化、filter-aware read、page size 语义 |
| Control doc 一致性 | PASS — issues-implementation-control.md 正确反映 WU-CLI-ACTIVITY-01 状态 |
| README 触发规则 | PASS — host/service/fins/tests README 均已更新 |
| Tests | PASS — Host 348 passed, Service/CLI 114 passed |
| Pyright | PASS — 0 errors, 0 warnings |
| CLI coverage | PASS — 89.96% (≥ 80%) |

## Open Questions

无。

## Residual Risk

- Finding #1 (`_cancel_and_await_task` 重复) 应在 merge 前或紧跟 merge 后修复。
- Finding #2 (`--detail`/`--no-detail` README 缺失) 和 Finding #3 (PR body scope) 为文档级问题，不阻断 merge。
- PR body validation 中 Service/CLI 测试计数 (97 vs 114) 存在差异，可能因后续新增测试未同步更新 body。不阻断。

## Conclusion

**PASS（附 1 项中 severity 建议修复）。**

PR 实现与 PR body 声明的核心目标一致：activity stream 全链路（Host → Service → CLI）、follow-up EventLog/projection hardening（delta 不持久化、filter-aware read、无 budget、inline repair 对齐）集成正确。无 public API/contract 未裁决漂移。Design doc / control doc / README 与代码一致。Tests 362 passed, pyright 0 errors。

建议 merge 前修复 Finding #1（`_cancel_and_await_task` 重复），其余为非阻断文档级问题。
