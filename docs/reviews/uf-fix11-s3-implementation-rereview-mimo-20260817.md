# UF-FIX11 S3 Implementation Re-Review

## Re-review metadata

- reviewer: MiMo (independent)
- date: 2026-08-17
- gate: S3 implementation re-review
- branch: `codex/upload-filing-oracle`
- scope: uncommitted diff (14 files, +913/-12)
- inputs:
  - `docs/reviews/uf-fix11-s3-implementation-review-mimo-20260817.md`（原 review）
  - `docs/reviews/uf-fix11-s3-implementation-review-ds-20260817.md`（DS review）
  - `docs/gateflow/uf-fix11-s3-implementation-review-fix-20260817.md`（fix artifact）
  - 修复后完整工作树 diff

## Methodology

- 核对 DS F-01/F-02/F-03 的直接代码/测试证据是否关闭。
- 验证 CLI 用例经过 production command loop。
- 验证 runner fixture 类型/owner 合理。
- 验证 `to_json_summary` 措辞没有把 serializer 冒充 repository save/re-read。
- 检查新回归/越界。
- 重跑最小必要验证：26 passed（F-01/F-02/F-03 专用）；546 passed（S3 focused 全集）。

---

## DS Finding Closeout

### F-01 — docstring drift — CLOSED

**Fix**: `dayu/service/fins_wait_adapter.py` `_completed_result_value` docstring returns 部分从 "download 使用 nested 自解释对象；其它 operation 保持业务 details" 改为 "completed value 恒包含 `warnings` 数组，非 upload 自然为空 `[]`；download 使用 nested 自解释对象，其它 operation 保持业务 details"。

**代码证据**: 函数体 `value` dict 第 583 行 `"warnings": company_metadata_warnings_to_json(result.warnings)`。docstring 现在准确描述了 completed value 恒包含 `warnings` 数组这一事实。

**验证**: 函数签名、函数体、运行时行为零 diff（除 docstring）。既有测试 `test_fins_wait_adapter_projects_completed_warning_exactly` 与 `test_fins_wait_poll_adapter_maps_observation_statuses` 继续通过。

**裁决**: 关闭。docstring 与代码语义一致。

---

### F-02 — CLI command-loop 组合缺口 — CLOSED

**Fix**: `tests/cli/test_fins_commands.py` 新增参数化 `test_upload_filing_command_loop_preserves_summary_and_routes_warning`，覆盖 uploaded（ok/stored=1）与 skipped（skipped/stored=0）。

**代码证据**: 测试通过 `cli_main.main(_live_command_argv("upload_filing", tmp_path))` 进入真实 CLI dispatch，经 `dayu/cli/commands/fins.py` 的 direct command loop。使用 `monkeypatch.setattr(fins_command, "FINS_DIRECT_SERVICE_FACTORY", factory)` 注入 `_FakeFinsDirectService`，该 fake 返回预设的 `FinsEvent`（含 `FinsResultSummary(warnings=(warning,))`）。

**验证命令循环真实性**:
- `_live_command_argv("upload_filing", tmp_path)` 构造真实 argv：`["upload_filing", "--ticker", "AAPL", "--action", "create", "--fiscal-year", "2024", "--fiscal-period", "FY", "--files", ...]`
- `cli_main.main(...)` 走真实 CLI dispatch → `fins_command` → `_FakeFinsDirectService.stream_upload_filing(...)` → 命令循环消费事件 → `render_fins_direct_event` → stdout/stderr
- 测试断言 `fake_service.stream_calls == [FinsOperationKind.UPLOAD_FILING]` 与 `fake_service.closed_streams == 1`，证明命令循环正确打开了 stream 并关闭

**断言精确性**:
- `exit_code == EXIT_SUCCESS`（0）
- `captured.out` 精确匹配两行：`Fins succeeded: ...` 与 `Fins summary: ...`，包含 `status="ok"` 或 `status="skipped"` 与对应 requested/stored 计数
- `captured.err` 精确等于一行 canonical `COMPANY_NAME_IGNORED_WARNING_MESSAGE`

**裁决**: 关闭。测试经过真实 production command loop，不绕过 renderer 或 stream consumer。

---

### F-03 — production runner handoff 复合链缺口 — CLOSED

**Fix**: `tests/fins/test_fins_service_runtime.py` 新增 `test_production_upload_runner_preserves_pipeline_warning_in_summary_and_json`。

**代码证据**: 测试使用真实 `ProductionFinsUploadRunner.run_upload`，注入最小 `_WarningFilingPipelineFacade`。facade 的 `upload_filing` 方法返回 dict `{"status": "skipped", "stored_file_count": 0, "warnings": [warning.to_json()]}`，这正是 `SecPipelineUploadResult` 的 production shape。

**production chain 验证**:
1. `_WarningFilingPipelineFacade.upload_filing()` 返回 canonical pipeline terminal JSON
2. `ProductionFinsUploadRunner._run_filing_upload()` 调用 `FinsUploadPipelineResult.from_pipeline_json(pipeline_result, source_kind=SourceKind.FILING)` — 这是 production parser
3. `FinsUploadPipelineResult.__post_init__` 校验 warning invariant（exact type, at-most-one, ok/skipped-only）
4. `ProductionFinsUploadRunner.run_upload()` 调用 `_upload_summary_from_result(request, result)` — 这是 service 汇合点
5. `_upload_summary_from_result` 显式复制 `result.warnings`（`service_runtime.py:323`）

**断言**:
- `pipeline.requests == [request]` — runner 正确传递 request
- `pipeline.cancellation_checkers == [cancellation_checker]` — runner 正确传递 cancellation checker
- `summary.status == "skipped"` — pipeline result 正确解析
- `summary.warnings == (warning,)` — typed warning 从 pipeline JSON → parser → runner → summary 完整保留
- `summary.to_json_summary()["warnings"] == [warning.to_json()]` — durable serializer 输出正确

**关于 `to_json_summary` 措辞**: fix artifact 说 "直接覆盖 durable serializer"。这是准确的：`to_json_summary()` 是 `FinsUploadResultSummary` 的序列化方法，产出 durable JSON shape。测试调用它验证 serializer 输出正确。真正的 repository save/re-read 由既有 `test_accepted_upload_terminal_store_rejects_mismatch_and_preserves_existing_fields` 覆盖（该测试通过 `FinsIngestionJobStore` 保存并重读 job record）。两者测试不同边界：serializer shape vs. 持久化 round-trip。fix artifact 没有把 serializer 冒充 repository。

**边界裁决**: fix artifact 明确说明没有继续复制 ingestion private execution context 来把 runner summary 注入 direct builder，因为那会耦合到 S3 direct symbol 之外的 runtime assembly。`summary → direct` 的机械复制由既有 `test_direct_upload_stream_copies_typed_warnings_exactly` 独立覆盖。这是 controller 认可的边界选择。

**裁决**: 关闭。真实 production pipeline JSON → typed parser → production runner → runtime summary → durable serializer 链完整覆盖。

---

## 回归与越界检查

### 新增 diff 范围

对比原 review（14 files, +666/-11）与当前（14 files, +913/-12）：

- `dayu/service/fins_wait_adapter.py`：+3/-1（docstring 修正 + import 行调整）
- `tests/cli/test_fins_commands.py`：+124/-0（新增 F-02 command-loop 测试 + 原有 renderer 测试增加 `expected_other_stream` 参数）
- `tests/fins/test_fins_service_runtime.py`：+216/-0（新增 F-03 runner 测试 + `_WarningFilingPipelineFacade` / `_NeverCancelledChecker` fixtures + `_upload_summary_from_result` warning copy 测试）

**无新增 production 行为**：唯一 production diff 是 `fins_wait_adapter.py` 的 docstring 文本变更，不影响运行时行为。

**无越界文件**：仍为原 14 个 allowed files。Host/Engine/material/oracle/scenario/registry/frozen boundary 零侵入。

**observation helpers 零 diff**：`_observation_failure_result`、`_observation_cancelled_result`、`_mark_observation_failed` 无变更。

### 测试结果

- 最小 review-fix tests：26 passed, 3 warnings
- S3 focused 全集：546 passed, 3 warnings（原 543 + 新增 3）
- pyright：0 errors（`dayu/service/fins_wait_adapter.py` 单独验证通过）

### Fixture owner 合理性

- `_FakeFinsDirectService`：CLI 测试的标准 direct service 替身，monkeypatch 注入 `FINS_DIRECT_SERVICE_FACTORY`。fake 返回预设 `FinsEvent`，命令循环消费事件并走真实 renderer。不绕过 production stream consumer。
- `_WarningFilingPipelineFacade`：最小 pipeline facade，返回 canonical terminal JSON（dict）。由 `FinsUploadPipelineResult.from_pipeline_json` 生产 parser 解析。fake 只替代 pipeline 层，不替代 parser/runner/summary。
- `_NeverCancelledChecker`：标准 cancellation checker 替身，始终返回未取消。与既有 `_AlwaysCancelledChecker` 对称。

三者都是 owner 边界内的合理 test double：fake 替代的是 pipeline/service 层，不替代 parser/runner/summary/serializer 等 production 组件。

---

## Residual risks

### 不变

- 既有 later-work-unit residuals（name-only metadata batch writer lock/physical swap、material upload 类似行为、真实 CLI/network/scenario/oracle/frozen evidence、post-commit cleanup 可见性）均未触碰。
- 没有新增单测试贯穿 production runner 到 direct runtime assembly — 这是 controller 认可的边界选择。

### 未分类 residual risk

无。

---

## Verdict

**PASS**

DS F-01/F-02/F-03 均以直接代码/测试证据关闭：

- F-01：docstring 与代码语义一致。
- F-02：CLI 测试经过真实 `cli_main.main()` → command loop → renderer，不绕过 production stream consumer。
- F-03：真实 `ProductionFinsUploadRunner.run_upload` 覆盖 pipeline JSON → parser → runner → summary → durable serializer 链；`to_json_summary` 措辞准确区分了 serializer 与 repository save/re-read。

无新回归、无越界。S3 focused 546 passed，pyright clean。实现就绪。
