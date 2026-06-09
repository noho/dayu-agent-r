# WU-TOOLS-01-F01-03 PR Review Re-Review — AgentDS

## Scope

- **Mode**: current changes（PR review fix re-review）
- **Branch**: `phase/wu-tools-01-f01-03`
- **Output file**: `docs/reviews/wu-tools-01-f01-03-pr-review-rereview-ds.md`
- **Reviewed scope**: 仅 MiMo medium finding — LLM-facing `ToolCancelledOutcome.message` 中的 `"by the host"`
- **Fix artifact**: `docs/reviews/wu-tools-01-f01-03-pr-review-fix-codex.md`

## Verdict

**pass** — finding fixed；0 blocking findings；0 new findings。

---

## 修复验证

### 取消 message 不再包含 host/Host

**Status: fixed**

- **文件**: `dayu/fins/tools/download_tools.py:45`, `preprocess_tools.py:44`, `upload_tools.py:58`
- **验证证据**:
  1. `download_tools.py:45`: `_CANCELLED_MESSAGE: Final[str] = "Fins download start was cancelled."`（原 `"...cancelled by the host."`）
  2. `preprocess_tools.py:44`: `_CANCELLED_MESSAGE: Final[str] = "Fins preprocess start was cancelled."`
  3. `upload_tools.py:58`: `_CANCELLED_MESSAGE: Final[str] = "Fins upload start was cancelled."`
  4. targeted scan: `rg "by the host"` 在三个工具文件中无匹配
  5. 内部 `reason=TOOL_CANCELLED_REASON_HOST_CANCELLED` 保留不改——这是 `dayu.contracts.tool_outcome` 的契约常量，不是 LLM-facing text

### 测试覆盖

**Status: fixed**

- **文件**: `tests/fins/test_fins_ingestion_tools.py:90, 570, 589, 618, 806-821`
- **验证证据**:
  1. `_FORBIDDEN_CANCELLED_MESSAGE_FRAGMENTS = ("host", "Host")` (line 90)
  2. `_assert_cancelled_outcome_hides_host_term(outcome)` (lines 806-821): 拼接 `outcome.message + "\n" + outcome.hint`，对 `("host", "Host")` 执行 `assert fragment not in visible_text`
  3. 三个工具的 cancelled 测试均调用该 assertion（lines 570, 589, 618）
  4. 三个测试同时保留 `assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED`——内部 reason 契约断言不受影响

### 无新增问题

- 无新增 LLM-facing 术语泄漏
- 无 schema/类型/分层问题
- targeted type scan 无匹配

## 验证摘要

| 检查项 | 结果 |
|---|---|
| pytest `tests/fins/test_fins_ingestion_tools.py` | 29 passed, 3 warnings |
| pyright `dayu/ tests/ utils/` | 0 errors |
| git diff --check | passed |
| `"by the host"` in tool files + test | 0 matches |
| `TOOL_CANCELLED_REASON_HOST_CANCELLED` reason 契约 | 保留，测试断言通过 |
