# UF-FIX03 S3 implementation

## Gate metadata

- Work unit：`UF-FIX03 summary-and-bounded-errors`
- Gate：`implementation S3`，含 controller 裁决后的 `code review fix`
- Slice：`UF-FIX03-S3 — CLI unknown boundary, direct no-artifact regression guard, and documentation`
- Accepted plan：`docs/gateflow/uf-fix03-accepted-plan-20260813.md`
- Execution baseline：`a65cec936876260fd10f47f9156e8d6a33da494e`
- Branch：`codex/upload-filing-oracle`
- Artifact path：`docs/gateflow/uf-fix03-s3-implementation-20260813.md`
- Completion status：implementation 与 controller 三项 `NEEDS_FIX` 均已落实；AgentMiMo/AgentDS 双路 re-review 均为 `PASS`。
- Next Gateflow entry：`accepted slice commit`。本轮未自行执行 deepreview/re-review，不 push。

## First-principles judgment and owner adjudication

三项 review 动机均成立：

1. frozen `upload_filing.malformed-and-empty-input` 要求普通 stderr 同时包含 canonical 文件名与有界原因。旧 `_upload_result_details(...)` 把 `file` 排在第 9 项，通用 renderer 的 8 项上限会稳定截断该事实，因此不能降级为后续工作。
2. 默认日志是匿名临时文件；旧 unknown 文案“请查看日志后重试”没有告诉用户如何保留日志，进程结束后不可行动。
3. requested/stored 虽在 runtime details 有 owner test，但 success/delete/skip/failure 缺少真实 typed RESULT 到既有 CLI renderer 的用户可见护栏。

Controller 对语义 owner 的裁决如下：

- canonical file、failure kind/code/message/retry hint 与 requested/stored 的 typed terminal 排序 owner 是 `dayu/fins/ingestion_runtime.py::_upload_result_details(...)`。修复必须在此提升 file detail 优先级；`dayu/cli/output.py` 保持通用，不增加 Fins 特例或差异化 cap。
- unknown exception 的用户可见固定提示 owner 是 `dayu/cli/commands/fins.py::run_fins_direct_command(...)` generic boundary；operator `_LOGGER.exception(...)` 保持不变。
- CLI count 测试必须消费 `FinsUploadResultSummary -> _direct_upload_terminal_events(...) -> FinsResultSummary.details -> render_fins_direct_event(...)` 同一 production 链，不在 fixture 手写第二套 details、counts 或 status 重分类。

该方案只修正已有 owner 的投影优先级和固定提示，不新增 schema、renderer 分支、兼容层、facade 或跨层依赖，因此没有过度设计。

## Implemented changes

### Production

- `dayu/fins/ingestion_runtime.py`
  - `_upload_result_details(...)` 固定把 `source kind/status/requested/stored` 放在前四项；failure 随后投影 closed kind/code、canonical file、bounded message，再放 retry hint 与 document 等辅助信息。
  - 带 file label 的 content failure 前 8 项现在同时包含 counts、kind、code、file 与 message；所有值仍直接来自同一个 `FinsUploadResultSummary` / `FinsUploadFailureReason`，未重算或解析字符串。
- `dayu/cli/commands/fins.py`
  - generic unknown stderr 固定为：`命令执行失败，请使用 --log-file PATH 重试并查看日志`。
  - `_LOGGER.exception("Fins direct command failed; command=%s", ...)` 未改，完整 traceback 仍只进入 operator log。
  - known usage、prevalidation、protocol 与 typed terminal 分支未改。
- `dayu/cli/output.py`
  - 明确 no-touch；通用 `_FINS_SUMMARY_MAX_ITEMS = 8` 与 renderer 逻辑未增加 Fins 特例。

### Tests

- `tests/fins/test_fins_ingestion_runtime.py`
  - owner test 精确断言 failure detail 的完整顺序与前 8 项投影护栏；即使存在 document/retry hint，canonical file 与 bounded message 也不会被 cap 截断。
  - success 正控通过 production upload runner 发布 filing，并从 Fins repositories 读回 source meta、original blob、derived Docling asset。
  - no-artifact 负事实只在成功正控后检查；legacy job 路径由 typed concrete `ingestion.job_store.root_dir` 取得，不硬编码生产目录。
  - empty、corrupt PDF、corrupt DOCX、mixed valid+corrupt 覆盖 typed reason、requested/stored、fail-fast 与零 publication。
- `tests/cli/test_fins_commands.py`
  - 真实 subprocess `upload_filing` 覆盖 empty PDF、corrupt PDF、corrupt DOCX：逐项断言 canonical basename、closed content kind/code、requested=`1`、stored=`0`、bounded reason、无绝对路径/traceback、fresh workspace 零 mutation。
  - unknown 与 stream failure exact stderr 同步为 `--log-file PATH` 自足提示，并继续断言 raw exception 只存在于 caplog。
  - success/delete/skip/failure 使用 `SourceKind.FILING` 与 `FinsUploadFilingRequest`；通过 public `validate_fins_upload_filing_request(...)` 构造唯一 typed validated request，再调用同模块 terminal projection owner 和既有 renderer。测试仅提供 helper 必需的最小 context 与 typed never-cancelled protocol double，不复制 validation、company-meta、count、status 或 error 映射。
  - 四状态分别断言正确 `requested_files` / `stored_files`、输出流与 `uploaded_files` 缺失。
- `tests/service/test_fins_direct.py`
  - Service public direct API 继续不暴露 start/read/wait/cancel job handle。

### Documentation

- `README.md`：面向最终用户说明 content failure stderr 同时显示文件名与有界原因；unknown failure 明示用 `--log-file PATH` 重试并查看日志。
- `dayu/fins/README.md`：说明 typed terminal detail priority、count/reason 真源与有界消费者契约。
- `tests/README.md`：说明真实 filing RESULT -> renderer 四状态集成、canonical file/bounded reason 与 no-artifact 覆盖。
- 未触发 `dayu/README.md`、Host、Engine、Service README 更新：分层/装配/public Service contract 未变。

## Changed files

相对 `a65cec93` 的 intended code/docs scope：

- `dayu/cli/commands/fins.py`
- `dayu/fins/ingestion_runtime.py`
- `tests/cli/test_fins_commands.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/service/test_fins_direct.py`
- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- `docs/gateflow/uf-fix03-s3-implementation-20260813.md`
- `docs/gateflow/uf-fix03-s3-review-fix-20260813.md`

两份既有 review artifact 保持原样：

- `docs/reviews/deepreview-uf-fix03-s3-20260813.md`
- `docs/reviews/deepreview-uf-fix03-s3-agentds-20260813.md`

## Validation

### Tests-first evidence

- 新 owner/order 与 unknown exact tests 在旧 production 上结果：`3 failed, 4 passed`。
- 失败分别直接指向旧 detail ordering 和旧 unknown 文案；四状态 typed RESULT -> renderer 链当时已通过，证明 fixture 没有手写第二套 counts。

### Final focused tests

- S3 focused：
  - `pytest -q tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py`
  - `368 passed, 3 warnings`。
- S1–S3 focused：
  - accepted plan §8.2 的八文件命令。
  - `473 passed, 3 warnings`。
- latest test-fixture simplification targeted：
  - `pytest -q tests/cli/test_fins_commands.py::test_upload_terminal_summary_renderer_uses_typed_requested_and_stored_counts`
  - `4 passed, 3 warnings`。

### Coverage

- accepted plan §8.3 八文件 coverage：`473 passed, 3 warnings`，total `88%`。
- per file：
  - `dayu/cli/commands/fins.py`：`86%`
  - `dayu/fins/direct_events.py`：`88%`
  - `dayu/fins/ingestion_runtime.py`：`91%`
  - `dayu/fins/pipelines/docling_upload_service.py`：`88%`
  - `dayu/fins/pipelines/sec_upload_workflow.py`：`93%`
  - `dayu/fins/service_runtime.py`：`90%`
  - `dayu/fins/upload_failure.py`：`97%`
  - `dayu/fins/pipelines/cn_pipeline.py`：`69%`

### Type and static audits

- final full type check：`python -m pyright dayu/ tests/ utils/` -> `0 errors, 0 warnings, 0 informations`。
- `git diff --check`：pass。
- old field audit：production `dayu/**` 零 `uploaded_files`；测试唯一 snake-case 命中是 controller 要求的 `assert "uploaded_files" not in rendered` 负向护栏，不是兼容字段。runtime details 另有 `"uploaded files" not in details` 负向护栏。
- production `FinsUploadResultSummary(...)` 仍为 accepted-plan 四个构造点；progress `file_count` 仍存在且测试覆盖。
- no-touch diff：`dayu/host/**`、`dayu/engine/**`、`dayu/runtime/**`、`dayu/config/**`、`dayu/service/**` production、`dayu/fins/storage/**`、frozen JSON/evidence 均无相对基线改动。
- frozen SHA-256：
  - `docs/cli_ci_scenarios.json`：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`
  - `docs/cli_ci_oracles.json`：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`
- 明确未运行 UF-PF03、未修改 frozen evidence、未启动内部 agents、未 commit、未 push。

## Findings and residual risks

### Fixed in current review-fix

- F1 canonical file 被 renderer cap 截断：已在 typed terminal projection owner 修复；owner 顺序、真实 empty/PDF/DOCX stderr 均有护栏。
- F2 unknown 文案在默认匿名日志下不可行动：已改为自足 `--log-file PATH` 重试指引；operator logger 不变。
- F3 缺少四状态 CLI requested/stored 集成：已用真实 filing summary/typed terminal/renderer 链覆盖，不出现旧字段。
- no-artifact jobs path 硬编码：S3 success 正控已改为 `ingestion.job_store.root_dir`；无关既有 download 测试未改。

### Assigned to later work unit

- `tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` 的既有 fixture 缺 fresh filing create 所需 `company_name`，与当前 prevalidation contract 不一致。Owner：upload tool contract/test work unit；本 S3 不在 production 增加兼容分支。

### Coverage scope adjudication

- `cn_pipeline.py` 在 S3 八文件子集 coverage 中为 `69%`，但该文件不是 S3 production diff；其修改切片 S2 已用 broader changed-file run 验证为 `94%`（`1404 passed, 1 skipped, 1 deselected`）。因此修改生产文件覆盖率目标已满足，不需要扩大 S3 测试范围、降低阈值或增加 pragma。

### External residual retained by accepted plan

- 真实 Docling 多平台差异仍归 UF-PF03；本轮按要求未执行 UF-PF03。

## Gate decision

S3 implementation 与 controller 三项 review fix 已完成，required validation、docs、frozen/no-touch audit 均已记录。AgentMiMo 与 AgentDS 定向 re-review 均为 `PASS`，artifact 分别为 `docs/reviews/deepreview-uf-fix03-s3-rereview-mimo-20260813.md` 与 `docs/reviews/deepreview-uf-fix03-s3-rereview-agentds-20260813.md`。下一入口为 accepted slice commit。
