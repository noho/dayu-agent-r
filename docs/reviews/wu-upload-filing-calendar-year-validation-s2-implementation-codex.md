# UF-FIX04 S2 upload strict static admission implementation

## Gate record

- Gate: `implementation`
- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Slice: `S2-upload-strict-static-admission`
- Baseline commit: `e5d4394ab29ce5d8ec7db0f3aa6bb3c262696c12`
- Branch: `codex/upload-filing-oracle`
- Scope: upload filing 在 workspace state read、operation/observation/job、runner/converter 与 storage mutation 前消费 S1 shared calendar/year owner，并向 CLI/LLM tool 投影同一 typed usage 语义。
- Completion status: `implementation complete; review pending`
- Current gate / next entry point: `dual S2 deepreview`
- Artifact path: `docs/reviews/wu-upload-filing-calendar-year-validation-s2-implementation-codex.md`

## Changed files

1. `dayu/fins/ingestion_runtime.py`
   - filing static validator 直接调用 S1 `parse_calendar_year` / `parse_iso_calendar_date`；只捕获 owner `ValueError` 并映射 field-specific typed usage。
   - 删除 `FILING_DATE_TOO_LONG` / `REPORT_DATE_TOO_LONG`，新增 `INVALID_FILING_DATE` / `INVALID_REPORT_DATE`，closed mapping 同步更新。
   - year、filing date、report date 的三条 message 由 `_USAGE_MESSAGES` 各自唯一拥有，业务中立、自解释且不含 `--`。
   - 日期验证位于 period 后、file existence probes 前；invalid request 不可达 state-aware validation、operation、runner 或 durable storage。
2. `dayu/cli/commands/fins.py`
   - direct `upload_filing` 的 `filing_date` / `report_date` 传 argparse 原值，不 strip、不把 blank 折为 `None`。
   - `upload_filings_from`、material 及其它 `_optional_stripped_text` consumer 保持不变。
3. `dayu/fins/tools/upload_tools.py`
   - 新增 filing-only `_optional_raw_nullable_text`：missing/null -> `None`，string 原样返回，非 string 抛 `ValueError`。
   - 仅 filing branch 的两个日期字段使用该 reader；material/company/shared helper 未改变。
   - filing-specific LLM schema 自足说明 fiscal year 四位整数、实际 Gregorian full date 和 raw whitespace 非法，不扩大 material contract 或 arguments shape。
4. `tests/fins/test_fins_ingestion_runtime.py`
   - 迁移 `fiscal_year=0` 旧 state-aware test 为合法 `2024`。
   - 增加 bool、`0/-1/999/10000`、两个日期字段的 empty/blank/padded/non-padded/non-leap/month/separator 负向矩阵。
   - 增加 `1000/9999` 与 `2024-02-29` 正向、deterministic identity 和 shared-owner delegation guards。
   - 通过 forbidden repository/runner、holding executor、observation registry、job/portfolio tree snapshot 锁定零副作用。
5. `tests/cli/test_fins_commands.py`
   - 扩展 exact exit/stderr、fresh/seeded workspace snapshot、factory/service stream 零调用矩阵；whitespace cases 同时证明 direct CLI 未改写日期原值。
6. `tests/fins/test_fins_ingestion_tools.py`
   - 增加真实 callable 的 exact `invalid_argument` outcome、raw nullable reader、schema、material helper regression 与 state/observation/job/executor/workspace 零副作用测试。
7. `docs/reviews/wu-upload-filing-calendar-year-validation-s2-implementation-codex.md`
   - 记录本 slice 的实现、baseline/after failure 集合、验证、docs decision、residual risks 与下一 gate。

未修改其它文件；未修 `UF-FIX01` fixture；未进入 S3；未运行 `UF-PF04`；未 stage、未 commit。

## First-principles judgment and semantic ownership

- 动机成立且严重性准确：基线 upload static validator 自行接受任意非负整数，日期只限制长度，导致非法 business fact 可进入 published-state read 与后续 lifecycle；CLI/tool 又会 strip/fold filing dates，无法实施 strict admission。
- calendar/year 业务真源是 S1 accepted `dayu.fins.domain.filing_semantics`。本 slice 没有在 runtime、CLI 或 tool 重写 Gregorian/year 规则；runtime 只拥有 upload typed usage projection，CLI/tool 只拥有各自输入边界。
- 三条 LLM/CLI 共用 message 的唯一 owner 是 `ingestion_runtime._USAGE_MESSAGES`；tool 通过 runtime `FinsUploadUsageError` 原样消费，CLI 通过同一 failure 投影，不存在 channel-specific 重算。
- filing-only raw reader 是必要且最窄的 adapter boundary：JSON 参数类型 admission 属于 tool adapter，日期真实性仍完全委托 domain owner；material/shared helper 保持原 contract。
- 未新增 schema/state-machine/DTO、factory、profile、compatibility alias、fallback 或 migration，属于满足 strict admission 的最小实现，没有过度设计。

## Baseline and after failure-set evidence

### Pre-implementation baseline

- Command: `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q`
- Result: exit `1`; `57 passed`, `1 failed`, `3 warnings`。
- Complete failure node set:
  - `tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`
- Classification: pre-existing `UF-FIX01 follow-up`; fixture/code 未在本 slice 修改。

### Post-implementation full-file check

- Command: `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q`
- Result: exit `1`; `82 passed`, `1 failed`, `3 warnings`。
- Complete failure node set:
  - `tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`
- Decision: after 集合与 baseline 精确相等；没有新增、减少或变化，满足 S2 stop condition。

## Validation

所有命令均在仓库根目录执行并先激活 `.venv`；没有运行 `UF-PF04`，没有用 `xfail`、fixture 修改或非 coverage deselect 掩盖完整 tool 文件。

1. Focused S2 cases
   - Command: plan §12 指定的六个 focused nodes。
   - First result: exit `1`; `88 passed`, `1 failed`。唯一失败来自新增 material regression test 错误假设 shared helper 会把纯空白折为 `None`；直接读取 helper contract 后只修正测试为既有合法 padded/absent case，生产 material contract 未改变。
   - Final result: exit `0`; `89 passed`, `3 warnings`。
2. Runtime full file
   - Command: `pytest tests/fins/test_fins_ingestion_runtime.py -q`
   - Result: exit `0`; `256 passed`, `3 warnings`。
3. CLI full file
   - Command: `pytest tests/cli/test_fins_commands.py -q`
   - Result: exit `0`; `109 passed`, `3 warnings`。
4. Tool full file
   - Command/result/完整失败集合见上一节；真实 exit `1` 且精确等于唯一 baseline node。
5. Runtime coverage
   - Command: `coverage erase`；exit `0`。
   - Command: `coverage run -m pytest tests/fins/test_fins_ingestion_runtime.py -q`；exit `0`; `256 passed`, `3 warnings`。
   - Command: `coverage report --include='dayu/fins/ingestion_runtime.py' --fail-under=80`；exit `0`; `2188` statements、`202` missed、**`91%`**。
6. CLI coverage
   - Command: `coverage erase`；exit `0`。
   - Command: `coverage run -m pytest tests/cli/test_fins_commands.py -q`；exit `0`; `109 passed`, `3 warnings`。
   - Command: `coverage report --include='dayu/cli/commands/fins.py' --fail-under=80`；exit `0`; `469` statements、`68` missed、**`86%`**。
7. Tool coverage
   - Command: `coverage erase`；exit `0`。
   - Command: `coverage run -m pytest tests/fins/test_fins_ingestion_tools.py --deselect=tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect -q`；exit `0`; `82 passed`, `1 deselected`, `3 warnings`。
   - Command: `coverage report --include='dayu/fins/tools/upload_tools.py' --fail-under=80`；exit `0`; `102` statements、`9` missed、**`91%`**。
8. Targeted pyright
   - Command: `python -m pyright dayu/fins/ingestion_runtime.py dayu/cli/commands/fins.py dayu/fins/tools/upload_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py`
   - Result: exit `0`; `0 errors, 0 warnings, 0 informations`。
   - Controller 预审指出的 `record_date -> object` 已在验证前改为精确 `datetime.date`，所有新增函数均具有中文 Args/Returns/Raises docstring。
9. Diff integrity and scope
   - `git diff --check`: artifact 写入前后均 exit `0`，无输出。
   - 最终 `git status --short` 精确列出六个 allowed production/test 文件与唯一允许新增的 S2 implementation artifact；没有 README、冻结文件或其它 workspace change。

三条 pytest warning 均来自 `.venv` 中 `edgar` deprecated imports，不是本 slice 新增或修改代码产生的失败。

## Zero-side-effect evidence

- Runtime direct request matrix同时执行 workspace prevalidation、`start_upload` 与 `prepare_observed_upload`；forbidden `read_filing_upload_state` 调用即失败，最终 calls 始终为空。
- `_HoldingExecutor.operations == []`，`_ForbiddenUploadRunner.requests == []`，`runtime._observations == {}`，证明 operation/observation/executor/runner/converter path 不可达。
- `.dayu/fins_ingestion/jobs` 与 `portfolio` 不存在，fresh/seeded workspace tree 在调用前后 byte-for-byte snapshot 相等，证明 job/workspace/storage mutation 为零。
- CLI matrix断言 exit `2`、stdout 空、单行 exact stderr、`FINS_DIRECT_SERVICE_FACTORY`/service stream 零调用；包含 fresh workspace 与 seeded sentinel snapshot。
- Tool matrix断言真实 callable 返回 exact `ToolFailedOutcome(error="invalid_argument")`，state repository、observation、executor、job store 与 workspace snapshot 均为零变化。
- shared-owner guards 对两个合法边界年和两个合法日期字段记录直接 parser 调用；合法请求产生 deterministic filing identity 并进入 state-aware validation。

## Docs decision

- 用户明确规定 S2 不改 README/冻结文件；本 slice 仅新增当前 implementation artifact。
- `dayu/fins/README.md` 与根 `README.md` 的最终稳定 consumer contract 更新仍由 accepted S3 负责，本 slice 不提前宣称 download/aggregate contract 已完成。
- `tests/README.md`、`dayu/README.md`、Host/Engine README 不更新：没有测试层级/运行方式、分层或对应目录职责变化。

## Findings and residual risks

- Implementation self-check findings: 无 blocking finding；正式 finding 状态由下一 gate 的 dual S2 deepreview 裁决。
- S3 download shared-owner consumer 与最终 README：`covered by later approved slice`，owner=`S3-download-shared-owner-and-closeout`。
- 唯一 tool baseline failure：`assigned to later work unit`，owner=`UF-FIX01 follow-up`；failure set 在本 slice 前后精确不变。
- `UF-PF04` 真实 CLI evidence：`assigned to later work unit`，owner=`UF-PF04`；本 slice按用户要求未运行。
- `upload_filings_from` metadata strip parity：`assigned to later work unit`，owner=`upload_filings_from metadata strictness parity`。
- 其它 upload findings：`assigned to later work unit`，owner=各自既定 work unit。

没有 `unclassified residual risk`，没有 blocking open question。

## Completion and handoff

S2 objective、strict owner delegation、typed usage mapping、CLI/tool raw admission、LLM-facing schema、正负矩阵、零副作用、完整文件 failure-set equality、三个生产文件 coverage、定向 pyright与 scope integrity 均达到 accepted plan completion signal。本 artifact 只声明 implementation complete，不声明 slice accepted，不进入 S3，也不创建 checkpoint commit。

Next entry point: `dual S2 deepreview`。
