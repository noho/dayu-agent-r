# WU-SEMANTIC-OWNERSHIP-01 / R08-S1 Implementation — AgentCodex

## Gate result

- Umbrella：`WU-SEMANTIC-OWNERSHIP-01`
- Remediation：既有 `R08`，slice `S1 producer contracts + all actual processors`
- Gate：implementation / self-check
- Accepted plan commit：`19cbe8a054784297a593cfd6ea823bac40109b99`
- Transition HEAD：`c433b21a881ff10311a3bdf8ac77a583a98184aa`
- Accepted plan SHA-256：`bb37b88b46b2247530d6ce5cafdf875feaee1695a63e7d63f93ada9255e90251`
- Status：`implementation-self-check-blocked`
- Stop：停在 Controller immutable-tree validation 入口之前；未进入 S2、review、fix/re-review 或 commit gate

S1 production 与 owner tests 已实现，focused owner matrix、modified-owner pyright、scoped Ruff、source scans 和 diff check 通过。正式 exact-node pytest/coverage 与逐文件 coverage gate 存在两项无法在 S1 exact allowlist、禁 compatibility/shim/skip/xfail 条件下闭合的 plan-level blocker，详见“Blocking validation evidence”。因此本 tree 不能声明 `implementation-complete`，Controller 不应把它锁定为已通过的 immutable review tree。

## First-principles / owner evidence

问题真实存在，且直接证据与 accepted plan 一致：

- Financial producer contract 同时拥有报表业务事实、locator 和 method/empty 内部诊断；下游会把处理器调用路径误当成 LLM-facing 业务事实。
- XBRL producer 用本地 `len(facts)` 生成 count，同时把可选 filters 放进嵌套对象；这既重复派生事实，也与 consumer 的顶层读取 shape 漂移。
- `sec_fiscal_fields._build_financials_payload` 没有 production caller，却独立生成异常字符串 reason，构成 alternate owner。

S1 正确 owner boundary 是：

- `dayu.fins.domain.financial_result_contract`：financial producer typed contract 与 terminal validation；
- `dayu.fins.domain.xbrl_result_contract`：raw XBRL producer typed contract、flat query params 与 terminal validation；
- actual processors：只负责把 method/source/table 的直接观测映射到上述 contract；
- `sec_fiscal_fields._extract_fiscal_from_xbrl_query`：只消费新 XBRL validator，不生成替代 financial reason。

没有在 read/tool/serializer 下游补默认、重算 count、保留兼容字段或添加临时 adapter。

## Production changes

### Domain owners

- `dayu/fins/domain/financial_result_contract.py`
  - producer result 收敛为七个 required 业务字段：`statement_type`、`periods`、`rows`、`currency`、`units`、`scale`、`data_quality`；
  - `reason` 改为 `NotRequired`，完整结果必须省略，partial 必须存在；
  - reason 闭集收敛为 accepted plan 的七值业务集合；
  - 删除 locator 类型、字段和 validator；
  - top-level result 与 period nested object 均做 exact-key validation；
  - 保留 scale/period direct-evidence quality invariant，并允许其它业务 partial reason 由 actual producer 终端提供。
- `dayu/fins/domain/xbrl_result_contract.py`
  - 新增 `XbrlQueryParams`、`XbrlDataQuality`；
  - 删除 producer count，result 仅保留 `query_params`、`facts`、`data_quality` 与 optional `reason`；
  - query params 改为 flat exact shape，optional filter 缺席时不补 `None`；
  - `fiscal_period` 直接消费 `FiscalPeriod` / `FISCAL_PERIODS`；
  - `min_value` / `max_value` 在接收 `int | float` 前显式拒绝 `bool`，并拒绝非有限 float；
  - result/query-param unknown keys、complete/partial reason matrix、不可用结果夹带 facts 均 fail closed；validator 只复制，不改写 raw payload。

### Actual processors and shared producer logic

- `dayu/fins/processors/sec_processor.py`
  - 删除 locator 与未使用 pandas import；
  - method absent、method return `None`、空 DataFrame、空 rows 统一为 `statement_not_found`；
  - complete financial result 省略 reason；
  - XBRL 输出 flat typed params、无 count、complete result 省略 reason。
- `dayu/fins/processors/bs_report_form_common.py`
  - 与 SEC generic 使用同一 financial/XBRL contract；
  - 删除 locator、内部 method/empty reasons、nested filters 和 count；
  - XBRL failure result 缺业务 reason 时 fail closed，不用 fallback reason 掩盖 invariant。
- `dayu/fins/processors/bs_six_k_processor.py`
  - 删除 base/XBRL result locator；
  - complete/partial reason 按 optional presence 产生；
  - top-level terminal 继续把 XBRL/HTML/OCR 均无结果归一为 `statement_not_found`。
- `dayu/fins/processors/html_financial_statement_common.py`
  - HTML structured result 删除 locator，complete 时省略 reason。
- `dayu/fins/processors/six_k_form_common.py`
  - HTML/OCR 两个 result owner 删除 locator，complete 时省略 reason。
- `dayu/fins/processors/report_form_financial_statement_common.py`
  - HTML fallback reason 只消费 typed `xbrl_not_available | statement_not_found`；删除内部 reasons 与字符串 loose normalization。
- `dayu/fins/processors/sec_xbrl_query.py`
  - 删除 locator helper、其专属 title/period-label/row-label helpers 与引用；
  - fiscal-period 与 number filter 签名传播到共享 typed contract。
- `dayu/fins/processors/financial_base.py`
  - Protocol 的 fiscal period 与 number 参数传播为共享 typed signature。
- `dayu/fins/pipelines/sec_fiscal_fields.py`
  - 删除 `_build_financials_payload`、其专属 protocol/type guard、异常字符串 reason 和无用 timestamp import；
  - fiscal consumer 直接校验无 count 的 XBRL producer result。

`dayu/fins/processors/sec_report_form_common.py` 在 allowlist 中，但当前只机械消费 optional reason，没有旧字段构造或必要类型错误，因此保持零 diff。

## Test changes

- `tests/fins/test_financial_read_contracts.py`
  - financial exact required keys、optional reason presence、七值闭集、unknown/missing/null/quality failures；
  - SEC generic、BS common、BS 10-K/10-Q/20-F inheritance、BS 6-K、HTML、OCR actual producer contract；
  - method absent、return `None`、空表、空 rows 四类 terminal 观测统一；
  - XBRL exact result/query-param keys、flat params、zero-hit、partial reasons、all-concepts-failed typed error；
  - shared fiscal-period values、`True`/`False` rejection、int/float acceptance、optional filter absence；
  - raw payload immutability 与 producer 无 count exact keys。
- `tests/fins/test_sec_pipeline_download.py`
  - 删除只固化 alternate financial owner 的 fixture/assertions；
  - 保留 processed quality 与真实 fiscal precedence/extraction tests；
  - fiscal XBRL fixtures 迁移为 flat、无 count、complete reason 缺席 contract。
- `tests/fins/test_fins_read_runtime.py`
  - 只把旧 fiscal node 改名为 `test_sec_fiscal_inference_consumes_countless_xbrl_contract`，fixture payload 删除 count 并断言 `(2025, "FY")`；
  - 六个 S2 normalize/dedup nodes 与两个 generic LRU/form-matching nodes 零 diff；未添加 skip/xfail/shim。

## Validation command ledger

所有 Python 命令均先执行 `source .venv/bin/activate`。

### Baseline / scope

- `git branch --show-current`：`phaseflow/host-issues-control`。
- `git status --short`：初始为空。
- `git rev-parse HEAD`：`c433b21a881ff10311a3bdf8ac77a583a98184aa`。
- `git rev-parse 19cbe8a054784297a593cfd6ea823bac40109b99^{commit}`：精确返回 accepted plan commit。
- `git merge-base --is-ancestor 28b6fc1956bd3832489a471fa29bfe354b319860 HEAD`：exit 0，R07 completion 在 lineage 中。
- `git merge-base --is-ancestor 19cbe8a054784297a593cfd6ea823bac40109b99 HEAD`：exit 0。
- `shasum -a 256 docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`：匹配 accepted SHA-256。
- `python -m compileall -q <S1 changed Python files>`：pass，无输出。

### Tests

- Focused owner matrix：

  ```bash
  pytest tests/fins/test_financial_read_contracts.py tests/fins/test_sec_pipeline_download.py tests/fins/test_processor_registry.py -k 'financial or statement or xbrl or quality or reason or fiscal'
  ```

  结果：`98 passed, 50 deselected, 3 warnings`。warnings 均为既有 edgar dependency deprecation。

- 不含共享 exact node 的诊断性完整 S1 owner files：

  ```bash
  pytest tests/fins/test_financial_read_contracts.py tests/fins/test_sec_pipeline_download.py
  ```

  结果：`147 passed, 3 warnings`。

- 共享 exact node、正式 S1 pytest 与正式 coverage：均在 collection 阶段因同一 S2 import propagation 失败，详见下一节；没有收集或运行六个 S2 nodes。

### Type / lint / diff

- `pyright <S1 全部实际修改 production 与 test Python files>`：`0 errors, 0 warnings, 0 informations`。
- `pyright`：`5 errors, 0 warnings, 0 informations`；全部位于预声明 S2 production paths，exact ledger 见下节。
- `python -m ruff check <S1 全部实际修改 Python files>`：`All checks passed!`。
- `git diff --check`：pass，无输出。

### S1 scans

- Internal raw-total positive inventory：修正 shell quote 后按 §5.5 owner roots 运行，exit 1 / 零命中；没有可保留 raw/provider/reported total。
- Financial/internal negative scan：exit 1 / 零命中。
- `pytest.mark.skip|pytest.mark.xfail|type: ignore|noqa` scoped bypass scan：exit 1 / 零命中。
- 第一次 positive inventory 命令因 shell 单引号组合错误返回 `zsh: unmatched '`；随后用等价 `\x22/\x27` regex 精确重跑并获得零命中，未把该 shell 错误当成 scan pass。

## Full-pyright exact propagation ledger

| 文件:行 | symbol / rule / exact message | 已删或收窄的 producer contract | S2 owner / exact action |
|---|---|---|---|
| `dayu/fins/tools/read_runtime.py:2095` | financial projection；`reportTypedDictNotRequiredAccess`；`"reason" is not a required key in "FinancialStatementResult", so access may result in runtime exception` | financial `reason` 从 required nullable 改为 optional presence | `read_runtime.py`：S2 机械投影只在 producer field 存在时复制，不补默认 |
| `dayu/fins/tools/read_runtime.py:2096` | financial projection；`reportGeneralTypeIssues`；`"statement_locator" is not a defined key in "FinancialStatementResult"` | 删除 financial producer locator field | `read_runtime.py`：S2 删除 locator projection，改调 single public builder |
| `dayu/fins/tools/read_runtime_helpers.py:1200` | `_normalize_xbrl_query_payload`；`reportAssignmentType`；`Type "dict[str, object]" is not assignable to declared type "dict[str, JsonValue]" ... Consider switching from "dict" to "Mapping" which is covariant in the value type` | 旧 `dict[str, JsonValue]` query-param shape 被 flat typed `XbrlQueryParams` 取代 | `read_runtime_helpers.py`：S2 直接消费/复制 typed params，不从 raw dict 重建 |
| `dayu/fins/tools/read_runtime_helpers.py:1219` | `_normalize_xbrl_query_payload`；`reportAttributeAccessIssue`；`Cannot access attribute "total" for class "ValidatedXbrlFactsResult"; Attribute "total" is unknown` | 删除 XBRL producer count | `read_runtime_helpers.py`：S2 删除 raw count 读取，final public builder 唯一产生 `fact_count` |
| `dayu/fins/tools/result_types.py:27` | domain import；`reportAttributeAccessIssue`；`"StatementLocator" is unknown import symbol` | 删除 producer locator type | `result_types.py`：S2 删除 import/旧 public locator field，建立新 public type |

诊断只落在四个预声明 S2 paths 中的三个：`result_types.py`、`read_runtime_helpers.py`、`read_runtime.py`。`fins_tools.py` 当前无诊断。没有 test、S1 owner 或其它 production path 诊断。

## Blocking validation evidence

### B1 — exact fiscal node 无法在 S1 tree 被 pytest 收集

以下两条正式命令均在 collection 阶段失败：

```bash
pytest tests/fins/test_fins_read_runtime.py::test_sec_fiscal_inference_consumes_countless_xbrl_contract
pytest tests/fins/test_financial_read_contracts.py tests/fins/test_sec_pipeline_download.py tests/fins/test_fins_read_runtime.py::test_sec_fiscal_inference_consumes_countless_xbrl_contract tests/fins/test_processor_registry.py
```

直接传播链：

```text
test_fins_read_runtime.py
-> dayu.fins.tools.cache（先执行 dayu.fins.tools.__init__）
-> provider -> fins_tools -> read_runtime -> search_engine
-> read_runtime_helpers -> result_types
-> import 已删除的 producer locator type
-> ImportError before node collection
```

exact error：`ImportError: cannot import name 'StatementLocator' from 'dayu.fins.domain.financial_result_contract'`。

这与 full-pyright ledger 的 `result_types.py:27` 是同一 S2 direct propagation。可行修复只有：

1. 进入 S2 修改 `result_types.py` / tools import chain；或
2. 在共享 test 文件为 S1 添加条件/lazy import 临时 seam；或
3. 保留兼容 producer type。

三条都被当前 gate 禁止：第一条越过 S1 stop，后两条是 test/production shim 或 compatibility。六个 S2 nodes 与 generic nodes 不能移动 local imports，四个 S2 production files也不能提前改。因此 B1 需要 Controller 调整 gate sequencing/test collection 方案，AgentCodex 未越界补救。

### B2 — §5.4 formal test set 无法满足逐个实际修改 production 文件 80% line coverage

正式 coverage 命令先因 B1 collection failure 失败。为排除 exact fiscal node 对 processor coverage 的影响，另运行同一正式 owner files、仅暂时去掉该单 node 的诊断 coverage；`147 passed` 后逐文件结果为：

| production file | line coverage |
|---|---:|
| `financial_result_contract.py` | 87% |
| `xbrl_result_contract.py` | 86% |
| `sec_fiscal_fields.py` | 91% |
| `financial_base.py` | 100% |
| `bs_report_form_common.py` | 65% |
| `bs_six_k_processor.py` | 48% |
| `html_financial_statement_common.py` | 59% |
| `report_form_financial_statement_common.py` | 41% |
| `sec_processor.py` | 42% |
| `sec_xbrl_query.py` | 67% |
| `six_k_form_common.py` | 66% |

单一 fiscal node 只执行 `sec_fiscal_fields` consumer，不能把上述 7 个 actual/common processor 文件从 41%–67% 提升到 80%。在只允许三份 S1 tests、正式 coverage 固定只收集这些 tests 的约束下，闭合该门需要为大量未改 processor 行为制造与 R08 owner contract 无关的测试；这会扩大 slice、固化偶然实现并违背 accepted plan 的 owner-level/minimal scope。使用 pragma、omit、aggregate coverage、fake execution 或降低阈值同样被禁止。B2 需要 Controller 改为 modified-line coverage、授权现有 broader processor tests 进入 coverage，或重新裁决整文件 80% gate。

## Changed path manifest

### Production（11 个实际 diff；均在 12-path allowlist）

- `dayu/fins/domain/financial_result_contract.py`
- `dayu/fins/domain/xbrl_result_contract.py`
- `dayu/fins/pipelines/sec_fiscal_fields.py`
- `dayu/fins/processors/bs_report_form_common.py`
- `dayu/fins/processors/bs_six_k_processor.py`
- `dayu/fins/processors/financial_base.py`
- `dayu/fins/processors/html_financial_statement_common.py`
- `dayu/fins/processors/report_form_financial_statement_common.py`
- `dayu/fins/processors/sec_processor.py`
- `dayu/fins/processors/sec_xbrl_query.py`
- `dayu/fins/processors/six_k_form_common.py`

### Tests（3 个实际 diff；精确等于 S1 test allowlist）

- `tests/fins/test_financial_read_contracts.py`
- `tests/fins/test_fins_read_runtime.py`
- `tests/fins/test_sec_pipeline_download.py`

### Artifact

- `docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md`

无 S2 tools、README、control/design、Host、R07 owner 或其它 path diff。未 stage、commit、push 或创建 PR。

## README / docs decision

按 accepted plan §5.1，S1 不改 README；public surface 要到 S2 定型后再同步。唯一新增文档是本 implementation artifact。control/design/plan 均未修改。

## Residual risks / classification

- Full-pyright 5 条 direct propagation：`covered by later approved slice (R08-S2)`；ledger 已精确登记，无其它诊断。
- B1 shared exact-node collection conflict：`requiring explicit Controller decision`；S1 内无无-shim修复路径。
- B2 per-file coverage gate conflict：`requiring explicit Controller decision`；不得用无关测试或 coverage 技巧补救。
- 正式 S1 pytest 与 coverage 未通过，因此 immutable review tree 尚不可锁定：`requiring explicit Controller decision`。
- R09-R12、S2 public projection、README 与 aggregate review：均保持 out of scope，未开始。

没有把上述 blocker 分类为实现已完成或可接受 product state。

## Completion / next entry point

当前完成的是 S1 production/test implementation 与可执行 self-check 证据，不是 S1 gate pass。下一入口必须是 `Controller validation/adjudication of B1+B2`：Controller 先裁决 accepted plan 的 test-collection 与 coverage gate，再决定重开 S1 validation 或调整 sequencing。裁决前不得进入 S2、两路 review、commit 或 PR。

## Final scope / tree handoff

- `git diff --check`：pass，无输出。
- `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-r08-s1-implementation-codex.md`：pass，无输出。
- `git status --short --untracked-files=all`：仅 11 个 production、3 个 tests 为 modified，本 artifact 为 untracked；无其它 path。
- `git diff --cached --name-only`：空，staged tree 未修改。
- 当前 14 个 tracked path 的完整 `git diff --binary` SHA-256：`0d985b85aa65d7c4b06d9ee464cd73fc4a39ef2ee0934f376b0b845a09b20f57`。
- 逐 path 工作树 content hash 已在 handoff 前计算；Controller 必须按 §5.4 在包含本 artifact 的最终 tree 上独立重算 path manifest 与 cumulative diff hash，不能把本节视为 immutable-tree validation pass。
