# UF-FIX11 S3 Implementation Re-Review — DS 第二路定向复核

- reviewer：DS（第二路严格独立 adversarial review）
- 时间：2026-08-17
- review target：
  - `docs/gateflow/uf-fix11-s3-implementation-review-fix-20260817.md`（controller review-fix）
  - 修复后完整工作树 diff
  - 本路原 review artifact：`docs/reviews/uf-fix11-s3-implementation-review-ds-20260817.md`
- 独立声明：本复核未读取 MiMo 路 re-review artifact，所有结论仅基于上述文档与代码/测试直接证据独立得出。
- scope：只读。未修改任何既有文件；未 stage/commit。只新增本 artifact。

## 1. 复核目标

按 controller 裁决，逐项验证 DS `F-01`/`F-02`/`F-03` 是否以直接代码/测试证据关闭；特别核查：

1. F-02 的 CLI 用例是否确实经过 production command loop，而非 renderer 直调；
2. F-03 的 runner fake 与 `cast` 的严格类型与 owner seam 是否合理；
3. F-03 对 `to_json_summary` 的声明是否被错误夸大为 repository save/re-read；
4. 修复是否新增回归、越出 allowed boundary 或引入新的生产抽象。

## 2. 逐项 closeout 验证

### F-01（docstring 漂移）— 已关闭 ✓

- diff 证据：`dayu/service/fins_wait_adapter.py` 本轮相对上一轮只新增 `:returns:` 一段
  （"completed value 恒包含 ``warnings`` 数组，非 upload 自然为空 ``[]``；download 使用 nested 自解释对象，
  其它 operation 保持业务 details"），函数签名、函数体与运行时行为零变化。✓
- 契约一致性：docstring 现在与 `_completed_result_value` 中无条件
  `"warnings": company_metadata_warnings_to_json(result.warnings)` 表达同一 completed contract。✓
- 既有测试持续覆盖 upload warning exact JSON 与 non-upload `[]`
  （`test_fins_wait_poll_adapter_maps_observation_statuses`、
  `test_fins_wait_adapter_projects_completed_warning_exactly`）。✓

### F-02（命令循环组合测试缺口）— 已关闭 ✓

新增 `test_upload_filing_command_loop_preserves_summary_and_routes_warning`（参数化 `ok`/`skipped`）：

- **确实经过 production command loop**：测试调用 `cli_main.main(_live_command_argv("upload_filing", tmp_path))`，
  其中 `_live_command_argv`（`test_fins_commands.py:3820-3851`）构造真实 CLI argv 并在 tmp_path 写入真实文件；
  `fake_service` fixture（`586-608`）通过 monkeypatch 替换生产模块的 `FINS_DIRECT_SERVICE_FACTORY`，
  dispatch → `dayu/cli/commands/fins.py` 命令循环 → production stream consumer → `render_fins_direct_event`
  全部为生产代码路径，没有直调 renderer 或绕过 stream consumer。✓
- **断言强度**：
  - 命令返回 `EXIT_SUCCESS`（真实命令循环返回码，非事件字段）；
  - stdout **精确等于**生产两行：`Fins succeeded:` 与 `Fins summary:`——我已核对生产常量
    `_FINS_EVENT_SUCCEEDED_PREFIX`/`_FINS_EVENT_SUMMARY_PREFIX`（`dayu/cli/output.py:61/64`）与
    `_print_result_details` 格式，与断言逐字符一致；
  - stderr 精确等于一行 canonical `COMPANY_NAME_IGNORED_WARNING_MESSAGE`；
  - fake service 断言 `stream_calls == [UPLOAD_FILING]`、恰一次 upload request、恰一次 stream close。✓
- fix 文档对首次运行把前缀误写为 `Fins result:`、经实际输出修正为 `Fins summary:` 的披露诚实；
  最终断言以生产常量为基准，不存在把测试夹具文案固化进生产的行为。✓

### F-03（runner 复合链缺口）— 已关闭（按 controller 限定边界）✓

新增 `test_production_upload_runner_preserves_pipeline_warning_in_summary_and_json`
（`tests/fins/test_fins_service_runtime.py:563-657`）：

- **真实链覆盖**：`prevalidate_fins_upload_filing_request_for_workspace` 产出真实
  `ValidatedFinsUploadFilingRequest`；真实 `ProductionFinsUploadRunner.run_upload` →
  `_run_filing_upload` → `FinsUploadPipelineResult.from_pipeline_json(..., source_kind=SourceKind.FILING)`
  （production parser）→ `_upload_summary_from_result`（production 汇合点）→ typed
  `FinsUploadResultSummary`。fake facade 只替换 runner 的 pipeline 边界，返回合法
  `SecPipelineUploadResult`（typed JSON dict），production parser 是真实恢复 warning 的一环。✓
- **runner fake/cast 与 owner seam 合理性**：`cast(SecPipeline, pipeline)`/`cast(CnPipeline, pipeline)`
  是测试替身的静态类型收敛手段，与同文件既有 fixture（`cast(fins_command.FinsDirectCommandService, service)`）
  及 `test_fins_direct_stream.py` 负例 `cast` 先例一致；运行时契约未被 cast 掩盖——runner 真实调用
  `pipeline.upload_filing(...)`，facade 以 identity 断言证明收到**同一个** validated request 与**同一个**
  cancellation checker（`pipeline.requests == [request]`、`pipeline.cancellation_checkers == [checker]`）。
  任何 runner handoff 契约漂移都会让 facade 以 AttributeError/TypeError 或 identity 断言失败显式变红，
  不会静默绿。pyright `0 errors` 确认无类型错误扩散。seam 位置（runner↔pipeline 边界）恰是 F-03 目标链
  的起点，属合理最小替身。✓
- **`to_json_summary` 声明精度（重点核查，无夸大）**：fix 文档原话为
  "`summary.to_json_summary()["warnings"]` 等于 canonical warning JSON，**直接覆盖 durable serializer**"。
  该测试断言的确只覆盖 canonical durable serializer 的输出；repository save/re-read round-trip 由既有
  `test_accepted_upload_terminal_store_rejects_mismatch_and_preserves_existing_...`（真实 job store，断言
  `saved.result_summary["warnings"] == [...]` 且 `runtime.read_job(...) == saved`）覆盖。fix 文档没有把
  新测试宣称为 repository save/re-read 测试，边界声明与代码事实一致，不存在需要拒绝的错误夸大。✓
- **controller 限定边界的执行**：fix 未复制 ingestion private execution context 把同一 summary 注入 direct
  builder，summary→direct 的同值复制继续由既有 `test_direct_upload_stream_copies_typed_warnings_exactly`
  独立关闭；未新增生产抽象、fallback 或兼容分支。该边界选择是 controller 明确裁决，属 accepted residual
  而非缺口。✓

## 3. 回归与边界核查

- **生产 diff 未因修复改变**：`dayu/fins/ingestion_runtime.py`、`direct_events.py`、`service_runtime.py`、
  `dayu/cli/output.py` 四处相对上一轮零变化（36 changed lines 与上一轮一致）；唯一生产改动为
  `fins_wait_adapter.py` docstring。✓
- **allowed boundary**：`git diff --name-only` 仍严格等于 S3 allowed files（5 生产 + 6 测试 + 3 README）；
  无新增越界文件。✓
- **冻结符号**：`_observation_failure_result`/`_observation_cancelled_result`/`_mark_observation_failed`
  diff 命中数为 0；Host/Engine/warning codec/pipeline/storage/oracle/scenario/registry 零 diff。✓
- **独立重跑**：
  - S3 focused：`546 passed, 3 warnings`（与 fix 文档一致）；
  - combined regression：`2155 passed, 1 skipped, 3 warnings`（与 fix 文档一致，2152+3 个新增用例算术自洽）；
  - pyright：`0 errors, 0 warnings, 0 informations`；
  - `git diff --check`：通过；cached diff 为空，未 stage/commit。✓
- **README**：fix 未触碰 README；`tests/README.md` 既有 S3 focused 矩阵已包含两个新增测试所在文件，
  无需更新，结论成立。✓

## 4. Findings

无新增 finding。

三个原 findings 均以直接代码/测试证据关闭，且关闭方式与 controller 裁决边界一致；修复过程中发现的
唯一问题（CLI 测试初始前缀写错）已在 fix 文档中如实披露，并以生产常量为最终断言基准，不构成伪造
通过或行为固化。

## 5. Open questions

- 无新增 blocking open question。

## 6. Residual risks and suggested tracking destination

- R-1（accepted tradeoff，维持）：completed wait 对所有 operation 显式 `warnings` 数组（非 upload 为 `[]`）。
- R-2（accepted boundary，维持）：无单测试贯穿 production runner 到 direct runtime assembly；
  controller 明确允许，summary→direct 机械复制由既有 owner test 独立覆盖。若未来 runner/direct assembly
  结构变化，建议后续 work unit 重新评估是否建立更重的跨 boundary fixture。
- R-3（既有 later-work-unit residuals，未触碰）：name-only metadata batch writer lock/physical swap、
  material upload 类似行为、真实 CLI/network/scenario/oracle/frozen evidence、post-commit cleanup 可见性，
  owner/destination 不变。
- 未分类 residual risk：无。

## 7. Final conclusion

**PASS**

F-01/F-02/F-03 全部以直接代码/测试证据关闭：

- F-02 的 CLI 用例确经 `cli_main.main` 真实 dispatch 与 production command loop，断言真实返回码、精确
  双流输出与 stream 生命周期；
- F-03 的 runner fake/cast 属同文件既有测试替身先例，运行时契约经 identity 断言真实行使，seam 位于
  runner↔pipeline 边界（F-03 目标链起点），合理且防漂移；
- `to_json_summary` 声明精确限定为 durable serializer，repository save/re-read 由既有真实 job store
  测试独立覆盖，无夸大；
- 无新增回归（focused 546 / combined 2155 / pyright 0 / diff-check 均独立复现），无越界文件，无新生产
  抽象，未 stage/commit。

下一步入口由 controller 决定：S3 implementation acceptance 或直接进入下一 gate。
