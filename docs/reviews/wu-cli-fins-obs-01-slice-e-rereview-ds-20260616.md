# WU-CLI-FINS-OBS-01 Slice E Re-review (AgentDS)

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: E, README / design-adjacent docs / tests synchronization
- Gate: re-review (review fix)
- Reviewer: AgentDS
- Date: 2026-06-16
- Review artifact: `docs/reviews/wu-cli-fins-obs-01-slice-e-review-ds-20260616.md`
- Review fix artifact: `docs/reviews/wu-cli-fins-obs-01-slice-e-review-fix-codex.md`

## Scope

只审查 fix 对应的增量：`dayu/fins/README.md` 的 "调用者装配示例" → "Download / preprocess / upload caller" 节的代码示例改造。不接受新的全量审查。

## Fix 内容核对

### DS-E01 fix verified

**旧状态（DS-E01 finding）：** `dayu/fins/README.md` L231-254 的代码示例只展示 legacy `ingestion.start_download(...)` / `ingestion.start_preprocess(...)` / `ingestion.start_upload(...)` 调用，与 L143-145 声明的 stable entry `download(...) -> AsyncIterator[FinsEvent]` 不一致。

**新状态：** caller 示例已重构为三个明确分层：

1. **Direct stream 优先（L213-268）**：`async for event in ingestion.download(...)` / `ingestion.preprocess(...)` / `ingestion.upload(...)`，使用 `FinsEventType.RESULT` 判断终态。展示了正确的 async consumption 模式。导入 `from dayu.fins.direct_events import FinsEventType`，路径有效（`python -c "from dayu.fins.direct_events import FinsEventType"` 通过）。✅

2. **Observation handle 流程草图（L271-278）**：`start_fins_download/preprocess/upload → start_observed_* → ToolAwaitingOutcome(EXTERNAL_JOB) → poll observation snapshot`。正确表达了 tool awaiting provider 的 observation handle 路径，不与 CLI direct stream 混淆。✅

3. **Legacy job-store helpers（L280-289）**：单行示例 `ingestion.start_download(...)`，明确标注 "Legacy job-store helpers 仍可由低层测试或明确选择 legacy job-store 的内部路径调用"。不再作为前两个路径的替代方案。✅

### 术语更新核对

| 位置 | 旧术语 | 新术语 | 一致 |
|---|---|---|---|
| L291 | "download job 会进入明确 failed 终态" | "download stream 会进入明确 failed RESULT" | ✅ |
| L291 | "upload job 仍会进入明确的 failed 终态" (removed elsewhere) | "upload stream 产出 unsupported upload runtime 的 failed RESULT" | ✅ |

### 误导性描述检查（fix 增量范围）

- 新 direct stream 示例不提及 `job_id`、`request_cancel`、sidecar、terminal fallback、durable job record。✅
- Observation handle 流程草图使用 `start_observed_*`、`ToolAwaitingOutcome(EXTERNAL_JOB)`、`poll` — 全部是 current lightweight observation 术语。✅
- Legacy 示例显式标注 "Legacy job-store helpers"，且限定为 "低层测试或明确选择 legacy job-store 的内部路径"。✅
- 无 future plan 表述。✅

## 验证复现

```text
pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py
  tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py
  tests/service/test_host_assembly.py tests/cli/test_upload_filings_from_command.py
  tests/cli/test_init_command.py tests/cli/test_prompt_command.py
  tests/cli/test_interactive_command.py tests/cli/test_arg_parsing.py -q
→ 281 passed, 3 warnings

pyright dayu/ tests/ utils/
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ clean
```

所有数值与 fix report 一致，三个 warning 仍为 edgartools 第三方 DeprecationWarning。

## 裁决

**结论：PASS。**

DS-E01 已修复。`dayu/fins/README.md` 的 caller 示例现在：
- 优先展示 direct stream `async for event in ingestion.download/preprocess/upload(...)`，与 declared stable entry 一致；
- 单独描绘 observation handle 流程，不与 CLI direct 混淆；
- Legacy job-store helpers 显式标注、限制范围。

阻断发现：**0 blocking findings**。
