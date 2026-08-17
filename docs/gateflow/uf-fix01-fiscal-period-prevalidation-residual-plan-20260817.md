# UF-FIX01 fiscal-period prevalidation residual — Implementation Plan

## Gate 元数据

- work unit：`UF-FIX01-fiscal-period-prevalidation-residual`
- gate：`plan`
- 日期：2026-08-17
- goal artifact：`docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-goal-confirmation-20260817.md`
- current gate：`accepted plan`
- next entry point：`S1 implementation`
- completion status：`accepted`
- artifact path：`docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-plan-20260817.md`

## 1. Goal / motivation / success signal

### Goal

修复 filing upload 的 fiscal-period 静态 admission 残余：所有市场和所有 filing upload raw request
入口都必须由同一 Fins domain owner 执行首尾空白清理、大小写归一化和封闭域校验，只接受
`FY`、`H1`、`Q1`、`Q2`、`Q3`、`Q4`。

### Motivation

`UF-A21-us-invalid-period` 直接证明 US `BANANA` 被当前 market branch 放过静态 admission，进入
operation 后才以 exit 1、`runtime/unexpected_runtime` 收口。该输入在读取 workspace state、创建
Service/operation/observation/job 或 converter/storage mutation 前即可判定，故必须作为 typed usage
failure 返回 exit 2 和可行动原因。

### Success signals

1. `dayu.fins.domain.filing_semantics` 是 fiscal-period 字面量集合、canonicalization 和校验的唯一 owner。
2. CLI 与 `start_fins_upload` tool 构造的 `FinsUploadFilingRequest`、US/CN/HK ticker 全部经过同一个
   market-neutral static admission；adapter/workflow 不解析 raw period。
3. 六个 canonical 值及其小写/混合大小写、首尾空白输入得到同一 canonical `FiscalPeriod`。
4. 非法非空值产生 `FinsUploadUsageCode.UNSUPPORTED_FISCAL_PERIOD` 与精确 reason
   `--fiscal-period 仅支持 FY、H1、Q1、Q2、Q3、Q4`；不保留旧 CN/HK 专用 code/文案。
5. CLI 对 US/CN/HK 非法值均 stdout 为空、stderr 只有一行具体 usage reason、无 traceback、exit 2；
   Service factory/stream/operation 不启动，业务 workspace tree 不变。
6. tool/raw runtime 非法值不创建 observation/job，不调用 runner/converter/storage mutation；合法行为、
   action/publication 与其它 failure projection 不变。
7. focused tests、修改文件 coverage、受影响回归和全仓 pyright 通过。

## 2. First-principles judgment and direct evidence

- 业务事实只有一个：fiscal period 是否属于当前封闭集合，以及其 canonical 文本。按市场分别解析没有业务依据；
  US、CN、HK filing upload 持久化的是同一 `FiscalPeriod` 语义。
- `filing_semantics.py::normalize_fiscal_period` 已经执行 `strip().upper()` 并校验 `FISCAL_PERIODS`；
  创建新 parser 或在 CLI/tool 各自重复判断都会扩大真源。
- `ingestion_runtime.py::_validate_fins_upload_filing_static` 在
  `_filing_upload_request_identity`、workspace state read、runtime producer/job/observation 之前运行，是 domain
  error 到 upload typed usage error 的正确直接上游 projection boundary。
- 当前该函数对 CN/HK 调用 pipeline `normalize_cn_fiscal_period`，对 US 只做 `strip().upper()`；这与 evidence
  中 CN/HK exit 2、US exit 1 的市场差异同源。
- `docling_upload_service.py::normalize_cn_fiscal_period` 复制同一字面量集合；它不是 market adapter 必需事实，
  `derive_report_kind` 可直接消费 domain owner。
- CLI `_prevalidate_upload_filing_request` 与 tool `_upload_request_from_arguments` 最终都构造
  `FinsUploadFilingRequest`，无需在两个入口添加业务判断。
- Host/Engine design 明确不拥有财报业务语义；本修复不触及 Host/Engine。

## 3. Design document alignment

- `docs/host/design.md`：Host 不承载财报业务语义、不直接管理财报仓储规则；因此不在 Host admission、ToolRuntime
  或 error ingest 增加 fiscal-period 分支。
- `docs/engine/design.md`：Engine 只执行单次 Agent/Runner/tool loop，不解释工具业务参数；因此不修改 tool schema
  transport、Runner 或 Engine failure state machine。
- 项目分层：CLI 仅投影 Fins typed usage failure；Service 仅传递 validated request；Fins domain 产生业务语义，
  Fins ingestion admission 投影 upload usage contract。
- 文档存取仍只通过 `dayu.fins.storage`；本轮在任何 storage read/mutation 之前失败，不新增仓储接口。

## 4. Semantic owner and exact data flow

### Unique owner

- 业务 owner：`dayu/fins/domain/filing_semantics.py`
  - `FiscalPeriod`
  - `FISCAL_PERIODS`
  - `normalize_fiscal_period`
- usage projection owner：`dayu/fins/ingestion_runtime.py::_validate_fins_upload_filing_static`
  - 只负责 required/length admission 顺序与 domain `ValueError` 到 closed `FinsUploadUsageError` 的映射；
  - 不维护 period 集合、不按市场判断。

### Data flow

```text
CLI upload_filing / start_fins_upload filing
  -> FinsUploadFilingRequest(raw fiscal_period)
  -> _filing_upload_request_identity
  -> _validate_fins_upload_filing_static
  -> normalize_fiscal_period (唯一业务 owner)
  -> ValidatedFinsUploadFilingRequest.normalized_fiscal_period
  -> SEC or CN/HK workflow 机械消费 canonical value
```

非法路径在 `normalize_fiscal_period -> FinsUploadUsageError` 结束，不进入 workspace state read、Service factory、
operation/observation/job、converter 或 publication。

## 5. Contract / schema / state-machine / public-interface changes

### Changed closed contract

- `FinsUploadUsageCode.UNSUPPORTED_CN_FISCAL_PERIOD` 删除。
- 新增 `FinsUploadUsageCode.UNSUPPORTED_FISCAL_PERIOD = "unsupported_fiscal_period"`。
- `_USAGE_MESSAGES` 使用 market-neutral 精确文案：
  `--fiscal-period 仅支持 FY、H1、Q1、Q2、Q3、Q4`。
- 不提供旧 enum 名称、旧值或旧文案的 re-export/alias/compatibility mapping。

### Type strengthening

- `_StaticFinsUploadFilingValidation.normalized_fiscal_period` 与
  `ValidatedFinsUploadFilingRequest.normalized_fiscal_period` 改为 `FiscalPeriod`，使 validated request 的
  canonical contract 由类型表达。
- upload 专用 `docling_upload_service.build_cn_filing_ids`、`build_sec_filing_ids` 与
  `derive_report_kind` 的 period 参数同步收窄为 `FiscalPeriod`；三者只消费 canonical typed value，
  不再执行 strip/uppercase 或 domain revalidation。CN download 自有的
  `cn_form_utils.build_cn_filing_ids` 属于独立 download owner，不在本轮修改。
- raw `FinsUploadFilingRequest.fiscal_period` 保持 `str | None`，因为它位于 admission 之前。

### Unchanged contracts

- CLI 参数名/requiredness、tool schema enum/参数、Service method、storage schema、document ID 算法、action/
  overwrite/repair/publication state machine、exit 0/1 行为保持不变。
- missing period 与 overlong period 的既有 code/message/validation priority 保持不变。
- download filter aliases 继续由 `parse_fiscal_period_filter_value` 拥有；不收窄别名集合。

## 6. Implementation decisions

1. `ingestion_runtime` 直接 import `FiscalPeriod` 与 `normalize_fiscal_period`，不再 import pipeline
   `normalize_cn_fiscal_period`。
2. `_validate_fins_upload_filing_static` 保持既有顺序：ticker → source/action/count → year → period required →
   period length → period domain → dates → company/files → identity。domain 调用传入 raw period，让唯一 owner 完成
   strip/uppercase；异常只映射为通用 usage code。
3. exact domain-error mapping 固定为：

   ```python
   try:
       normalized_period = normalize_fiscal_period(request.fiscal_period, field_name="--fiscal-period")
   except ValueError:
       _raise_upload_usage(FinsUploadUsageCode.UNSUPPORTED_FISCAL_PERIOD)
   if normalized_period is None:
       raise AssertionError("required fiscal_period owner 返回缺失值")
   ```

   required/length check 仍先执行；domain `ValueError` 不得逃逸为 runtime failure。
4. 删除 `docling_upload_service.normalize_cn_fiscal_period` 及其 `__all__` export，不保留透传 wrapper。
   `derive_report_kind`、`build_cn_filing_ids`、`build_sec_filing_ids` 直接消费 `FiscalPeriod`；删除两个 ID
   builder 内的 `strip().upper()`，不在 lower consumer 重做 owner 规则。
5. CLI 与 tool production 不增加 fiscal-period 解析；测试从它们的现有公共入口证明共享 admission。CLI/tool
   通用文本 helper 可能在 request 构造前 strip，入口测试只声明“最终 request 共享 canonical contract”；raw
   whitespace 的业务 owner 行为由 owner contract test 直接证明。
6. 测试 assertion 绑定 owner contract、closed code/message、canonical request 与零副作用，不从日志或偶然文件反推。

## 7. Slice S1 — shared owner and market-neutral admission

### ID / objective / expected outcome

- ID：`S1-owner-admission`
- Objective：消除 market-specific/duplicate parser，让 validated filing request 只可能携带 canonical
  `FiscalPeriod`，非法值在 workspace read 前成为通用 typed usage failure。
- Expected outcome：owner、usage code/message、admission、CN report-kind consumer 同源；不涉及 CLI 展示特例。

### Allowed files/modules

- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `tests/fins/test_fiscal_normalization_contracts.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/cli/test_fins_commands.py`（仅同步现有 UF-024 exact reason，不新增 S2 cases）
- `docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-s1-implementation-20260817.md`

### Prerequisites

- accepted plan commit 存在。
- 工作树除当前 slice 文件和 Gateflow artifact 外无不明改动。

### Exact allowed changes

1. 不修改 `filing_semantics.py` production；在 owner tests 参数化断言：
   - 六个 canonical 值原样返回；
   - 小写/混合大小写和首尾空白 canonical 化；
   - `None`/空白保持 optional owner 的 `None` 语义；
   - `BANANA`、`9M`、相近但非法值抛 `ValueError`，reason 绑定 field name。
2. 将 usage enum/message 改为通用名称和精确 market-neutral reason；更新 closed code set、exact message tests、
   现有 CLI UF-024 exact reason，并删除所有旧 enum/value/message 断言。
3. 将两个 `normalized_fiscal_period` 字段、两个 upload ID builder 参数与 `derive_report_kind` 参数标注为
   `FiscalPeriod`；合法 ID 对既有 canonical 输入保持完全相同。
4. static admission required/length check 后按 §6 exact try/except 调用 `normalize_fiscal_period`；所有 market 共享
   同一分支；domain error 映射为 `UNSUPPORTED_FISCAL_PERIOD`，`None` fail closed 为 invariant breach。
5. 删除 pipeline duplicate parser/export；删除两个 upload ID builder 的 strip/uppercase；`derive_report_kind` 只从
   typed canonical period 投影 annual/semi_annual/quarterly；更新该模块既有测试。
6. ingestion owner contract 参数化 US/CN/HK ticker：六个合法值及 normalization 得到 canonical 值；非法值均取得同一
   code/message；用 forbidden published-state read/repository seam 或直接 `_filing_upload_request_identity` 证明非法值先于
   workspace state read。

### Invariants / error handling

- 不捕获 owner 之外的异常为 usage error。
- 不改变 missing/overlong priority；overlong 仍先返回原 code。
- 不让 `None`、空白或非法字符串进入 ID builder。
- build SEC/CN IDs 只消费 canonical typed period，算法输出对合法既有输入不变。
- 不按 `normalized_ticker.market` 选择 parser。

### Non-goals

- 不改 CLI/tool production、Service、workflow adapter、material、download aliases、storage/publication。
- 不增加新的通用 value-object/parser class。

### Validation commands / expected assertions

```bash
source .venv/bin/activate
pytest tests/fins/test_fiscal_normalization_contracts.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_docling_upload_service.py \
  tests/cli/test_fins_commands.py -q
python -m pyright dayu/fins/domain/filing_semantics.py \
  dayu/fins/ingestion_runtime.py \
  dayu/fins/pipelines/docling_upload_service.py \
  tests/fins/test_fiscal_normalization_contracts.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_docling_upload_service.py \
  tests/cli/test_fins_commands.py
```

Expected：全部通过；pyright 0 errors；以下扫描在 `dayu tests` 无命中（历史 docs artifacts 除外）：

- `normalize_cn_fiscal_period`
- `UNSUPPORTED_CN_FISCAL_PERIOD` / `unsupported_cn_fiscal_period`
- `CN/HK --fiscal-period 仅支持`
- upload 专用两个 ID builder 内的 fiscal-period `strip().upper()`。

### Completion signal / stop condition

- implementation artifact 记录 changed files、owner contract、validation、docs decision、classified risks。
- 若删除 duplicate parser 发现非 upload consumer 依赖其不同语义，停止并回到 plan amendment；不得保留 wrapper。

## 8. Slice S2 — entry-point, market parity, zero-side-effect and docs proof

### ID / objective / expected outcome

- ID：`S2-entry-contracts-docs`
- Objective：从 CLI 与 tool 两个实际入口证明 US/CN/HK 一致的 exit/reason/no-start/no-mutation，并同步稳定文档。
- Expected outcome：UF-A21 的产品 contract 被确定性测试覆盖，不依赖真实 calibration。

### Allowed files/modules

- `tests/cli/test_fins_commands.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_service_runtime.py`（仅当 tool/runtime observation-before-start 需要现有 seam）
- `dayu/fins/tools/upload_tools.py`
- `README.md`
- `dayu/fins/README.md`
- `tests/README.md`
- `docs/gateflow/uf-fix01-fiscal-period-prevalidation-residual-s2-implementation-20260817.md`

### Prerequisites

- S1 accepted slice commit 存在。
- 通用 usage code/message 和 market-neutral admission 已通过 S1 review/re-review。

### Exact allowed changes

1. 扩展 CLI usage matrix，至少覆盖：
   - US `AAPL/BANANA`、CN `600519/9M`、HK `0700.HK/BANANA`；
   - 精确 exit 2、stdout 空、单行通用 reason、无 `Traceback`；
   - Service factory、upload stream 调用列表为空；
   - fresh/seeded workspace before/after snapshot 完全一致。
2. 增加 CLI 合法 normalization contract：至少一个 US 和 CN/HK 输入携带小写与首尾空白，送入 fake Service 的
   `ValidatedFinsUploadFilingRequest.normalized_fiscal_period` 为 canonical；不得在 CLI 实现归一化测试专用分支。
3. 扩展 tool/start upload contract：
   - raw tool arguments 的小写/空白 period 经 runtime validation 后 canonical；
   - US/CN/HK 非法 period 形成现有 tool failure envelope 中的具体 usage reason；
   - forbidden runner/executor/observation/job/converter seam 保持零调用，workspace tree 不变。
4. 若现有 tool harness 只断言 observation 不启动，则在最窄的现有 runtime/service test seam 补充；不创建新 fake framework。
5. 把 tool schema 的 `fiscal_period` description 改为自足闭集说明：只支持
   `FY、H1、Q1、Q2、Q3、Q4`，并保持 filing 必填/material 可选的现有 requiredness；在现有 schema contract test
   增加 exact assertion。schema 不从 runtime enum 反向拼装，也不新增兼容 alias。
6. 根 README 增补 direct filing fiscal-period 闭集、normalization、非法 exit 2/no operation 的用户可见行为。
7. `dayu/fins/README.md` 在现有 domain owner/static admission 段写明 period 同源与 market-neutral contract。
8. `tests/README.md` 在现有 Fins/CLI 测试职责段记录新增的 fiscal-period owner/entry/zero-side-effect 覆盖；不写用例流水账。

### Invariants / error handling

- CLI 只渲染 owner 已产生的 failure，不检查 market/period。
- tool schema 只做 LLM-facing 完整闭集说明；tool runtime 仍消费同一 raw request validator，不在 schema adapter 校验。
- no-start 证明必须使用显式记录/forbidden seam，不以“没有某行日志”替代；no traceback 作为额外公开输出断言。
- workspace snapshot 排除测试自身输入 fixture，只比较业务 workspace。
- 合法 period 的 action、document ID、publication 与 summary 不变。

### Non-goals

- 不运行真实 CLI、Docling 或网络 calibration。
- 不修改 accepted oracle/scenario/evidence。
- 不处理 `upload_filings_from` 或 material metadata。
- 不改 CLI error catcher/renderer、US/CN/HK workflow adapter。

### Validation commands / expected assertions

```bash
source .venv/bin/activate
pytest tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_service_runtime.py -q
pytest tests/fins/test_fiscal_normalization_contracts.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_docling_upload_service.py \
  tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_fins_service_runtime.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

Coverage：用 `coverage run -m pytest` 运行上述 affected tests，随后执行：

```bash
coverage report \
  --include='dayu/fins/ingestion_runtime.py,dayu/fins/pipelines/docling_upload_service.py,dayu/fins/tools/upload_tools.py' \
  --fail-under=80
```

这三个文件是 plan 允许修改的最终 production 集合；`filing_semantics.py` production 不修改，因此不为本 work unit
扩展其无关 sec-form/date/quality 测试来追逐整文件覆盖率。

Expected：测试全部通过；非法三市场 exact exit/reason/no-start/no-mutation/no-traceback；合法 normalization 同源；
全仓 pyright 0 errors/warnings/informations；diff check 通过。

### Completion signal / stop condition

- implementation artifact 和双路 code review artifacts 完整，accepted findings 已 fix/re-review。
- 若 tool 路径不经过 shared validator 或需要改变 public schema，停止并回到 plan amendment；不得在 tool adapter 复制规则。

## 9. Plan/review/commit sequencing

1. 两路 `$planreview` 并行审查本 artifact。
2. controller 裁决 findings；AgentCodex 修 plan；两路 re-review。
3. 无 blocking finding 后创建 `gateflow: accept plan for UF-FIX01 fiscal-period prevalidation residual`。
4. 实施 S1 → 两路 `$deepreview` code review → fix/re-review → accepted S1 commit。
5. 实施 S2 → 两路 `$deepreview` code review → fix/re-review → accepted S2 commit。
6. 两路 aggregate `$deepreview` → fix/re-review → accepted deepreview commit。
7. 用户明确不创建 PR、不 push；记录 draft-PR gate waived by explicit user scope，直接执行本地 final closeout。

## 10. Docs decision

- `dayu/fins/` 与 `tests/` 会修改，必须读取并遵守各 README 的更新约束；当前稳定 owner/admission 和测试职责属于其范围，
  预期更新 `dayu/fins/README.md`、`tests/README.md`。
- 用户可见 CLI exit/reason/no-start contract 改变，属于根 README 职责，预期更新 `README.md`。
- 分层和装配未变，不更新 `dayu/README.md`。
- Host/Engine 未修改，不更新 `dayu/host/README.md`、`dayu/engine/README.md`。

## 11. Risks / open questions / residual risks

### Open questions

无 blocking open question。

### Classified residual risks

- 外部 UF-PF01/UF-PF12 calibration 未运行：`assigned to later work unit`，owner 为用户后续 calibration 流程。
- frozen evidence/oracle/scenario 未刷新：`assigned to later work unit`，由用户明确排除。
- material fiscal metadata 未统一：`assigned to later work unit`；material 不是 required filing identity contract。
- download 财期别名仍多于 filing closed values：已由独立 filter owner 有意承诺，不是 defect；记录为
  `rejected-with-reason`，不进入实现。
- 旧 durable 非法 fiscal period 的兼容读取：schema 规则要求全新设计且用户未要求升级，`assigned to later work unit`。
- AgentCodex plan turn 两次无产出停滞：workflow execution risk，已由 controller durable artifact 收口；不影响产品语义。
- AgentCodex plan-fix turn 也发生同类无工具调用停滞；controller 仅机械落实已裁决 amendment，re-review 负责独立验证。

## 12. Why this is not overdesigned

方案复用一个已有 domain helper和一个已有 static admission，只删除重复 parser、替换一个 closed usage member，并在
现有测试矩阵/README 段落补 contract。没有新增层、protocol、factory、callback、schema、migration、registry 或兼容 shim；
两个 slice 分别隔离语义 owner 与入口证据，足以 review 又不把同一小改动拆成文件级碎片。

## 13. Completion report format

最终 closeout 必须明确：

- 改了什么：owner、closed usage contract、shared admission、删除的 duplicate parser、测试/README。
- 验证了什么：focused/affected/full regression、coverage、全仓 pyright、diff check，并列 exact 结果。
- finding status：两路 plan/code/aggregate review 每个 accepted finding 的 fix/re-review 终态。
- docs decision：实际更新与未更新原因。
- remaining risks/owners：只列已分类项。
- exclusions：未运行 UF-PF01/UF-PF12，未改 evidence/oracle/scenario，未 push/PR。
- commits：accepted plan、各 slice、accepted deepreview 和 final closeout commit hash。
- next entry point：用户后续可执行 focused/full-real calibration；本 work unit 到 `final closeout pass`。
