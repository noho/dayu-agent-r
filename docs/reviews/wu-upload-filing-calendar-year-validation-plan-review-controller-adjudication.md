# UF-FIX04 plan review controller adjudication

## Gate record

- Gate: plan review -> fix
- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Reviewed plan: `docs/reviews/wu-upload-filing-calendar-year-validation-plan-codex.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260814-134334.md`（AgentMiMo，`pass-with-risks`）
  - `docs/reviews/plan-review-20260814-135603.md`（AgentDS，`fail`）
- Controller decision: `fix required`
- Completion status: `pass`（findings 已逐项裁决，可以进入 plan fix）
- Next entry point: plan fix by AgentCodex
- Artifact path: `docs/reviews/wu-upload-filing-calendar-year-validation-plan-review-controller-adjudication.md`

## Controller contract decisions

1. fiscal year / download year-only / download year-month 的 year 合法域是非 bool 的 `1000..9999` 整数；这是用户原始目标显式给定的闭区间，不是从 oracle 文案推断。
2. full calendar date 的 year 不继承 fiscal-year 下界：严格 `YYYY-MM-DD` 且为实际公历日期即可，合法域由 Python `datetime.date` 的 `0001..9999` 与 strict round-trip共同决定。因此 `0999-12-31` 是合法 full date。
3. download wrapper 继续拥有 raw shape：year-only 与 year-month 的 year 部分调用 shared year owner；full-date先按 wrapper shape canonicalize，再调用 shared full-date owner。
4. upload filing 的 strict raw-date contract适用于 CLI 与 `start_fins_upload` filing branch。两个入口都不得在 domain admission 前 strip / 折叠 date；material branch保持原行为。
5. upload usage message 对 CLI 与 LLM tool 只使用一份业务中立、自解释文本，不包含 `--flag` 语法；禁止增加两套 channel-specific message owner。
6. `upload_filings_from` 的 metadata strip parity 不在用户授权 scope内，本 work unit不修改；README 必须把 strict 规则准确限定到直接 `upload_filing` / filing tool admission，避免虚假承诺。

## Finding adjudication

### AgentMiMo 01 — `parse_calendar_year(JsonValue)` API 过宽

- Decision: `accepted`
- Reason: upload/download direct consumer 都产生 `int`；required shared parser 应采用窄 `int` signature并仍显式拒绝 bool。raw JSON decode 由同 owner 模块的 optional normalizer先做类型 narrowing，再委托 required parser，不能把宽 raw JSON contract暴露为 required year API。
- Required fix: plan改为 `parse_calendar_year(value: int, ...) -> int`，精确说明 `normalize_fiscal_year(JsonValue | None)` 的 narrowing/delegation与测试。

### AgentMiMo 02 — `1000..9999` 缺少直接裁决

- Decision: `rejected-with-reason`
- Reason: 用户原始目标第 2 条逐字明确 fiscal-year 必须为 `1000 至 9999`；goal confirmation 也已确认。无需再次询问。
- Plan correction: 可补直接引用用户目标，不能把该范围写成推断。

### AgentMiMo 03 — download full-date canonicalize 步骤易遗漏

- Decision: `rejected-with-reason`
- Reason: 原 plan §6 已精确写出补零 canonical text 后调用 owner，§11 已包含 `2024-2-9` 回归；finding没有证据证明 plan 欠规格。

### AgentMiMo 04 — CLI test file跨 S2/S3

- Decision: `rejected-with-reason`
- Reason: S3 明确依赖 accepted S2，Gateflow按 slice 顺序实施/commit；同一文件在后续 slice追加独立 download regression是有序演进，不存在并行 merge ownership冲突。

### AgentMiMo 05 — read runtime 回归缺口

- Decision: `accepted`
- Reason: `normalize_fiscal_year` 的唯一直接生产 consumer 是 `read_runtime.py`；收紧 owner会改变 durable read fail-closed行为，必须有 consumer-level回归而不仅是 owner unit test。
- Required fix: 把相关 read-runtime test file列入相应 slice allowed files与 validation/coverage集合，断言合法值不变、非法历史 year明确 fail closed。

### AgentMiMo 06 — service_runtime 文件定位

- Decision: `rejected-with-reason`
- Reason: plan §4 已给出完整 path/function，且 implementation不修改 `service_runtime.py`；不应为了导航把未修改文件放入 allowed production files。

### AgentDS 1 — tool path strip 与 strict admission矛盾

- Decision: `accepted`
- Reason: `_optional_nullable_text` 在 domain owner之前 strip，直接使同一 raw date在 CLI/tool产生不同结果。
- Required fix: S2允许 `upload_tools.py` 为 filing branch两个 date字段使用不 strip、不把空白折叠为 None 的窄 raw reader；material/date其它消费者保留原 helper。tool tests必须覆盖 empty/blank/padded whitespace、invalid calendar、zero observation/job/executor side effects。

### AgentDS 2 — full date被 fiscal year范围过度耦合

- Decision: `accepted`
- Reason: 用户只给 fiscal-year `1000..9999`；full date contract是 strict ISO + actual Gregorian date。`0999-12-31`满足该 contract。
- Required fix: `parse_iso_calendar_date` 不调用 `parse_calendar_year`；只验证 strict ASCII `YYYY-MM-DD` shape、`datetime.date`真实性和 exact round-trip。download year-only/year-month仍调用 `parse_calendar_year`，download full-date调用 date owner。

### AgentDS 3 — coverage测量集不可达

- Decision: `accepted`
- Reason: reviewer按原 plan命令实测 `filing_semantics.py` 仅 63%，与 >=80% gate矛盾。
- Required fix: 为每个修改生产文件定义能覆盖其完整文件的明确测试集合；`filing_semantics.py` 可组合现有真正覆盖该模块其它 functions 的 tests，不得用当前 4 文件集合假定达标，也不得为了 coverage 添加无关产品行为。每个 slice的 coverage completion signal必须配套可执行命令。

### AgentDS 4 — affected test file存在预先失败

- Decision: `accepted`（事实）；reviewer建议的 fixture顺手修复不接受
- Reason: 失败与 UF-FIX04 calendar/year contract无同链路关系，用户明确禁止处理其它 upload finding，不能把 UF-FIX01 fixture repair混入当前 work unit。
- Required fix: plan记录基线失败的精确 test id与 owner=`UF-FIX01 follow-up`；S2新增/受影响 cases必须单独全绿。实现后仍运行完整文件以确认失败集合没有新增或扩散，并如实记录同一 baseline failure；若失败集合变化，停止并裁决。

### AgentDS 5 — tool outcome 暴露 CLI flag文案

- Decision: `accepted`
- Reason: `str(FinsUploadUsageError)` 直接进入 LLM-facing tool outcome；新增/修改文案不能使用 CLI-only `--flag` 术语。
- Required fix: `INVALID_FISCAL_YEAR`、`INVALID_FILING_DATE`、`INVALID_REPORT_DATE` 使用同一业务中立中文 message，字段名/含义自解释且不含 `--`。CLI也消费同一 message；不增加 channel-specific重复映射。schema与 outcome tests同步断言。

### AgentDS 6 — `upload_filings_from` 仍 strip metadata date

- Decision: `deferred-with-owner`
- Owner/destination: later `upload_filings_from metadata strictness parity` work unit；不创建/修改 issue。
- Reason: 用户当前授权明确限定 UF-FIX04 的 `upload_filing` 与 download shared owner，且禁止处理其它 finding。batch script generation不执行本 work unit的 storage mutation，但其 raw normalization parity需要单独 goal/behavior裁决。
- Required plan note: non-goals/residual risks/README scope必须记录该入口未改变，不能把 direct admission规则泛化成所有 batch generation行为。

### AgentDS 7 — `normalize_fiscal_year` consumer表述不准确

- Decision: `accepted`
- Reason: 直接 consumer只有 `read_runtime.py`；processor/pipeline是 fiscal facts producer，不能写成 parser consumer。
- Required fix: 更正 direct evidence、blast radius与 tests路径。

## Validation evidence adjudication

- AgentDS 的原 plan四文件 baseline运行发现一个稳定预存失败：`tests/fins/test_fins_ingestion_tools.py::test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`。分类：`assigned to later work unit`，owner=`UF-FIX01 follow-up`。
- AgentDS 的 `tests/fins + tests/cli` 扩大基线还出现其它失败，但该命令不在 accepted plan scope，且 shell pipeline掩盖了 pytest exit code；不得把它作为当前 gate pass/fail证据。实现后 controller只接受不掩盖 exit code的命令结果。
- 受影响新 cases、owner tests、download regressions、read-runtime regressions、pyright、diff check和单文件 coverage必须各自有可判定 exit code。

## Residual risks

- `UF-PF04`真实 CLI evidence：`assigned to later work unit`，owner=`UF-PF04`。
- 其它 upload findings：`assigned to later work unit`，owner=`UF-FIX01/02/03/05...`。
- `upload_filings_from` raw-date parity：`assigned to later work unit`，owner=`upload_filings_from metadata strictness parity`。
- 预存 tool fixture failure：`assigned to later work unit`，owner=`UF-FIX01 follow-up`；本 work unit必须证明没有新增或扩散。
- 当前没有 unclassified residual risk。

## Required re-review state

AgentCodex必须产出 plan fix artifact并直接修订原 plan；随后 AgentMiMo与AgentDS都要 re-review。只有全部 accepted findings状态为`已修复`、deferred/rejected裁决被忠实保留且无新 blocker，才能创建 accepted plan commit。
