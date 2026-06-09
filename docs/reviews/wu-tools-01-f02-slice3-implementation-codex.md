# WU-TOOLS-01-F02 Slice 3 实现记录 - Codex

## 修改文件

- `tests/tools/web/test_diagnose_web_access.py`
  - 新增 deterministic focused tests，覆盖 JSONL/TXT corpus 解析、元数据保留、去重、非法 JSONL 报错、storage-state host 路径解析、comparison bucket matrix、batch row/summary 统计、current `ToolDefinition.callable` 成功/失败 outcome 投影、CLI single/batch helper 写盘行为，以及 OLD Web/UI forbidden import guard。
- `utils/diagnose_web_access.py`
  - 在 `ToolFailedOutcome` 诊断 profile 中补充 `next_action`、`http_status` 与 `diagnostics` 字段。
  - `next_action` 从 current Web 工具 hint 的 `[action]` 前缀恢复；`http_status` 明确为 `None`；`diagnostics` 明确说明 current outcome 只暴露 error/message/hint，Web 工具内部 `http_status/internal_diagnostics` 不会经过 current adapter 进入 outcome。
- `docs/reviews/wu-tools-01-f02-slice3-implementation-codex.md`
  - 本实现记录。

## README 决策

未更新 `tests/README.md`。

原因：已先阅读该 README。其现有 `tests/tools/web/` 约束已经明确 Web provider tests 必须 deterministic，并通过 monkeypatch / fixture 控制搜索 provider、requests 主路径与 Playwright fallback，不做 live network 请求。本 Slice 只在既有 `tests/tools/web/` 层级下新增 focused deterministic test，没有新增测试层级、运行方式或维护规则。

## diagnose_web_access.py 修改说明

已修改 `utils/diagnose_web_access.py`。

root cause 证据：

- `dayu.tools.web.web_tools.ToolBusinessError` 会把 `next_action`、可选 `http_status` 与 `internal_diagnostics` 放入 `extra`。
- current adapter `dayu.tools._legacy_adapter.definition_adapter.project_legacy_exception(...)` 在投影 `ToolBusinessError` 时只保留 `code/message/hint`，没有把 `extra` 投影到 `ToolFailedOutcome`。
- 诊断脚本原先只输出 `error_code/error/message/hint`，导致 current fetch 失败 profile 缺少 plan 要求的业务可读 diagnostic 字段，也没有说明 `http_status/internal_diagnostics` 缺失是 current contract 边界而不是站点事实。

最小修正：

- 不改 Host / Engine / ToolRuntime / Web production contract。
- 不恢复 OLD registry、truncation、fetch_more、`dayu.web` 或 UI 路径。
- 只在 opt-in diagnostics artifact 中，从 hint 前缀恢复 `next_action`，并用 `diagnostics` 说明 current outcome 可见字段边界。

## 验证结果

- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q`
  - 通过：`23 passed in 0.35s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：`0 errors, 0 warnings, 0 informations`
- `bash -n utils/diag_web.sh utils/diag_web_batch.sh`
  - 通过
- `git diff --check`
  - 通过
- Targeted forbidden import/type scan for `utils/diagnose_web_access.py`
  - 通过：没有 OLD registry/truncation/fetch_more/`dayu.web`/UI imports，也没有 `Any`/`object` type-name hits。

## 剩余风险

- Deterministic tests intentionally do not prove live network, real browser installation, real storage-state cookies, anti-bot challenge behavior, or provider/API availability.
- Current `ToolFailedOutcome` still cannot expose Web `ToolBusinessError.extra` fields through the current adapter contract; this Slice only makes the diagnostics artifact explicit about that boundary and recovers `next_action` when it is present in hint.
