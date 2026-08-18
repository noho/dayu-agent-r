# UF-FIX04 aggregate adversarial deepreview（AgentDS）

- 审查类型：current changes（UF-FIX04 聚合 dual deepreview 之一，与 MiMo 并行独立执行）
- 审查时间：2026-08-14T16:15:57+0800
- Work unit：`UF-FIX04 shared-calendar-year-validation`
- Branch：`codex/upload-filing-oracle`
- Base：`f609a4d8238c6b31456c2e1d548079b22b771a68`（accepted plan）
- HEAD：`0dfc9f34`（S3 accepted 提交）
- 审查输入：`AGENTS.md`（与 `CLAUDE.md` 同源）、goal confirmation artifact、accepted plan、plan-review/rereview adjudication、S1/S2/S3 全部 implementation/review/rereview/adjudication artifacts、`f609a4d8..HEAD` 完整生产/测试/README diff、`dayu/fins/domain/filing_semantics.py` / `dayu/fins/download_contract.py` / `dayu/fins/ingestion_runtime.py` / `dayu/fins/tools/upload_tools.py` / `dayu/fins/tools/read_runtime.py` / `dayu/fins/service_runtime.py` / `dayu/service/fins_direct.py` / `dayu/cli/commands/fins.py` 相关段落全文
- 排除范围：`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 等冻结 evidence（只核对未改，不审查内容）；MiMo 并行 aggregate artifact（保持双路独立性，未读取）
- 审查动作：只读。未修改生产代码或测试，未 stage、未 commit。

## 结论

**Findings：2 个低严重度，无中/高/严重。** UF-FIX04 的核心目标全部达成且有直接证据支撑，聚合状态可以 close：

- 唯一 calendar/year owner 位于 `dayu.fins.domain.filing_semantics`；upload static admission 与 download wrapper 均直接委托同一 owner（代码调用 + monkeypatch 委托 spy 双证据）；
- 非法 `fiscal_year` / `filing_date` / `report_date` 在 workspace state read、operation/observation/job 创建、runner/converter 与 durable storage mutation 之前被 typed usage error 拒绝；direct CLI、direct tool、direct runtime 三个入口全部收敛到同一 `_filing_upload_request_identity -> _validate_fins_upload_filing_static` 路径，Service 层类型边界只接受 `ValidatedFinsUploadFilingRequest`，不存在 raw admission 旁路；
- download full-date 公历域 `0001..9999` 与 partial year `1000..9999` 解耦正确；`YYYY` / `YYYY-M[M]` / `YYYY-M[M]-D[D]` shape、外围空白 strip、inclusive 展开、真实月末与 start/end ordering 全部由 wrapper/range owner 保持，无回归；
- batch `upload_filings_from` 与 `upload_material` 的既有 strip/normalize 行为未被误改；
- read path 对历史非法 durable fiscal year fail closed，三个 `_parse_source_document_meta` 调用点均不会吞掉 owner `ValueError`；
- 测试为 owner 级 contract 断言；除 F2 指出的调用次数固化外，未发现 fake/mock 固化偶然行为；
- 两份 README 与代码逐句一致；coverage amendment 已由 controller artifact 正式收束，替换集合真实可达且四个非 CLI 文件零改动；
- scope/frozen 完整：tracked diff 精确为 plan 允许文件，冻结 registry/evidence 未改，`UF-PF04` 未执行（verified-by-absence）。

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `f609a4d8`
- Included scope：`f609a4d8..HEAD` 全部 3 个 accepted slice 提交（35 个 tracked 文件），逐文件核对：
  - 生产：`dayu/fins/domain/filing_semantics.py`、`dayu/fins/ingestion_runtime.py`、`dayu/cli/commands/fins.py`、`dayu/fins/tools/upload_tools.py`、`dayu/fins/download_contract.py`
  - 测试：`tests/fins/test_fiscal_normalization_contracts.py`、`tests/fins/test_read_runtime_semantic_ownership_guards.py`、`tests/fins/test_fins_ingestion_runtime.py`、`tests/fins/test_fins_ingestion_tools.py`、`tests/cli/test_fins_commands.py`
  - 文档：根 `README.md`、`dayu/fins/README.md`
  - 治理：goal/plan/S1-S3 全部 artifacts 与 adjudications
- Excluded scope：冻结 oracle/scenario/evidence JSON；`docs/gateflow/` 历史 plan 文档（含已废弃 `FILING_DATE_TOO_LONG` 引用，非代码、非 LLM-facing，无需处理）
- Parallel review coverage：无 subagent，全部由主 reviewer 逐行走读；MiMo 为并行独立 reviewer，其 artifact 由 controller 裁决。

## 验证复核（本机独立执行）

| 声明 | 复核命令 | 复核结果 | 一致 |
| --- | --- | --- | --- |
| S1 focused owner/direct-consumer tests | `pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q` | `98 passed, 3 warnings`，exit 0 | ✅（与 S1 re-review 记录一致） |
| Runtime 完整文件 | `pytest tests/fins/test_fins_ingestion_runtime.py -q` | `258 passed, 3 warnings`，exit 0 | ✅（与 S2 re-review 记录一致） |
| CLI 完整文件 | `pytest tests/cli/test_fins_commands.py -q` | `124 passed, 3 warnings`，exit 0 | ✅（与 S3 implementation 记录一致） |
| Tool 完整文件（真实失败集合） | `pytest tests/fins/test_fins_ingestion_tools.py -q` | exit 1；唯一失败节点 `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`（预存 UF-FIX01 baseline），`82 passed` | ✅（失败集合与 S2 baseline 精确相等） |
| `filing_semantics.py` 可达 coverage | 三文件集合（含 `test_sec_pipeline_download.py`）+ `--fail-under=80` | `211 passed`；`141` statements、`18` missed、**87%** | ✅ |
| `download_contract.py` 可达 coverage（amendment 集合） | 五文件集合 + `--fail-under=80` | `458 passed`；`330` statements、`38` missed、**88%** | ✅ |
| `dayu/cli/commands/fins.py` coverage | 同一五文件集合 + `--fail-under=80` | `469` statements、`68` missed、**86%** | ✅ |
| 全量 pyright | `python -m pyright dayu/ tests/ utils/` | exit 0，`0 errors`（仅新版提示） | ✅ |
| Diff integrity | `git diff --check` | exit 0，无输出 | ✅ |
| 非 CLI coverage consumer 零改动 | `git diff f609a4d8...HEAD -- tests/service/ tests/cli/test_output.py tests/README.md dayu/README.md dayu/fins/domain/__init__.py docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` | 无输出 | ✅ |
| 冻结文件与工作树 | `git status --short` | 仅存在两个 aggregate review artifacts（ds/mimo），无其它改动 | ✅ |

三条 pytest warning 均来自 `.venv` 中 `edgar` deprecated imports，与改动无关。

## Findings

### F1-未修复-低-download public DTO 的非补零日期错误文案被静默统一，S3 审查记录的“wording 原样保留”只对第一分支成立

- **入口/函数**: `dayu/fins/download_contract.py::_parse_optional_iso_date`；消费者为 `FinsDownloadEffectiveFilters.__post_init__`（`download_contract.py:236-237`）与 `FinsDownloadDocumentResult.__post_init__`（`download_contract.py:284-285`）
- **文件(行号)**: `dayu/fins/download_contract.py:841-861`（函数体）、`858-861`（唯一 try/except message 分支）；对照 accepted plan `docs/reviews/wu-upload-filing-calendar-year-validation-plan-codex.md:201`（§6 要求“`_parse_optional_iso_date` 继续拥有 download public DTO 的文本安全和错误 wording”）；S3 DS 审查记录 `wu-upload-filing-calendar-year-validation-s3-deepreview-ds.md:70`（声称“try 内只把 owner 的 `ValueError` 重抛为同一 exact message（861 行原文保留）”）
- **输入场景**: 程序化构造 public DTO 时传入非补零但可被 Python 3.11 `date.fromisoformat` 解析的日期，如 `FinsDownloadEffectiveFilters(start_date="2024-2-9")`，或 source adapter 以 provider 原始非补零文本构造 `FinsDownloadDocumentResult(filing_date="2024-2-9")`；同类还包括 3.11 才接受的 basic format `20240229` 与 week-date
- **实际分支**: baseline 代码对非补零日期走 `parsed.isoformat() != value` 分支，抛 `ValueError(f"{field_name} must use canonical ISO format")`；新代码删除该分支，统一委托 `parse_iso_calendar_date` 后只抛 `ValueError(f"{field_name} must be an ISO date")`（`download_contract.py:859-861`）
- **预期行为**: plan §6 承诺 `_parse_optional_iso_date` 保留既有错误 wording；若 wording 统一是委托 shared owner 的必然结果，应作为 contract 变更显式记录并由 controller 裁决，而不是由实现静默吸收
- **实际行为**: “must use canonical ISO format” 分支被删除且无任何 artifact 记录该 wording 变更；S3 审查结论“错误类型和用户可见 message 与 baseline 一致”对该输入类不成立（错误类型 `ValueError` 不变，接受集不变，但 message 文本改变）
- **直接证据**: 1) baseline `git show f609a4d8:dayu/fins/download_contract.py` 中第二分支原文存在；2) 当前代码 `download_contract.py:856-861` 只有一个 message；3) 全仓 grep `canonical ISO format` 零残留，无测试锁定旧文案、无 consumer 按 message 区分（`_parse_optional_iso_date` 仅两个 `__post_init__` 消费者，均只传播异常）；4) plan §6 原文与 S3 DS review 第 70 条记录与代码不完全一致
- **影响**: 仅提示文案精度下降——适配器作者失去“需要补零 canonical 格式”的定向提示；生产主链不受影响（`FinsDownloadEffectiveFilters` 在正常下载流程中只接收 `FinsDownloadDateRange.start_text` 产生的 canonical 文本，用户输入走 `_parse_date_bound` 的 download usage 文案；`FinsDownloadDocumentResult` 的错误只在 adapter 开发/测试时可见）。无状态写入、无错误吞没、无接受集变化
- **建议改法和验证点**: owner-boundary 修复在控制层：controller 在聚合裁决 artifact 中正式记录该 wording 统一为委托 shared owner 的预期 contract 变更（不恢复双文案、不新增 compat 分支），并修正后续引用 S3 审查“wording 一致”表述的准确性。验证点：裁决 artifact 明确引用 plan §6 与 `download_contract.py:856-861`；新增一个 public DTO 非补零日期测试锁定统一后的 exact message `start_date must be an ISO date`，防止未来 wording 再次静默漂移
- **修复风险（低）**: 只写裁决/补一个 DTO 级 message 测试，不触碰生产代码与冻结 evidence
- **严重程度（低）**:

### F2-未修复-低-owner 委托测试用静态校验调用次数固化内部结构，而非锁定 owner contract

- **入口/函数**: `tests/fins/test_fins_ingestion_runtime.py::test_filing_calendar_year_static_admission_accepts_boundaries_and_delegates`
- **文件(行号)**: `tests/fins/test_fins_ingestion_runtime.py:1770-1771`
- **输入场景**: 任何未来合法重构——例如 `prevalidate_fins_upload_filing_request_for_workspace` 内去重一次静态校验（`_filing_upload_request_identity` 与 `validate_fins_upload_filing_request` 目前各执行一遍 `_validate_fins_upload_filing_static`），或 CLI 预校验路径改为复用已缓存静态结果
- **实际分支**: 测试断言 `year_calls == [fiscal_year, fiscal_year, fiscal_year, fiscal_year]` 与 `date_calls == ["2024-02-29"] * 8`——精确锁定“两个 prevalidate 调用 × 每个调用两次静态校验 × 两个日期字段”的内部调用结构
- **预期行为**: 该测试的 owner contract 是“upload 静态 admission 把年份与完整日期委托 shared owner、值原样传递、合法边界年与闰日进入 state-aware path、identity 稳定”。这些已由 `year_calls`/`date_calls` 的值内容、`first.document_id == second.document_id`、`first.request is request` 独立证明
- **实际行为**: 调用次数 4/8 与 owner contract 无关，是当前实现偶然结构；若未来把静态校验结果缓存复用（不改变任何对外语义与零副作用保证），该测试会无 contract 变化地失败，形成“旧测试固化偶然行为、倒逼生产代码保留重复校验”的约束——与 AGENTS.md 语义所有权条款中“禁止让测试固化偶然行为”的边界相邻
- **直接证据**: 1) 生产代码 `prevalidate_fins_upload_filing_request_for_workspace`（`dayu/fins/service_runtime.py:80-94`）先 `_filing_upload_request_identity` 再 `validate_fins_upload_filing_request`，两者各自调用静态校验；2) 测试 1770-1771 行的精确倍数是该双重校验 × 两次调用的直接投影；3) plan §9 只要求“monkeypatch/spy 证明 static path 调用 owner”，未要求锁定调用次数
- **影响**: 仅测试维护性——未来合理的实现去重会被旧测试倒逼回退或改测试；不影响当前正确性，不是 fake 固化业务结果的严重形态（spy 调用真实 owner 而非 fake 返回值，这一点是正确的）
- **建议改法和验证点**: 把断言改为“值内容 + 每类字段至少一次委托”的 contract 形式（如 `assert year_calls == [fiscal_year] * 2` 之前先记录 `assert set(year_calls) == {fiscal_year}`、`assert len(year_calls) >= 2`，`assert date_calls.count("2024-02-29") >= 2`），或在测试 docstring 中显式声明“调用次数为当前双重静态校验结构的锁定点，去重时必须同步修改本测试”并交由 controller 裁决是否接受该锁定。验证点：修改后 full runtime 文件与 focused tests 仍全绿
- **修复风险（低）**: 只改测试断言，不触碰生产代码
- **严重程度（低）**:

## Adversarial failure pass 逐项记录（按用户指定审查问题逐条回答）

1. **非法 `filing_date` / `report_date` / `fiscal_year` 穿透任一 direct upload_filing 入口、状态读取、operation/observation/job、runner/converter、source meta/manifest/storage 的路径：未发现穿透路径。**
   - CLI 入口：`_prevalidate_upload_filing_request`（`dayu/cli/commands/fins.py:683-707`）在 `FINS_DIRECT_SERVICE_FACTORY` 调用前构造 request 并执行 `prevalidate_fins_upload_filing_request_for_workspace`；后者第一行 `_filing_upload_request_identity`（`dayu/fins/service_runtime.py:80`）即触发静态校验，之后才构造 `FsFilingUploadStateRepository` 并 read state。日期原值直传（`fins.py:694-695`），CLI 不再 strip/折叠。
   - Tool 入口：`_upload_request_from_arguments` filing 分支用 `_optional_raw_nullable_text`（`dayu/fins/tools/upload_tools.py:312-313, 337-363`），字符串原样进入 runtime；`FinsUploadToolCallable` -> `prepare_observed_upload` -> `_validate_runtime_upload_request`（`dayu/fins/ingestion_runtime.py:4203-4235`）同样先 identity 再 read state/建 observation。
   - Direct runtime 入口：`start_upload` / `prepare_observed_upload`（`ingestion_runtime.py:4148-4179, 3339-3375`）均在 job/observation 创建前执行同一验证。
   - Service 层：`FinsDirectCommandService.upload_filing`（`dayu/service/fins_direct.py:280-297`）签名只接受 `ValidatedFinsUploadFilingRequest`，raw request 无法从类型边界进入，不存在第四入口。
   - 静态校验内部顺序：year/date 位于 period 之后、file existence probes（`FILE_NOT_FOUND` 等）与 `build_sec/cn_filing_ids` 之前（`ingestion_runtime.py:895-912`），且优先级测试用“非法日期 + 确认缺失的文件”锁定。
   - converter/runner/source meta/manifest/storage：全部位于 validated request 之后（runner 只接收 validated request），zero-side-effect 测试用“调用即 `AssertionError`”的 forbidden repository/runner、`_HoldingExecutor` 与 workspace SHA-256 快照证明不可达。
2. **upload/download 重复日历解析或 owner semantic mismatch：未发现。** `grep fromisoformat|dt.date|monthrange` 于 `download_contract.py` 仅剩 wrapper-owned 展开构造（`dt.date(year, 12, 31)` / `dt.date(year, 1, 1)` / `calendar.monthrange`，均在 `parse_calendar_year` 校验之后，且为 plan 明确裁决的 wrapper-owned partial 展开语义）。upload 侧只调用 owner 两个函数；`normalize_fiscal_year` 的唯一生产直接 consumer 仍为 `read_runtime._parse_source_document_meta`（`dayu/fins/tools/read_runtime.py:627`），无第二套 year 规则。
3. **download full-date `0001..9999` 与 partial `1000..9999` 解耦、year/month/full-date/inclusive/order 保持：全部通过。** full-date 分支（`download_contract.py:808-813`）补零后只调用 `parse_iso_calendar_date`，不调用 `parse_calendar_year`；`parse_iso_calendar_date` 无任何 1000 下界（`filing_semantics.py:368-397`）。委托 spy 证明 partial 请求只走 year owner、full-date 请求在 year_calls 不变的同时只走 date owner；`("0001-1-1", "0999-12-31")` 正向、`("0999","0000","0999-12","0000-1")` 拒绝、`2024-2 -> 2024-02-29` 闰年月末、外围空白 canonicalization、`FinsDownloadDateRange.__post_init__`（`download_contract.py:580-590`）ordering exact message 全部由本机 124 例 CLI 全绿复核。
4. **direct CLI/tool raw admission 而 batch/material 不误改：通过。** `upload_material` CLI 分支（`fins.py:726-737`）与 tool material builder（`upload_tools.py:327-337`）继续使用 `_optional_stripped_text` / `_optional_nullable_text`，material 回归测试锁定 `" 2024-02-29 " -> "2024-02-29"`。`upload_filings_from`（`fins.py:303-389`）仍走 `_optional_stripped_text` 与 batch plan，未触碰 strict admission。已知中间态（batch strip 后生成 direct 命令）在 plan §14 与三份 implementation artifact 中均记录为 `assigned to later work unit`（owner=`upload_filings_from metadata strictness parity`），README 亦明确不覆盖该入口——无遗漏。
5. **read invalid durable year fail closed：通过。** `normalize_fiscal_year` 对 `999/10000/bool/"2025"` 抛 owner `ValueError`；`_parse_source_document_meta` 三个调用点（`read_runtime.py:2415, 2554, 3061`）前两个只 catch `FileNotFoundError`、第三个无 catch，`ValueError` 全部向上传播，不会被忽略或默认化。S1 回归测试直接断言该行为。
6. **跨层/类型/docstring/LLM 文案：通过，一处既有模式说明。** 无 Host/Engine/Service/storage/converter/pipeline 生产文件改动；`dayu.runtime` 未触碰。新增函数均有完整中文 Args/Returns/Raises docstring；全量 pyright `0 errors`。tool schema 对 filing 分支自足说明四位整数、实际 Gregorian 日期与 raw whitespace 非法，三条 usage message 业务中立、不含 `--` 且 CLI/tool 同源（`_USAGE_MESSAGES` 单一 owner）。`_optional_raw_nullable_text` 的非字符串报错为英文 `"filing_date must be a string or null"` 且原样投影进 `ToolFailedOutcome`——这与 `_ingestion_tool_helpers` 全部既有参数 helper（`ticker`/`fiscal_year` 等 8 条英文文案）同一样式，属于工具 adapter 边界既有模式而非本 work unit 新引入的漂移，不作为 finding。
7. **测试是否遗漏边界或用 fake 固化：边界覆盖充分；fake 固化仅 F2 的调用次数锁定一处。** 正负矩阵覆盖 `1000/9999` 边界、闰日、世纪非闰年、`0000/0001/9999/10000` 年份域、空白/非补零/错误分隔符/非 ASCII 数字；forbidden fakes 只用于断言“不可达”（调用即失败），spy 全部调用真实 owner 而非 fake 返回值；zero-side-effect 同时断言 state/observation/job/executor/runner/workspace 快照五个面；validation priority、delete action、material 回归、closed code mapping 与 message 精确文本均已锁定。download 侧 S3 DS review 记录的 `_parse_date_bound` empty/too-long 分支 missed line 为 pre-existing 缺口，本机五文件集合复核确认不影响 88% gate。
8. **README 与代码一致：通过。** 根 README download 段（`1000..9999` partial / `0001..9999` full-date / 一至两位月日 / 首尾空白 / 真实月末闰年 / 补零显示）与 `_parse_date_bound` + `start_text` 逐句对应；upload 段精确限定 direct `upload_filing` / `start_fins_upload` filing 分支并排除 `upload_filings_from`；`dayu/fins/README.md` 的 domain owner、download wrapper 职责分界与 direct admission 三段与生产代码一致，未写 work unit 流水账或未来能力。`tests/README.md` 与 `dayu/README.md` 按各自触发边界正确未改。
9. **coverage amendment 合理：合理。** 本机独立复现 plan §12 CLI-only 集合对 `download_contract.py` 只能到 63%，amendment 集合（CLI + runtime + Service direct/wait + output 五个既有消费者文件）实测 `458 passed` / `88%`，四个非 CLI 文件相对 base 零改动，为凑门槛短暂新增的两个非目标测试 grep 零残留。S3 审查 F1（缺 controller 裁决 artifact）已由 `wu-upload-filing-calendar-year-validation-s3-review-controller-adjudication.md` 正式 amendment 关闭：记录了 63% 不可达事实、替换集合、零修改约束与“历史 accepted plan 不回写、amendment supersede”的治理关系。聚合复核确认该裁决 artifact 存在且内容与实现证据一致。
10. **scope/frozen/UF-PF04：通过。** tracked diff 精确为 plan §7 允许的 5 生产 + 5 测试 + 2 README 文件；`dayu/fins/domain/__init__.py` 无 re-export；冻结 `docs/cli_ci_oracles.json` / `docs/cli_ci_scenarios.json` 零改动；无 staged changes；`UF-PF04` 无任何执行产出证据，S1/S2/S3 全部 artifact 一致声明未执行，与用户 scope 排除一致（只能 verified-by-absence）。

## 逐 slice 裁决状态复核

- S1：DS-2（message 与 bounds 同源）、DS-3（非 str 防御测试）、DS-4（模块 docstring）已修复并在本机代码中确认（`_CALENDAR_YEAR_RANGE_TEXT` 派生、`cast` 反例测试、模块概览更新）；DS-1（round-trip 防御）controller `rejected-with-reason` 且代码原样保留。裁决闭环有效。
- S2：AgentDS F1（日期校验优先于文件探测未锁定）已修复——`test_validate_fins_upload_filing_request_preserves_validation_priority` 含对称 date case + tmp_path 缺失文件，本机 runtime 全绿复核通过。tool 完整文件唯一失败节点与 baseline 精确相等，本机复核通过。
- S3：AgentDS F1（coverage amendment 缺裁决）由 controller amendment artifact 关闭；MiMo 001（Unicode digit）分类为独立后续 residual（baseline 接受集未变、plan 明令不改 shape），分类合理。
- 遗留 owner 明确项：`UF-PF04`（未执行）、`UF-FIX01 follow-up`（tool 预存失败）、`upload_filings_from metadata strictness parity`、`download date ASCII-shape admission`——均有 owner，无 unclassified 项。

## Open Questions

- 无阻碍 confident judgment 的问题。F1 的边界（是否需要 controller 显式记录 wording 统一）与 F2 的边界（调用次数锁定是否接受）均为低风险治理/维护性判断，已给出建议方向，交 controller 裁决。

## Residual Risk

- `_parse_optional_iso_date` 的 wording 统一未在测试中锁定（F1 验证点提出后即关闭）。
- 静态校验调用次数被测试锁定（F2），未来实现去重时需同步调整测试。
- `_parse_date_bound` empty/too-long 分支在真实可达集合中为 missed line（pre-existing，88% ≥ 80% gate 已达成，不影响本 work unit 结论）。
- `FinsDownloadDocumentResult` 的 DTO 级日期委托未被 spy 直接锁定（helper 级已锁定，pre-existing 调用路径，边际缺口）。
- download shape regex 的 Unicode digit 宽松（controller 已分类为独立后续 residual）。
- `UF-PF04` 真实 CLI evidence 未执行（用户 scope 排除），只能核验“无产出证据”。
- 历史非法 durable fiscal year 读取 fail closed 是有意 contract 收紧，任何存量 workspace 中带非法 year 的 source meta 将不可读——这是 plan §14 明确裁决的预期结果，不做兼容读取。
