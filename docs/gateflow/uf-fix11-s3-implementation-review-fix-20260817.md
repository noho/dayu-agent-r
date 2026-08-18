# UF-FIX11 S3 implementation review-fix

## Gate metadata

- work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- gate：`S3 implementation review-fix`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- controller adjudication：关闭 DS `F-01`、`F-02`、`F-03`
- review inputs：
  - `docs/reviews/uf-fix11-s3-implementation-review-ds-20260817.md`
  - `docs/reviews/uf-fix11-s3-implementation-review-mimo-20260817.md`
  - `docs/gateflow/uf-fix11-s3-implementation-20260817.md`
  - `docs/gateflow/uf-fix11-s3-projection-boundary-amendment-20260817.md`
- completion status：`COMPLETE / READY FOR S3 IMPLEMENTATION RE-REVIEW`
- stage / commit / push / PR：均未执行

## 动机、owner 与修复边界

三个 finding 均由直接代码证据支持，但严重性保持为低：F-01 是 completed value 契约的 docstring 漂移；F-02
是命令循环组合测试缺口；F-03 是真实 `ProductionFinsUploadRunner` handoff 的复合回归缺口。三者不要求修改
production 行为，也不构成新增 warning owner。

语义 owner 保持不变：pipeline terminal JSON 由 filing pipeline facade 产生，
`FinsUploadPipelineResult.from_pipeline_json` 校验并恢复 typed warning，`ProductionFinsUploadRunner` 负责调用 pipeline
并把结果汇合为 `FinsUploadResultSummary`；CLI 只消费 direct public result，wait adapter 只序列化 completed result。
因此本轮只修改一个既有 docstring、两个既有 owner/boundary 测试文件和本 artifact，不新增生产抽象、fallback、兼容
分支或行为。

## Finding closeout

### F-01 — 已修复

修复：只修改 `dayu/service/fins_wait_adapter.py` 中 `_completed_result_value` 的中文 docstring。返回值说明现在明确：
completed value 恒包含 `warnings` 数组，非 upload 使用自然空值 `[]`；download 与其它 operation 的既有投影说明保持
不变。函数签名、函数体和运行时行为均未因本 finding 修改。

直接证据：

- docstring 与函数体中的 `company_metadata_warnings_to_json(result.warnings)` 现在表达同一 completed contract；
- `tests/service/test_fins_wait_adapter.py` 既有测试继续分别断言 upload warning exact JSON 与 non-upload `[]`。

### F-02 — 已修复

修复：在 `tests/cli/test_fins_commands.py` 新增参数化
`test_upload_filing_command_loop_preserves_summary_and_routes_warning`，覆盖：

- uploaded：pipeline status 语义为 `ok`，`requested_files=1`、`stored_files=1`；
- skipped：pipeline status 语义为 `skipped`，`requested_files=1`、`stored_files=0`。

两种场景都复用既有 `_FakeFinsDirectService`、`FINS_DIRECT_SERVICE_FACTORY` fixture 与
`_live_command_argv("upload_filing", ...)`，并通过 `cli_main.main(...)` 进入真实 CLI dispatch 和
`dayu/cli/commands/fins.py` 的 direct command loop。测试没有直调 renderer 或绕过 production stream consumer。

直接证据：两种场景均断言：

- 命令返回 `EXIT_SUCCESS`（`0`）；
- stdout 精确保持两行原摘要：`Fins succeeded` 与 `Fins summary`，并保留各自 `ok/skipped`、requested/stored
  计数；
- stderr 精确等于一行 canonical `COMPANY_NAME_IGNORED_WARNING_MESSAGE`；
- fake service 只记录一次 `UPLOAD_FILING` stream、一次 upload request，并被命令循环关闭一次。

### F-03 — 已修复（按 controller 限定边界）

修复：在最贴近 runner owner boundary 的 `tests/fins/test_fins_service_runtime.py` 新增
`test_production_upload_runner_preserves_pipeline_warning_in_summary_and_json`。测试使用真实
`ProductionFinsUploadRunner.run_upload` 与最小 `_WarningFilingPipelineFacade`：fake facade 从一个合法 typed
`CompanyMetadataWarning` 生成 canonical terminal JSON，production parser 恢复 typed pipeline result，真实 runner
再产生 `FinsUploadResultSummary`。

直接证据：测试断言：

- fake facade 收到同一个 validated filing request 与同一个 cancellation checker；
- runner 返回 exact `FinsUploadResultSummary`，status 为 `skipped`；
- summary 的 warning tuple 与输入 typed warning 值完全相同；
- `summary.to_json_summary()["warnings"]` 等于 canonical warning JSON，直接覆盖 durable serializer。

边界裁决：本测试没有继续复制 ingestion private execution context 来把同一个 runner summary 注入 direct builder。
这样做会在 service-runtime owner 测试中重复 `tests/fins/test_fins_ingestion_runtime.py` 已有的私有 context fixture，并把
runner handoff 测试耦合到 accepted S3 direct symbol 之外的 runtime assembly。当前测试关闭真实
pipeline JSON → typed parser → production runner → runtime summary → durable JSON 链；既有
`test_direct_upload_stream_copies_typed_warnings_exactly` 继续独立关闭 summary → direct result 的同值复制契约。

## Changed files

- `dayu/service/fins_wait_adapter.py`：仅 `_completed_result_value` docstring。
- `tests/cli/test_fins_commands.py`：新增 uploaded/skipped mocked command-loop 参数化测试。
- `tests/fins/test_fins_service_runtime.py`：新增真实 production runner 复合链测试及其最小 typed fixtures。
- `docs/gateflow/uf-fix11-s3-implementation-review-fix-20260817.md`：本 review-fix artifact。

共享工作树中既有 S3 production、tests、README 与两路 review artifact 均保留，未覆盖、回退、stage 或 commit。

## Validation

所有命令均在仓库根目录、`source .venv/bin/activate` 后执行。

### 最小 review-fix tests

```text
pytest -q \
  tests/cli/test_fins_commands.py::test_upload_filing_command_loop_preserves_summary_and_routes_warning \
  tests/fins/test_fins_service_runtime.py::test_production_upload_runner_preserves_pipeline_warning_in_summary_and_json \
  tests/service/test_fins_wait_adapter.py
```

最终结果：`26 passed, 3 warnings`。首次运行的两个 CLI 参数场景仅因新增测试把既有 stdout 前缀误写为
`Fins result:` 而失败；实际输出直接证明 production 固定前缀是 `Fins summary:`。只修正测试期望后重跑全绿，未改
production 行为。

### S3 focused

```text
pytest -q \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/fins/test_fins_direct_stream.py \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_wait_adapter.py
```

结果：`546 passed, 3 warnings`。

### Combined regression

```text
pytest -q \
  tests/fins \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_wait_adapter.py
```

结果：`2155 passed, 1 skipped, 3 warnings`。唯一 skip 仍为既有 Docling integration 环境条件；warnings 仍为
已安装 edgar 包的 deprecation warning。

### Branch coverage

```text
coverage erase
coverage run --branch -m pytest \
  tests/fins \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_wait_adapter.py
coverage report -m \
  --include='dayu/fins/ingestion_runtime.py,dayu/fins/service_runtime.py,dayu/fins/direct_events.py,dayu/cli/output.py,dayu/service/fins_wait_adapter.py'
```

结果：同一 regression 为 `2155 passed, 1 skipped, 3 warnings`；逐文件 coverage：

- `dayu/fins/ingestion_runtime.py`：89%
- `dayu/fins/service_runtime.py`：88%
- `dayu/fins/direct_events.py`：83%
- `dayu/cli/output.py`：82%
- `dayu/service/fins_wait_adapter.py`：91%

五个 modified production files 均达到 ≥80% gate。

### Type check 与 static boundary

```text
python -m pyright dayu tests utils
```

结果：`0 errors, 0 warnings, 0 informations`。

- `git diff --check`：通过。
- cached diff：空；未 stage/commit。
- `_observation_failure_result`、`_observation_cancelled_result`、`_mark_observation_failed` diff 命中数：`0`。
- Host、Engine、warning codec、pipeline/storage、oracle、scenario、registry 等冻结或禁止路径 diff 命中数：`0`。
- 未运行真实 CLI、network、calibration、scenario 或 frozen oracle evidence。

## README decision

`tests/README.md` 的现有 S3 focused 矩阵已经包含两个新增测试所在文件，并已说明 company metadata warning 在 CLI
stdout/stderr 与 runtime summary 的覆盖。本轮没有新增测试层级、用户行为或运行命令，且 controller 明确限制为
docstring、必要测试和本 artifact，因此不再修改 README。

## Residual risks 与 uncovered areas

- fixed in current slice：F-01 docstring 漂移、F-02 command-loop 组合缺口、F-03
  pipeline→parser→runner→summary→durable 复合链缺口。
- uncovered area：没有新增单测试贯穿 production runner 到 direct runtime assembly；这是 controller 明确允许的
  边界选择，summary→direct 的机械复制由既有 owner test 独立覆盖。若未来 runner/direct assembly 发生结构变化，可
  由后续 work unit 重新评估是否值得建立更重的跨 boundary fixture。
- 既有 later-work-unit residuals（name-only metadata batch writer lock/physical swap、material upload 类似行为、真实
  CLI/network/scenario/oracle/frozen evidence、post-commit cleanup 可见性）均未触碰，owner/destination 不变。
- 未分类 residual risk：无。

## Completion status 与 next entry point

- DS `F-01`：`已修复`。
- DS `F-02`：`已修复`。
- DS `F-03`：`已修复`（按 controller 限定边界）。
- blocking open question：无。
- next entry point：`S3 implementation re-review`。
