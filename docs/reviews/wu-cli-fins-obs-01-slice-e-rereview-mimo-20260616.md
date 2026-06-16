# WU-CLI-FINS-OBS-01 Slice E Re-Review

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: E re-review
- Reviewer: AgentMiMo
- Date: 2026-06-16
- Fix artifact: `docs/reviews/wu-cli-fins-obs-01-slice-e-review-fix-codex.md`
- Original review: `docs/reviews/wu-cli-fins-obs-01-slice-e-review-mimo-20260616.md`

## DS-E01 Fix Verification

原 review finding DS-E01: `dayu/fins/README.md` caller 示例仍展示 legacy `start_download` / `start_preprocess` / `start_upload` 调用。

Fix 内容（`dayu/fins/README.md` 第 199-289 行）：

1. **Direct stream caller 示例**（第 233-268 行）：展示 `async for event in ingestion.download(...)` / `ingestion.preprocess(...)` / `ingestion.upload(...)` 模式，用 `FinsEventType.RESULT` break 收口。导入来自 `dayu.fins.direct_events` 和 `dayu.fins.ingestion_runtime`。无 job_id、无 sidecar、无 durable job 语义。✅

2. **Observation handle flow**（第 271-278 行）：单独标注 `start_fins_download` / `start_fins_preprocess` / `start_fins_upload` → `start_observed_*` → `ToolAwaitingOutcome(EXTERNAL_JOB)` → `FinsIngestionWaitPollAdapter polls observation snapshot`。✅

3. **Legacy job-store helper**（第 280-289 行）：明确标签 "Legacy job-store helpers 仍可由低层测试或明确选择 legacy job-store 的内部路径调用"，展示 `ingestion.start_download(...)` 示例。✅

## Checklist

| 检查项 | 结果 |
|---|---|
| DS-E01 已修：caller 示例改为 direct async stream | ✅ |
| 无误导为 CLI direct durable job | ✅ direct 示例只用 `AsyncIterator[FinsEvent]` |
| 无 future plan | ✅ 所有示例描述当前代码 |
| observation handle 与 legacy job-store 分区清晰 | ✅ 三段独立标注 |
| 验证命令可信 | ✅ pytest 281 passed, pyright 0 errors, git diff --check clean |

## Conclusion

**PASS**

DS-E01 已修复。caller 示例正确展示 direct stream、observation handle 和 legacy job-store 三类入口，无 blocking findings。
