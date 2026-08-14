# UF-FIX04 shared calendar/year validation implementation plan

## Gate state

- Gate: `plan review fix`
- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Branch: `codex/upload-filing-oracle`
- Goal confirmation: `pass`
- Goal artifact: `docs/reviews/wu-upload-filing-calendar-year-validation-goal-confirmation-controller.md`
- Scope: 只设计 shared Fins calendar/year owner、upload filing 静态 admission、download consumer 接线、对应测试与必要 README 更新。
- Changed files in this gate: 本 plan artifact，以及独立 fix artifact `docs/reviews/wu-upload-filing-calendar-year-validation-plan-fix-codex.md`。
- Validation in this gate: 完整读取 Gateflow、两份 plan review、controller adjudication 与本 plan；只读核对相关生产代码、direct consumer 和测试文件；执行内容一致性与 `git diff --check`。按用户要求未实现、未运行测试、未运行 `UF-PF04`、未 stage、未 commit。
- Completion status: `plan fix complete`
- Current gate / next entry point: `plan re-review`
- Artifact path: `docs/reviews/wu-upload-filing-calendar-year-validation-plan-codex.md`

## 1. Goal / motivation / success signal

### Goal

在 `dayu.fins.domain.filing_semantics` 建立 upload filing 与 download 共同消费的唯一 calendar/year 合法性 owner：

- `filing_date` / `report_date` 若非 `None`，必须是无首尾空白、月日补零的精确 `YYYY-MM-DD`，且能构造真实公历日期；
- required upload filing `fiscal_year` 必须是拒绝 bool 的 `1000..9999` 整数；
- upload 的非法 year/date 必须在 workspace state read、operation/observation/job 创建、converter 调用和 storage mutation 前转成 `FinsUploadUsageError`；
- download 保留自己的输入 shape、空白预处理、partial inclusive 展开和 start/end ordering，只把共同的完整日期与年份合法性交给 shared owner。

### Motivation

Calendar date 和四位业务年份是同一 Fins 领域事实，不应由 upload/download 各自实现。当前 upload 的 owner boundary 已经足够靠前，但规则不完整；download 已有更强的日历解析，却是 wrapper 私有实现。正确修复不是新增下游 fallback，而是在现有 `dayu.fins.domain` owner boundary 提供窄函数，并让两个入口直接消费。

### Success signals

1. Owner tests 证明：
   - year 只接受非 bool 的 `1000`、普通四位年份、`9999`；
   - 拒绝 `True`、`False`、`0`、负数、`999`、`10000`、float 和数字文本；
   - ISO full date 接受 `0001-01-01`、合法普通日/闰日和 `9999-12-31`，拒绝空串、纯空白、首尾空白、非补零、错误分隔符、`0000`、非闰日与非法月日；full-date 公历域不继承 fiscal-year 的 `1000` 下界。
2. Upload runtime/CLI/tool tests 证明非法 year/date 返回 typed usage/invalid-argument，不读取 published workspace state，不创建 operation/observation/job，不调用 runner/converter，不发生 storage mutation。
3. Upload 正向覆盖 `1000`、`9999`、`2024-02-29`，validated request 保留已经证明 canonical 的原始日期文本。
4. Download 的 `YYYY`、`YYYY-M[M]`、`YYYY-M[M]-D[D]` shape、外围空白接受、partial inclusive 展开和 ordering 保持；year-only/year-month 使用 `1000..9999` shared year owner，full-date 使用 `0001..9999` shared Gregorian date owner。
5. 生产代码中 upload/download 不再各自构造另一套 year/calendar validity；直接 imports/calls 可证明同源。
6. 受影响测试、逐文件 coverage 与全量 pyright 通过；README 按各自写作边界更新。

## 2. Non-goals / scope boundary

- 不执行 `UF-PF04` 真实 CLI evidence。
- 不刷新或修改 `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 及其它冻结 evidence。
- 不处理 `UF-FIX01/02/03/05...` 等其它 upload finding。
- 不扩展或收紧 `FinsUploadMaterialRequest` / `upload_material` 的日期或 fiscal year 行为。
- 不改变 download 的 ticker、forms、source 选择、overwrite/rebuild、provider、storage 或 terminal contract。
- 不改变 download 的 year/year-month/full-date shape；尤其不借本 work unit 把既有非补零 download month/day 改为只接受补零形式。
- 不改变 download 的外围空白 `strip` 行为、partial bound inclusive expansion 或 `start <= end` ordering。
- 不改变 `upload_filings_from` 生成脚本时对 metadata 日期的 strip 行为；其 strict parity 明确 deferred 到 later `upload_filings_from metadata strictness parity` work unit，本计划的 direct admission 规则不得泛化到该入口。
- 不修改 schema 文件或 durable storage schema；不迁移、兼容读取或修复历史非法 durable state。
- 不引入 compatibility shim、fallback、re-export、adapter 补偿、`hasattr/getattr`、默认值补救或 loose parsing。
- 不新建 calendar service/class/protocol/profile/factory/state machine，不把 Fins 语义放入 `dayu.runtime`、Host、Engine、Service 或 CLI。
- 不做 PR、push、merge、approve、mark ready 或外部 comment。

## 3. Design document alignment

### `docs/host/design.md`

- §2 固定 `UI -> Service -> Host -> Engine`，并明确 Host 不承载财报业务语义、不直接管理财报原文仓储规则。
- Tool/LLM-facing 参数语义必须由 source owner 保证，Host projection 不得用 fallback 或字段猜测修复。
- 因此 calendar/year 不属于 Host admission、EventLog、ToolRuntime 或 projection；Host 无需修改。

### `docs/engine/design.md`

- §1 明确 Engine 不负责工具参数校验、财报业务语义或财报仓储。
- Engine 只消费 tool schema 与 `ToolExecutor`，不能按工具名特化 upload/download 日期规则。
- 因此 Engine 无需修改；共享 owner 必须位于 Engine 外的 Fins domain。

### Repository architecture

- `dayu.runtime` 禁止承载 Fins 业务语义并禁止 import `dayu.fins`，故不能作为 calendar/year owner。
- `dayu.fins.domain.filing_semantics` 已拥有 fiscal year / fiscal period 等 filing 共享业务值，是最小且无反向依赖的 owner boundary。`normalize_fiscal_year` 的唯一生产直接 consumer 是 `dayu/fins/tools/read_runtime.py::_parse_source_document_meta`；processor/pipeline 产生 fiscal facts 或消费本模块其它语义，不是该 parser 的直接 consumer。
- CLI、tool、ingestion runtime、download wrapper 只负责各自输入形态与错误投影，不能成为第二真源。

## 4. First-principles judgment and direct evidence

### Judgment

问题真实存在，严重性准确，但必须保持 goal artifact 的现状校正：upload 已拒绝负数和 bool，不能在 plan/test 中把它们描述为“当前仍被接受”。真实缺口是 `0`、`999`、`10000` 和只做长度校验的日期；根因是同一静态 validator 的业务规则不完整，以及 download/calendar 与 fiscal year parser 各自维护不同合法域。

### Direct evidence

1. `dayu/fins/ingestion_runtime.py::_validate_fins_upload_filing_static`
   - year 条件为 `bool/non-int/request.fiscal_year < 0`；所以 `-1` 和 bool 已拒绝，但 `0`、`999`、`10000` 被接受。
   - `filing_date` / `report_date` 只调用 `_validate_optional_upload_text`，它只检查 `strip()` 后是否超过 240 字符；空白、非补零和不存在日期均可进入后续流程。
2. `dayu/fins/service_runtime.py::prevalidate_fins_upload_filing_request_for_workspace`
   - 先调用 `_filing_upload_request_identity(request)`，之后才构造 `FsFilingUploadStateRepository` 并 `read_filing_upload_state(...)`。
   - 因此将 year/date 校验放进现有 static validator 即可满足 workspace state read 前拒绝，无需新增入口特例。
3. `dayu/fins/ingestion_runtime.py::FinsIngestionRuntime._validate_runtime_upload_request`
   - raw filing request 同样先通过 `_filing_upload_request_identity`，之后才读 repository；`start_upload` 又在 job/operation 创建前调用该方法。
4. `dayu/cli/commands/fins.py::_prevalidate_upload_filing_request`
   - CLI 在 Service factory 前调用 Fins prevalidation；现有 CLI usage tests 已断言 factory 零调用和 workspace 零 mutation。
   - 但当前日期使用 `_optional_stripped_text`，会把显式空白折叠为 `None`、把首尾空白静默清理，阻止 domain owner执行严格“若提供”校验。
5. `dayu/fins/download_contract.py::_parse_date_bound`
   - 独立维护 `YYYY` / `YYYY-M[M]` / `YYYY-M[M]-D[D]` regex、`int` 转换、`calendar.monthrange` 和 `datetime.date` calendar validity。
   - 函数先 `strip`，完整日期 month/day 允许 1～2 位，并拥有 partial start/end inclusive expansion。
6. `dayu/fins/download_contract.py::_parse_optional_iso_date`
   - download effective/public result contract 又独立用 `date.fromisoformat + isoformat round-trip` 校验完整日期。
7. `dayu/fins/domain/filing_semantics.py::normalize_fiscal_year`
   - 已拒绝 bool、非 int 和 `<= 0`，但没有 `1000..9999` 边界。
   - 全仓库直接调用证据显示唯一生产 consumer 是 `dayu/fins/tools/read_runtime.py::_parse_source_document_meta`；收紧后 durable source metadata 的非法历史 year 会在 read path 明确 fail closed。
8. `tests/fins/test_fins_ingestion_runtime.py::test_validate_fins_upload_filing_request_resolves_state_aware_contract`
   - 旧测试明确把 `fiscal_year=0` 固化为“合法域”；实现时必须迁移测试到正确 owner contract，不能为保留旧测试增加兼容逻辑。
9. 冻结依据：
   - `docs/cli_ci_oracles.json` 的 `upload_filing.date-and-year-domain` 要求真实 ISO date、正四位 fiscal year、upload/download 共享合法性且 download 保留 partial expansion。
   - `docs/cli_ci_scenarios.json` 的 `UF-FIX04 shared-calendar-year-validation` 要求相同 calendar/year 复用公共 owner，状态为 `fix-required-not-started`；`UF-PF04` 是另一个 fix 后 rerun，不在本 work unit 执行。
10. 用户原始目标直接给出 fiscal-year 闭区间 `1000..9999`；该范围不是从“正四位年份”措辞推断，也不外推到 full calendar date。

## 5. Unique semantic owner and exact API decision

### Owner

唯一语义 owner：`dayu.fins.domain.filing_semantics`。

该模块负责：

- 定义 calendar year 的唯一合法范围；
- 拒绝 bool/非整数；
- 验证 canonical ISO full date 的精确 shape；
- 构造 `datetime.date` 以验证真实公历日期；
- 让 optional fiscal year normalization 委托同一 year parser。

调用层只拥有：

- upload：optional/required 组合、字段对应的 typed usage code/message、validation ordering；
- download：原始字符串的三种 shape、外围空白处理、partial expansion、start/end ordering 与 download-specific message；
- CLI：参数采集和 Fins typed error 到 exit 2 的机械映射；
- tool schema：为 LLM 自足描述 filing 分支的输入约束，不实现校验。

### Exact APIs

在 `dayu/fins/domain/filing_semantics.py` 增加两个直接函数，不新增类或协议：

```python
def parse_calendar_year(
    value: int,
    *,
    field_name: str = "year",
) -> int:
    ...

def parse_iso_calendar_date(
    value: str,
    *,
    field_name: str = "date",
) -> datetime.date:
    ...
```

精确 contract：

- `parse_calendar_year`
  - 只接受 `int` 且明确拒绝 `bool`；
  - 只接受闭区间 `1000..9999`；
  - 不接受 string/float，不推断、不 clamp、不补默认；
  - 非法统一抛 `ValueError(f"{field_name} 必须是 1000..9999 的整数")`。
- `parse_iso_calendar_date`
  - 窄签名只接受 `str`；
  - 必须 exact-match ASCII digit 的 `YYYY-MM-DD`，月日各两位，不调用 `strip`；
  - 不调用 `parse_calendar_year`，避免把 fiscal-year 的业务下界耦合到 full date；
  - 使用 `datetime.date` 构造并要求 round-trip `isoformat()` 与输入完全相同，公历 year 合法域为 `0001..9999`；
  - 非法统一抛 `ValueError(f"{field_name} 必须是实际存在的 YYYY-MM-DD 日期")`。
- 模块级私有常量承载 `1000`、`9999` 和 strict ISO regex，避免 magic values 分散；不从 `dayu.fins.domain.__init__` re-export，consumer 使用明确 owner module import。
- `normalize_fiscal_year(value: JsonValue | None, field_name=...)` 保留 optional/raw JSON semantic：`None -> None`；非空先在同一 owner 模块内显式拒绝 bool/非 int，完成 `JsonValue -> int` narrowing，再机械委托 `parse_calendar_year`。required parser 不暴露宽 raw JSON contract。这不是 compatibility wrapper；normalizer拥有“字段可缺失 + raw JSON type admission”的额外语义，而 year 范围合法性只有 `parse_calendar_year` 一份。

### Why this API is the minimum correct boundary

- 两个函数分别对应不可再合并的基础事实：整数年份合法性与 canonical full-date 合法性。
- 不引入 `CalendarValue` dataclass、parser object、strategy、registry 或 runtime helper；当前没有多历法、时区、日期区间类型或扩展压力。
- download 不需要接收 upload error types，upload 也不需要依赖 download wrapper；两者只共享纯 domain value parser。
- `datetime.date` 是 Python 3.11 标准库的公历真实性 owner，无需手写闰年/月长规则。

## 6. Input adjudication

### Upload strict dates

- `None`：表示未提供，允许。
- `""`、`"   "`：调用方显式提供但不是日期，拒绝；不得折叠为 `None`。
- `" 2024-02-29"`、`"2024-02-29 "`：拒绝；不得 strip 后接受。
- `"2024-2-9"`、`"2024-02-9"`、`"2024-2-09"`：拒绝；必须月日补零。
- `"2024/02/29"`：拒绝。
- `"2023-02-29"`、`"2024-13-01"`、`"2024-04-31"`：拒绝为不存在的公历日期。
- `"2024-02-29"`：接受。
- full date 只受 strict shape 与实际 Gregorian date 约束；`0001-01-01`、`0999-12-31` 和 `9999-12-31` 接受，`0000-12-31` 拒绝。它不继承 fiscal-year `1000` 下界。

CLI 的 `_prevalidate_upload_filing_request` 对 upload filing 的两个日期字段必须传递 argparse 原值，不再调用 `_optional_stripped_text`。其它字段及 `upload_material` 继续使用原 helper，不受影响。

`start_fins_upload` 的 filing branch 对 `filing_date` / `report_date` 使用模块级窄 raw nullable reader：字段缺失或 JSON null 才返回 `None`；string（包括空串、纯空白和带首尾空白文本）原样进入 domain admission；非 string 在 tool argument boundary 拒绝。不得改 `_optional_nullable_text` 的既有 strip 语义，company/material branch 及所有其它消费者继续使用原 helper。

### Download preservation strategy

- 继续先对 `raw_value` 调用 `strip()`；所以外围空白仍按既有 download wrapper contract 接受。
- 继续由 `_YEAR_PATTERN`、`_YEAR_MONTH_PATTERN`、`_FULL_DATE_PATTERN` 识别 `YYYY`、`YYYY-M[M]`、`YYYY-M[M]-D[D]`；不改 regex shape。
- year-only：把四位文本转为 int 后调用 `parse_calendar_year`，再按 start/end 展开到 `01-01` / `12-31`。
- year-month：年份调用 `parse_calendar_year`；month 合法性与 start day=1/end day=`calendar.monthrange` 继续由 download wrapper 拥有。
- full-date：保留 1～2 位 month/day shape；wrapper 拆分后用 `f"{year:04d}-{month:02d}-{day:02d}"` 构造 canonical 文本，再调用 `parse_iso_calendar_date`。该分支不调用 `parse_calendar_year`，所以 `0999-12-31` 合法；download 的 `2024-2-9` 仍接受并投影为 `2024-02-09`，而 upload 的同一原始文本严格拒绝。
- `_parse_optional_iso_date` 继续拥有 download public DTO 的文本安全和错误 wording，但把真实 ISO/calendar 校验委托 `parse_iso_calendar_date`。
- `FinsDownloadDateRange.__post_init__` 继续唯一拥有 `start_bound <= end_bound`；不得移到 shared date owner。

## 7. Affected files and call/data flow

### Planned production files

1. `dayu/fins/domain/filing_semantics.py`
   - 新增 shared year/date APIs；收紧 `normalize_fiscal_year` delegation。
2. `dayu/fins/ingestion_runtime.py`
   - upload static validator 调用 shared owner；调整 typed usage code/message；只保留 company name 的通用 optional text length helper。
3. `dayu/fins/download_contract.py`
   - date-bound 与 public ISO date wrapper 委托 shared owner；保留 download shape/expansion/order。
4. `dayu/cli/commands/fins.py`
   - upload filing 日期不再预先 strip/折叠空白；其它命令/字段不变。
5. `dayu/fins/tools/upload_tools.py`
   - filing branch 两个日期字段使用不 strip、不折叠空白的窄 raw reader；material/company 与其它字段保留原 helper；同步更新 filing-specific LLM-facing schema 文案。

### Planned tests

6. `tests/fins/test_fiscal_normalization_contracts.py`
   - shared owner contract tests；更新 fiscal normalization 边界。
7. `tests/fins/test_read_runtime_semantic_ownership_guards.py`
   - `read_runtime.py::_parse_source_document_meta` direct consumer 回归：合法四位年份不变，非法历史年份明确 fail closed。
8. `tests/fins/test_fins_ingestion_runtime.py`
   - upload direct owner/delegation、typed error、static validation ordering、legacy job zero-side-effect、正向边界；迁移 year 0 旧测试。
9. `tests/fins/test_fins_ingestion_tools.py`
   - LLM-facing upload schema/outcome 自足约束；filing raw date 不 strip；tool filing invalid input 在 observation/job/executor 前 failed outcome；material 回归不变。
10. `tests/cli/test_fins_commands.py`
   - upload CLI year/date matrix、exit 2、exact stderr、Service factory/workspace zero-side-effect；download shape/expansion/calendar/order 回归。

### Planned docs

11. `dayu/fins/README.md`
    - 更新 domain owner 稳定 contract：full calendar date `0001..9999` 与 fiscal/download partial year `1000..9999`；说明 download wrapper ownership，并把 strict raw admission 限定到直接 `upload_filing` 与 filing tool。
12. `README.md`
    - 在最终用户 download 与直接 `upload_filing` / filing tool 段补充当前可用输入规则和 usage rejection；不得概括为所有 upload/batch 入口，不写内部 owner/module。

### Explicitly unaffected

- `dayu/fins/domain/__init__.py`：不新增兼容 re-export。
- `dayu/cli/arg_parsing.py`：`--fiscal-year type=int` 与现有参数面不变；filing/material 共用 help 不在此 work unit 混入不同 material contract。
- Host/Engine/Service/storage/converter/pipeline production files：不新增下游校验或补偿。
- `tests/README.md`：仍是同一测试层、命令与维护规则，按其更新边界无需机械追加用例流水账。
- `dayu/README.md`：跨包关系和装配边界不变。

### Call chain after implementation

```text
CLI upload_filing raw args (date preserved exactly)
  -> FinsUploadFilingRequest
  -> prevalidate_fins_upload_filing_request_for_workspace
  -> _filing_upload_request_identity
  -> _validate_fins_upload_filing_static
       -> parse_calendar_year
       -> parse_iso_calendar_date (filing_date/report_date when non-None)
  -> only after pass: FsFilingUploadStateRepository.read_filing_upload_state
  -> validate state-aware action/company contract
  -> Service factory / direct operation
  -> runner -> converter -> storage mutation

Tool/direct runtime filing request
  -> upload_tools filing-only raw nullable reader (date preserved exactly)
  -> prepare_observed_upload / start_upload
  -> _validate_runtime_upload_request
  -> same _filing_upload_request_identity/static owner
  -> only after pass: state read / observation or job creation / runner

Download raw bound
  -> _parse_date_bound owns strip + shape
  -> parse_calendar_year and/or parse_iso_calendar_date
  -> download-owned partial inclusive expansion
  -> FinsDownloadDateRange owns start/end ordering
```

## 8. Contract / error changes

### Domain contract

- 新增 `parse_calendar_year` / `parse_iso_calendar_date` direct module APIs。
- `parse_calendar_year` required API 只接受 `int`；`normalize_fiscal_year` 从“任意正整数”收紧为“缺失或 `1000..9999` 非 bool 整数”，并在同 owner 内先 narrow raw `JsonValue` 再委托 required parser。
- `parse_iso_calendar_date` 独立拥有 strict full-date 真实性，接受实际 Gregorian `0001..9999`，不复用 fiscal/download partial year 下界。
- 不增加 schema/version/migration；历史非法 durable metadata 在读取时按新 contract fail closed，不提供兼容读取。

### Upload typed usage contract

- `FinsUploadUsageCode.INVALID_FISCAL_YEAR` 保留 code identity，message 改为：`财年（fiscal_year）必须是 1000..9999 的整数`。
- 删除语义不再准确的 `FILING_DATE_TOO_LONG` / `REPORT_DATE_TOO_LONG`，新增：
  - `INVALID_FILING_DATE = "invalid_filing_date"`
  - `INVALID_REPORT_DATE = "invalid_report_date"`
- 对应 messages：
  - `披露日期（filing_date）必须是实际存在的 YYYY-MM-DD 日期`
  - `报告期日期（report_date）必须是实际存在的 YYYY-MM-DD 日期`
- 三个 code 各自只有上述一份业务中立、自解释 message owner，CLI usage 与 LLM tool outcome共同消费；message 不含 CLI `--flag` 语法，不增加 channel-specific 文案或重复映射。
- 所有 year/date domain `ValueError` 只在 upload admission boundary 映射为上述 typed usage codes；不把 raw exception 文本或 Python 类型名暴露给 CLI/LLM。
- closed mapping test 必须同步更新 exact code set 与 exact messages；不保留旧 code alias。

### Download contract

- `FinsDownloadUsageError` 类型和现有用户 wording 分类保留：empty、too long、format error、invalid calendar、ordering。
- year-only/year-month 的 year `<1000`（包括 `0001`/`0999`）由 shared year owner判为 invalid；full-date 的 `0001..0999` 继续合法并由 shared full-date owner验证；四位 shape 本身仍由 download wrapper识别。
- 非补零 full date 与外围空白继续按既有 download wrapper 接受并 canonicalize。
- 无 public schema/state-machine/DTO 字段变化。

### LLM-facing tool schema

- `start_fins_upload` 的 `fiscal_year` 描述明确：filing 必填且只接受 `1000..9999` 整数；material 仍只是可选，不声称本 work unit收紧其 contract。
- `filing_date` / `report_date` 描述明确：filing 分支若填写，必须是实际存在的 `YYYY-MM-DD`；不暴露 owner 模块、Host/runtime 或内部 code。
- schema 明确日期文本不会自动去除空白，空串、纯空白或首尾空白均非法；material 分支现有 normalization 不在本 work unit改变。

## 9. Zero-side-effect assertions and exact locations

### Owner/runtime assertions

在 `tests/fins/test_fins_ingestion_runtime.py` 增加参数化测试，覆盖每个 invalid class，并安装会立即失败的 spy/fake：

- `FilingUploadStateRepositoryProtocol.read_filing_upload_state`：调用即 `AssertionError`，证明 workspace state read 为零；
- `_HoldingExecutor.operations` / submitted operation：必须为空，证明 job/operation 为零；
- `_FakeUploadRunner.requests`：必须为空，证明 upload runner/converter path 不可达；
- workspace `.dayu/fins_ingestion/jobs` 与 `portfolio` tree：保持不存在或 byte-for-byte snapshot 不变，证明 durable mutation 为零。

分别通过：

- `prevalidate_fins_upload_filing_request_for_workspace(...)` 验证 CLI/Service preflight 顺序；
- `FinsIngestionRuntime.start_upload(raw_request)` 或 `prepare_observed_upload(raw_request)` 验证 legacy/awaiting operation 创建前顺序。

不要只断言异常类型；必须同时断言上述 call/mutation counters。

### CLI assertions

扩展 `tests/cli/test_fins_commands.py::test_upload_filing_usage_matrix_precedes_service_factory_and_workspace_mutation` 或建立同边界的专用参数化测试，覆盖：

- fiscal year：`0`、`999`、`10000`；
- filing/report date：空串、纯空白、首尾空白、非补零、非闰日、非法月、错误分隔符；
- exact exit=`2`、stdout 空、单行 exact stderr；
- `FINS_DIRECT_SERVICE_FACTORY` calls、service stream calls 均为空；
- fresh workspace 不存在，seeded workspace tree snapshot 不变。

### Tool assertions

在 `tests/fins/test_fins_ingestion_tools.py` 使用真实 upload callable + no-op/recording runtime boundary：

- invalid filing year/date 返回 `ToolFailedOutcome(error="invalid_argument")`；
- message 精确等于业务中立 usage 文案且不含 `--`；
- observation/job store 为空、executor submit 为零；
- filing branch 对 empty/blank/padded whitespace 原样送达 admission 并失败，证明 tool adapter 未 strip/折叠；
- 单独保留 material request 的既有合法 case，证明没有扩展 material validation。

## 10. Small implementation slices

### Slice 1 — Fins domain calendar/year owner

- ID/name: `S1-domain-calendar-year-owner`
- Objective: 建立唯一 pure domain APIs，并让 optional fiscal normalization 委托 year owner。
- Expected outcome: owner contract 完整、独立可测，尚不改变 upload/download wrapper ownership。
- Allowed files:
  - `dayu/fins/domain/filing_semantics.py`
  - `tests/fins/test_fiscal_normalization_contracts.py`
  - `tests/fins/test_read_runtime_semantic_ownership_guards.py`
- Prerequisites: accepted plan；无其它 slice dependency。
- Exact allowed changes:
  1. import `datetime`，增加私有 year bounds/strict ISO pattern；
  2. 实现本 plan §5 两个 exact API，补完整中文 docstring（参数、返回、异常）；
  3. `normalize_fiscal_year` 对 non-None raw `JsonValue` 先在本模块拒绝 bool/非 int，narrowing为 `int` 后只调用 `parse_calendar_year`；更新 docstring/message；
  4. 添加 exact positive/negative owner matrices、`0001..9999` full-date闰年/calendar/format/whitespace tests；更新旧“正整数”期望为四位范围；
  5. 在 `tests/fins/test_read_runtime_semantic_ownership_guards.py` 为 `_parse_source_document_meta` 增加 direct consumer回归：`1000/2025/9999` 保持解析，`999/10000/bool/数字文本` 抛 owner `ValueError`，证明非法历史 durable metadata fail closed而不被忽略或默认化。
- Invariants:
  - no strip/coercion/inference；bool 永不按 int 接受；
  - `datetime.date` 是 full-date calendar truth，`parse_iso_calendar_date` 不调用 `parse_calendar_year`；
  - 不 import upload/download/CLI/runtime；
  - 不 re-export，不新建对象模型。
- Non-goals: 不接线 consumer、不改 error projection、不改 README。
- Tests/validation:
  - `source .venv/bin/activate && pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q`
  - `source .venv/bin/activate && coverage erase && coverage run -m pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py tests/fins/test_sec_pipeline_download.py -q && coverage report --include='dayu/fins/domain/filing_semantics.py' --fail-under=80`
  - `source .venv/bin/activate && python -m pyright dayu/fins/domain/filing_semantics.py tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py`
- Completion signal: API/type/docstring、owner matrix与 read-runtime direct consumer回归一致；上述测试通过，真实可达 owner coverage集合对 `filing_semantics.py` 达到 >=80%，无 consumer-specific rule 进入 domain。
- Stop condition: 若现有 fiscal producer 明确需要合法的 `<1000` 或 `>9999` 业务年份直接证据，停止并返回 plan review，不加例外。

### Slice 2 — Upload strict admission and zero-side-effect boundaries

- ID/name: `S2-upload-strict-static-admission`
- Objective: upload filing 在所有 state/operation/converter/storage 边界前消费 shared owner，并给 CLI/LLM/tool 提供一致业务语义。
- Expected outcome: invalid upload year/date typed fail fast；合法 strict dates/edge years继续进入既有 state-aware validation。
- Allowed files:
  - `dayu/fins/ingestion_runtime.py`
  - `dayu/cli/commands/fins.py`
  - `dayu/fins/tools/upload_tools.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `tests/fins/test_fins_ingestion_tools.py`
  - `tests/cli/test_fins_commands.py`
- Prerequisites: S1 accepted。
- Exact allowed changes:
  1. static validator import/call `parse_calendar_year`，用 existing `INVALID_FISCAL_YEAR` 投影失败；
  2. 以专用 `_validate_optional_upload_iso_date`（或等价模块级窄 helper）处理两个 optional date，helper 只做 `None` gate、调用 shared owner、映射字段 code，不实现规则；
  3. 替换两个过时 date-too-long codes/messages，不保留 alias；三个 year/date code 使用§8唯一业务中立 message，更新 closed code mapping并断言文本不含 `--`；
  4. CLI upload filing 传递 date 原值，其它 `_optional_stripped_text` 调用保持；
  5. 在 `upload_tools.py` 增加 filing-only模块级窄 raw nullable reader：missing/null -> `None`，string原样返回，非 string抛 `ValueError`；仅 filing branch的 `filing_date/report_date` 使用它，material/company及其它消费者继续使用 `_optional_nullable_text`；
  6. 更新 upload tool schema 的 filing-specific 自足描述，不改变 arguments shape或 material request；
  7. 将现有 year 0“合法域”测试改为合法 2024 的 state-aware contract test，新增 year/date invalid matrices与边界正向 cases；
  8. 添加 §9 的 repository/operation/runner/workspace zero-side-effect assertions；
  9. 添加 shared-owner delegation guard：monkeypatch/spy `ingestion_runtime.parse_calendar_year` 和 `parse_iso_calendar_date`，证明 static path 调用 owner，而非只碰巧表现一致。
- Data flow/state transition:
  - invalid -> `FinsUploadUsageError`，无 state transition；
  - valid -> 既有 `_StaticFinsUploadFilingValidation` -> state read -> state-aware validated request；
  - 不修改 `ValidatedFinsUploadFilingRequest` shape，因为严格输入本身已是 canonical，validated request 保留同一 immutable request 即同源。
- Error handling:
  - 只捕获 owner `ValueError` 并映射 field-specific typed usage code；
  - 不捕获 `Exception`，不暴露 owner raw text，不使用 fallback/default。
- Invariants:
  - year/date checks 必须位于 file existence probes 之前或至少位于任何 workspace read/operation前；为更强的确定性，放在 period 后、file checks 前并用测试锁定；
  - 不读取 published state 再判 calendar/year；
  - delete 也必须满足 required fiscal year 和提供日期的合法性，因为 filing identity/metadata contract不因 action 绕过；
  - material branch与 `_optional_nullable_text` 行为不变。
- Non-goals: 不改 action/company/file/converter/storage 规则；不实施 UF-FIX01；不修其测试 fixture；不改 arg parser shape；不改 `upload_filings_from` metadata strip。
- Tests/validation:
  - 新增/受影响 cases 必须全绿：`source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py::test_filing_calendar_year_static_admission_precedes_all_side_effects tests/fins/test_fins_ingestion_runtime.py::test_filing_calendar_year_static_admission_accepts_boundaries_and_delegates tests/fins/test_fins_ingestion_tools.py::test_upload_tool_filing_calendar_year_invalid_input_has_zero_side_effects tests/fins/test_fins_ingestion_tools.py::test_upload_tool_filing_dates_preserve_raw_text_until_domain_admission tests/fins/test_fins_ingestion_tools.py::test_upload_tool_calendar_year_schema_and_usage_messages_are_business_neutral tests/cli/test_fins_commands.py::test_upload_filing_usage_matrix_precedes_service_factory_and_workspace_mutation -q`。
  - `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`，expected exit `0`。
  - `source .venv/bin/activate && pytest tests/cli/test_fins_commands.py -q`，expected exit `0`。
  - `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q`，允许且只允许 exit 非零对应同一 baseline failure `tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`；必须记录完整 failure node集合并与 pre-implementation baseline精确相等，任何新增/扩散立即停止。不得用 pipeline、`|| true`、`xfail`、deselect 或改 fixture掩盖这次完整文件核对。
  - 逐文件 coverage命令见§12；tool coverage集合只为 coverage明确 deselect上述 UF-FIX01 baseline，coverage命令自身必须 exit `0`，完整文件基线核对仍单独保留。
  - `source .venv/bin/activate && python -m pyright dayu/fins/ingestion_runtime.py dayu/cli/commands/fins.py dayu/fins/tools/upload_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py`
- Completion signal: 新增/受影响 cases全部 exit 0；runtime/CLI完整文件全绿；tool完整文件失败集合与唯一 UF-FIX01 baseline精确相等且无新增/扩散；三个生产文件各自 coverage >=80%；invalid matrices均为 typed fail-fast且所有 counter/tree 为零。
- Stop condition: 若 material/helper contract发生变化、tool完整文件失败集合变化、任一新增/受影响 case失败或需要修改 UF-FIX01 fixture，停止并返回裁决。

### Slice 3 — Download delegation, regressions, docs and aggregate validation

- ID/name: `S3-download-shared-owner-and-closeout`
- Objective: download 消费同一 owner、冻结 wrapper-owned行为，并完成稳定文档与全量验证。
- Expected outcome: upload/download 同源；download 既有 shape/expansion/order无回归；docs匹配当前实现。
- Allowed files:
  - `dayu/fins/download_contract.py`
  - `tests/cli/test_fins_commands.py`
  - `README.md`
  - `dayu/fins/README.md`
- Prerequisites: S1、S2 accepted。
- Exact allowed changes:
  1. 按 §6 接线 `_parse_date_bound`：shape与strip留在 wrapper，year-only/year-month委托 `parse_calendar_year`，full-date canonicalize后只委托 `parse_iso_calendar_date`；
  2. `_parse_optional_iso_date` 保留 public text/error wrapper，calendar parsing 委托 owner；
  3. 添加 owner delegation spy、year bounds、闰日/非法日、外围空白、非补零 full-date、year/year-month inclusive expansion、start/end ordering回归；
  4. 根 README 只写最终用户可见 download与直接 `upload_filing` / filing tool规则和 exit 2，明确不覆盖 `upload_filings_from` batch metadata normalization；
  5. Fins README 更新 domain owner与download wrapper职责，把 strict raw admission限定到直接 upload filing入口，不写 work unit/测试流水账；
  6. 按 README trigger复核 `tests/README.md` 与 `dayu/README.md`，预期不修改并在 implementation artifact记录理由。
- Invariants:
  - `_FULL_DATE_PATTERN` 继续允许 1～2 位 month/day；
  - input先strip；
  - full-date `0001..9999` 由 date owner决定；year-only/year-month仍只接受 `1000..9999`；
  - partial end使用真实月末，闰年 2 月正确；
  - ordering仍只在 `FinsDownloadDateRange`；
  - download user error type/分类不变；
  - README不得写未来能力、内部实现术语或把 direct admission泛化为 `upload_filings_from` parity。
- Non-goals: 不把 partial date parser移入 domain；不增加 date range类型；不改 provider/storage；不改 `upload_filings_from`。
- Tests/validation:
  - `source .venv/bin/activate && pytest tests/cli/test_fins_commands.py -q`
  - `source .venv/bin/activate && coverage erase && coverage run -m pytest tests/cli/test_fins_commands.py -q && coverage report --include='dayu/fins/download_contract.py' --fail-under=80 && coverage report --include='dayu/cli/commands/fins.py' --fail-under=80`
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `git diff --check`
- Completion signal: download/CLI完整测试、两个修改生产文件 coverage、全量 pyright、diff check全部通过；S1/S2各自 coverage和baseline证据仍有效；README scope decision已记录；没有未分类 residual risk。
- Stop condition: 任何 download shape/expansion/order regression、pyright新增/扩散错误、单文件 coverage不足或 README contract 与代码不一致时，不关闭 slice。

## 11. Test matrix and expected assertions

### Owner tests

| Contract | Accept | Reject |
| --- | --- | --- |
| calendar year | `1000`, `2024`, `9999` | bool、`0`、`-1`、`999`、`10000`、`2024.0`、`"2024"`、`None`（required parser） |
| optional fiscal year | `None`, `1000`, `2025`, `9999` | 与 required parser相同的非空非法值 |
| strict ISO full date | `0001-01-01`, `0999-12-31`, `1000-01-01`, `2024-02-29`, `9999-12-31` | empty/blank/padded whitespace、非补零、slash、`0000-12-31`、非闰日、month 13、April 31 |

### Upload tests

- 每个 field (`fiscal_year`, `filing_date`, `report_date`) 都有直接 request 负向与正向。
- bool year 必须在 Python typed boundary 测试，不能只依赖 argparse `type=int`。
- `0`、`999`、`10000` 必须明确拒绝；`-1` 保持拒绝作为回归，不写成新发现。
- date error code按 field区分；message exact且 <=240，不含 path/traceback。
- CLI usage 与 tool outcome 对同一 code使用同一业务中立 message，均不含 `--`；tool schema同步说明 raw whitespace非法。
- 合法 `2024-02-29` 与 fiscal years `1000/9999` 可产生 deterministic filing identity并进入 state-aware path。
- zero-side-effect 断言见 §9。

### Download tests

- year：`1000`/`9999` start/end expansion；`0999`/`0000` invalid。
- year-month：`2024-2` start=`2024-02-01`、end=`2024-02-29`；非法 month typed usage。
- full date：`0001-1-1`、`0999-12-31`、`2024-2-9` 和外围空白继续接受并 canonicalize；`0000-12-31`、`2023-2-29`、`2024-13-1`拒绝。
- ordering：expanded start晚于end仍由 `FinsDownloadDateRange`拒绝，message保持。
- effective/public result date DTO：strict canonical ISO，非补零/空白/不存在日期拒绝并通过 shared owner。
- delegation spy分别证明 year/full-date owner被调用。

### Regression tests

- 既有 ticker/forms、overwrite/rebuild、action/company/file、upload success与material case不变。
- `tests/fins/test_read_runtime_semantic_ownership_guards.py` 直接断言 `_parse_source_document_meta` 对合法四位年份保持解析，对非法历史年份 fail closed；不把 processor/pipeline误记为 `normalize_fiscal_year` direct consumer。
- `upload_material` 的可选 fiscal/date行为保持当前测试结果。
- `upload_filings_from` metadata strip parity保持现状，不在本 work unit测试或文档中宣称已严格化。
- frozen JSON只读，测试不得生成或重写 oracle/scenario。

## 12. Validation commands

每个修改生产文件使用下列真实可达测试集合；不再用同一个四文件集合假定所有文件都达到 coverage gate：

| 修改生产文件 | coverage / regression 测试集合 | 选择依据 |
| --- | --- | --- |
| `dayu/fins/domain/filing_semantics.py` | `tests/fins/test_fiscal_normalization_contracts.py`、`tests/fins/test_read_runtime_semantic_ownership_guards.py`、`tests/fins/test_sec_pipeline_download.py` | 分别覆盖新增 year/date与direct read consumer、既有 fiscal/SEC form/quality owners，能到达完整 owner模块而非只到新增函数 |
| `dayu/fins/ingestion_runtime.py` | `tests/fins/test_fins_ingestion_runtime.py` | 直接覆盖 static admission、state ordering、operation/job/runner路径与closed usage mapping |
| `dayu/fins/tools/upload_tools.py` | `tests/fins/test_fins_ingestion_tools.py`，coverage时精确 deselect唯一 UF-FIX01 baseline node | 直接覆盖 schema、arguments adapter、tool outcome与observation boundary；已知无关失败另做完整文件精确集合核对 |
| `dayu/cli/commands/fins.py` | `tests/cli/test_fins_commands.py` | 直接覆盖 upload prevalidation、download mapping、exit/stderr与factory/workspace边界 |
| `dayu/fins/download_contract.py` | `tests/cli/test_fins_commands.py` | CLI contract tests直接构造/执行 download request与date range路径，覆盖 shape/expansion/calendar/order |

### S1 commands

```bash
source .venv/bin/activate
pytest tests/fins/test_fiscal_normalization_contracts.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py -q
coverage erase
coverage run -m pytest \
  tests/fins/test_fiscal_normalization_contracts.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py \
  tests/fins/test_sec_pipeline_download.py -q
coverage report --include='dayu/fins/domain/filing_semantics.py' --fail-under=80
python -m pyright dayu/fins/domain/filing_semantics.py \
  tests/fins/test_fiscal_normalization_contracts.py \
  tests/fins/test_read_runtime_semantic_ownership_guards.py
```

Expected：每条命令自身 exit `0`，`filing_semantics.py >=80%`；不得用 shell pipeline掩盖 pytest/coverage exit code。

### S2 commands

```bash
source .venv/bin/activate
pytest \
  tests/fins/test_fins_ingestion_runtime.py::test_filing_calendar_year_static_admission_precedes_all_side_effects \
  tests/fins/test_fins_ingestion_runtime.py::test_filing_calendar_year_static_admission_accepts_boundaries_and_delegates \
  tests/fins/test_fins_ingestion_tools.py::test_upload_tool_filing_calendar_year_invalid_input_has_zero_side_effects \
  tests/fins/test_fins_ingestion_tools.py::test_upload_tool_filing_dates_preserve_raw_text_until_domain_admission \
  tests/fins/test_fins_ingestion_tools.py::test_upload_tool_calendar_year_schema_and_usage_messages_are_business_neutral \
  tests/cli/test_fins_commands.py::test_upload_filing_usage_matrix_precedes_service_factory_and_workspace_mutation -q
pytest tests/fins/test_fins_ingestion_runtime.py -q
pytest tests/cli/test_fins_commands.py -q
pytest tests/fins/test_fins_ingestion_tools.py -q

coverage erase
coverage run -m pytest tests/fins/test_fins_ingestion_runtime.py -q
coverage report --include='dayu/fins/ingestion_runtime.py' --fail-under=80
coverage erase
coverage run -m pytest tests/cli/test_fins_commands.py -q
coverage report --include='dayu/cli/commands/fins.py' --fail-under=80
coverage erase
coverage run -m pytest tests/fins/test_fins_ingestion_tools.py \
  --deselect=tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect -q
coverage report --include='dayu/fins/tools/upload_tools.py' --fail-under=80

python -m pyright dayu/fins/ingestion_runtime.py \
  dayu/cli/commands/fins.py \
  dayu/fins/tools/upload_tools.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/cli/test_fins_commands.py
```

Expected：focused新增/受影响 cases、runtime完整文件、CLI完整文件、三个coverage与pyright均 exit `0`。tool完整文件命令保留真实非零 exit，失败集合必须精确等于唯一预存 node `tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`；它是 `UF-FIX01 follow-up` 预存失败，不修 fixture、不标 xfail、不把完整文件伪报为通过。若失败集合新增、减少或变化，立即停止并由 controller裁决。

### S3 and aggregate commands

```bash
source .venv/bin/activate
pytest tests/cli/test_fins_commands.py -q
coverage erase
coverage run -m pytest tests/cli/test_fins_commands.py -q
coverage report --include='dayu/fins/download_contract.py' --fail-under=80
coverage report --include='dayu/cli/commands/fins.py' --fail-under=80
python -m pyright dayu/ tests/ utils/
git diff --check
```

Expected：每条 S3/aggregate命令自身 exit `0`，两个文件各自 coverage >=80%，pyright不新增/扩散/掩盖错误。实现 artifacts还必须汇总S1/S2各自 coverage结果与tool完整文件精确baseline比较，不能用后续窄命令替代早先证据。

本 plan fix gate 不运行以上命令；它们属于 implementation slice validation。`UF-PF04` 明确不在任何命令中。

## 13. README decision

- `dayu/fins/README.md`: **需要更新**。本 work unit改变 `dayu.fins.domain.filing_semantics` 的稳定 owner contract及 download/direct-upload复用关系，属于其开发者手册职责。必须区分 full-date `0001..9999` 与 fiscal/download partial year `1000..9999`，并把 strict raw-date admission限定为直接 `upload_filing` 与 `start_fins_upload` filing branch。
- 根 `README.md`: **需要更新**。直接 `upload_filing` / filing tool可接受年份/日期、download日期合法域与usage exit是最终用户可见工作流；不得写成所有 upload 或 `upload_filings_from` 均已实现 strict raw metadata parity。
- `tests/README.md`: **不更新**。只增加既有 Fins/CLI 测试层中的 contract cases，没有新增测试层级、运行方式或维护规则；其 README 更新边界禁止机械记录用例流水账。
- `dayu/README.md`: **不更新**。Fins仍是同一业务能力包，`UI -> Service -> Host -> Engine`、装配与依赖边界不变。
- `dayu/host/README.md` / `dayu/engine/README.md`: **不触发**，没有相应代码变化。

## 14. Risks / open questions / residual-risk classification

### Blocking open questions

- 无。owner、API、输入裁决、错误 contract、consumer boundary、测试位置和 docs decision均已确定，可直接进入 plan review。

### Risks and mitigations

1. **历史非法 fiscal year 读取变为 fail closed**
   - 说明：`normalize_fiscal_year` 收紧后，历史 `1..999` 或 `>9999` metadata不再可读为合法事实。
   - 决策：这是新 contract 的预期结果；schema按全新设计处理，明确不做兼容读取/迁移。
   - 分类：`fixed in current slice`（owner contract消除非法事实）；不是 deferred compatibility risk。
2. **CLI 过去静默 strip upload date**
   - 说明：显式外围空白将从接受变为 usage error。
   - 决策：这是 strict optional input requirement的必要 contract change；只改 upload filing date字段，其他字段不变。
   - 分类：`fixed in current slice`。
3. **download与upload格式严格度不同可能被误判为漂移**
   - 说明：download保留 wrapper-owned non-padded shape，upload严格 canonical ISO。
   - 缓解：shared year owner只拥有 fiscal/download partial year `1000..9999`；shared full-date owner独立拥有实际 Gregorian `0001..9999`。download先按自己的shape规范化，再调用对应owner。测试分别锁定。
   - 分类：`fixed in current slice`。
4. **shared tool schema字段也服务 material**
   - 说明：错误措辞可能无意宣称material contract已收紧。
   - 缓解：文案明确限定filing分支，并保留material回归测试。
   - 分类：`fixed in current slice`。
5. **`UF-PF04`真实CLI evidence未执行**
   - 分类：`assigned to later work unit`，owner=`UF-PF04`；本 work unit按用户明确排除。
6. **其它 upload findings**
   - 分类：`assigned to later work unit`，owner=`UF-FIX01/02/03/05...`各自 work unit；不得借本修复扩大。
7. **`upload_filings_from` raw-date parity**
   - 说明：batch script generation仍按现有 metadata strip语义工作，本计划不声明其与direct admission完全一致。
   - 分类：`assigned to later work unit`，owner=`upload_filings_from metadata strictness parity`；本 work unit不创建/修改issue。
8. **tool完整文件预存失败**
   - 说明：`tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` 是已稳定复现的UF-FIX01 fixture/contract不同步，不属于calendar/year链路。
   - 分类：`assigned to later work unit`，owner=`UF-FIX01 follow-up`；当前slice只证明新增/受影响cases全绿且完整文件失败集合没有新增或扩散。

没有 `unclassified residual risk`，没有需要新 issue 或用户裁决的风险。

## 15. Why this is not over-designed

- 复用已有 `filing_semantics.py`，只增加两个纯函数和私有常量；不新增包、类、协议、factory或状态机。
- 复用 Python `datetime.date`，不手写公历规则。
- 在已有最早 static admission owner修复，不增加 CLI/service/pipeline/storage 多层重复校验。
- download仅替换合法性实现，不搬迁其独有shape、partial expansion和ordering。
- filing tool只增加一个日期字段专用raw reader，避免修改共享strip helper而波及material/company；该窄分流由入口契约差异直接要求，不是兼容shim。
- validated upload request不增加重复的normalized date字段，因为严格接受的原文已经等于canonical文本；避免同一事实两份状态。
- 不为历史非法值、旧错误码或旧测试保留shim；测试跟随正确 owner contract迁移。
- 文档只更新稳定、当前可见 contract，不记录实现流水账或未来计划。

## 16. Completion report format

Implementation完成后的最终报告必须使用以下内容结构，并与真实验证结果一致：

```text
结论：UF-FIX04 <完成状态>；calendar/year owner 位于 <owner path>。

改了什么：
- <domain owner/API>
- <upload fail-fast/error/LLM schema>
- <download preserved behavior/delegation>
- <README updates>

验证了什么：
- <pytest commands + pass counts>
- <每个生产文件 coverage 百分比，均 >=80%>
- <full pyright result>
- <git diff --check result>
- <zero-side-effect assertions及结果>

未覆盖/风险：
- UF-PF04 未执行，owner=UF-PF04 later work unit。
- 其它 residual risks及分类；若无则明确“无未分类风险”。

Artifacts/commits：
- plan/review/implementation/code-review artifact paths
- accepted slice commit hashes（仅在后续 gate实际产生后填写）

Next entry point：<Gate Order 中下一个未完成 gate>
```

不得把未执行的 `UF-PF04`、未运行命令或未来 slice写成已完成；不得省略 docs decision、finding状态或 residual-risk owner。
