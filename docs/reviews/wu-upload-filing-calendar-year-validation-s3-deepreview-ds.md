# UF-FIX04 S3 deepreview（AgentDS）

- 审查类型：current changes（独立 dual deepreview 之一）
- 审查时间：2026-08-14T15:58:19+0800
- Branch：`codex/upload-filing-oracle`
- Base：`67c34c0f44bf72ddeea9f1e732808f06245d8044`（S2 accept 提交）
- 审查范围：相对 base 的全部未提交改动（4 个 allowed 文件）+ 新增 S3 implementation artifact
- 审查输入：`AGENTS.md`（与 `CLAUDE.md` 同源）、`docs/reviews/wu-upload-filing-calendar-year-validation-plan-codex.md`（accepted plan）、`docs/reviews/wu-upload-filing-calendar-year-validation-plan-rereview-controller-adjudication.md`、`docs/reviews/wu-upload-filing-calendar-year-validation-s1-rereview-controller-adjudication.md`、`docs/reviews/wu-upload-filing-calendar-year-validation-s2-rereview-controller-adjudication.md`、`docs/reviews/wu-upload-filing-calendar-year-validation-s2-deepreview-ds.md`、`docs/reviews/wu-upload-filing-calendar-year-validation-s3-implementation-codex.md`、`dayu/fins/domain/filing_semantics.py` 全文、`dayu/fins/download_contract.py` 全文、生产/测试/README diff 全文
- 排除范围：`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 等冻结 evidence（核对未改，不审查内容）；MiMo 并行 review artifact（不属于本审查对象）
- 并行审查覆盖：无 subagent，全部由主 reviewer 逐行走读
- 审查动作：只读。未修改生产代码或测试，未 stage、未 commit

## 结论

**Findings（1 个低严重度）**。S3 核心目标全部达成并有直接证据支撑：download 不再自行维护 common year/full-date 合法性（year-only/year-month 委托 `parse_calendar_year`，full-date 补零后只委托 `parse_iso_calendar_date`，public DTO 路径同样委托）；full-date 未套用 fiscal year 下界（`0001..9999` 保持合法）；partial year 拒绝 `0999/0000`；旧 year/year-month/full-date shape、外围空白 strip、真实月末、闰年、显式边界展开与 ordering 全部无回归；public DTO 的 exact error type/message 无漂移；canonicalization 无溢出、无新增非 ASCII 接受、无隐藏规则；测试为 owner 级 contract 断言而非过拟合；两份 README 与代码逐句一致；coverage correction 经本机复现为事实必要且替换集合真实可达。唯一 finding 是 accepted plan §12 的 S3 coverage 命令（CLI-only 对 `download_contract.py` `--fail-under=80`）按字面不可达（本机复现 63%），实现以真实可达五文件集合替换并在 artifact 中声称“控制侧裁决”，但 docs/reviews 中不存在记录该裁决的 controller artifact，需要 controller 在 S3 裁决 artifact 中正式收束（见 F1）。

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `67c34c0f`
- Included scope（相对 base 的 workspace changes）:
  - `dayu/fins/download_contract.py`（+9/-7）
  - `tests/cli/test_fins_commands.py`（+255/-0）
  - `README.md`（+9/-1）
  - `dayu/fins/README.md`（+6/-1）
  - 新增 `docs/reviews/wu-upload-filing-calendar-year-validation-s3-implementation-codex.md`（审查输入）
- Excluded scope: 冻结 oracle/scenario JSON（只核对未改）；S1/S2 已提交生产文件（`filing_semantics.py`、`ingestion_runtime.py`、`cli/commands/fins.py`、`upload_tools.py`）为冻结 owner baseline，只读核对未改
- Parallel review coverage: 无

## 验证复核（本机独立执行，全部与 implementation artifact 声明一致）

| 声明 | 复核命令 | 复核结果 | 一致 |
| --- | --- | --- | --- |
| S3 focused 6 组测试 | `pytest tests/cli/test_fins_commands.py -q -k 'download_date_bounds_preserve... or ...'`（artifact §Validation.1 同一 `-k` 表达式） | `15 passed, 109 deselected, 3 warnings`，exit 0 | ✅ |
| CLI 完整文件 | `pytest tests/cli/test_fins_commands.py -q` | `124 passed, 3 warnings`，exit 0 | ✅ |
| CLI-only coverage（plan §12 字面命令） | `coverage run -m pytest tests/cli/test_fins_commands.py -q` + `coverage report --include='dayu/fins/download_contract.py'` | `330` statements、`122` missed、**63%**；`--fail-under=80` 按字面执行必然 exit 非零 | ✅（证实 correction 必要性） |
| 真实可达五文件集合 | `coverage run -m pytest tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py tests/cli/test_output.py -q` + `coverage report --include='dayu/fins/download_contract.py' --fail-under=80` | `458 passed, 3 warnings`；`330` statements、`38` missed、**88%**，exit 0 | ✅ |
| CLI 生产文件 coverage | artifact §Validation.2（`--include='dayu/cli/commands/fins.py' --fail-under=80`） | `469` statements、`68` missed、**86%**（复读 artifact 与 S2 deepreview 记录；本机未重复执行该命令，S3 未改该文件） | ✅ |
| 全量 pyright | `python -m pyright dayu/ tests/ utils/` | exit 0，`0 errors`（仅新版 pyright 可用提示） | ✅ |
| diff integrity | `git diff --check` | exit 0，无输出 | ✅ |
| allowed 文件集合 | `git diff --name-only 67c34c0f --` | 精确为 4 个 allowed tracked 文件；工作区另有 2 个新增 review artifacts（S3 implementation + MiMo deepreview），无其它改动 | ✅ |
| 冻结 registry/evidence | `git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json` | 无输出，未改 | ✅ |
| 已撤销测试零残留 | `grep test_download_result_contract_derives_counts / test_download_provider_errors_preserve` | 无匹配，两个非目标 coverage 测试已完整撤销 | ✅ |
| UF-PF04 | git status、docs 目录无任何 evidence/artifact 变化 | 无任何被执行迹象；以“无产出证据”核验其未执行 | ✅（verified-by-absence） |
| 未 stage/commit | `git status --short`、`git diff --cached` | 无 staged changes，全部为工作区未提交改动 | ✅ |

## Findings

### F1-未修复-低-accepted plan §12 S3 coverage gate 被实现替换但缺可追溯 controller 裁决 artifact

- **入口/函数**: S3 验证命令集合（accepted plan §10 S3 Tests/validation 与 §12 S3 and aggregate commands）；实现侧偏离记录在 `docs/reviews/wu-upload-filing-calendar-year-validation-s3-implementation-codex.md` §Control-side coverage-set correction
- **文件(行号)**: `docs/reviews/wu-upload-filing-calendar-year-validation-plan-codex.md:453-458`（plan 字面命令与 completion signal）；`docs/reviews/wu-upload-filing-calendar-year-validation-s3-implementation-codex.md:44-57`（偏离说明）；生产/测试未受影响
- **输入场景**: 任何按 accepted plan §12 字面执行 S3 验证的 gate：`coverage erase && coverage run -m pytest tests/cli/test_fins_commands.py -q && coverage report --include='dayu/fins/download_contract.py' --fail-under=80`
- **实际分支**: plan §12 把 `download_contract.py` 的 coverage 集合错误绑定为 CLI 单文件；本机独立复现该字面命令得到 63%（`122/330` missed），`--fail-under=80` 必然 exit 非零——plan 的 completion signal 按字面不可达成。实现侧改为既有消费者五文件集合（CLI + runtime + Service direct/wait + output），本机复现 88% 且 `458 passed`，未修改任何既有测试文件、未用非目标新测试凑数、被中断的 coverage 运行未计入证据
- **预期行为**: plan 不可达的 gate 应通过正式 plan amendment 或 controller adjudication 收束，且裁决内容（替换集合、判定方式、不修改既有测试文件的约束）在 controller artifact 中可追溯
- **实际行为**: implementation artifact 声称“控制侧裁决指出该路径会把错误 coverage 假设转化为 goal drift；裁决成立”，但审查输入中的全部 controller artifacts（plan-review、plan-rereview、S1/S2 各裁决）均无该裁决记录，docs/reviews 中也无对应 controller artifact；S3 implementation 自身仍把该偏离写在 “Control-side coverage-set correction” 一节并称其为修正，而非被正式裁决的 plan amendment
- **直接证据**: 1) plan §12 原文命令与本机 63% 复现（见验证复核表第 3 行）；2) `ls docs/reviews/` 中 UF-FIX04 系列仅 goal-confirmation、plan×2、plan-review/rereview 裁决、S1×3、S2×7、S3 implementation 一个 artifact，无任何 S3/coverage controller 裁决文件；3) plan-rereview 裁决 §Docs decision 与 §Final decision 只覆盖 README 与 slice 顺序，未提及 coverage 集合修正
- **影响**: 治理/审计层面——若该偏离不被正式裁决，plan 的 completion signal 与验证证据之间的差异只能靠实现 artifact 的单方声明闭合，后续 controller/复核无法区分“被裁决的修正”与“绕过 gate 的实现自述”。技术实质已本机验证合理：替换集合全部是既有真实消费者测试文件，88% ≥ 80% 成立，correction 本身不引入 goal drift
- **建议改法和验证点**: owner-boundary 修复在控制层（coverage gate 的 owner 是 controller 对 plan 的裁决，不是实现）：controller 在 S3 裁决 artifact 中正式确认 coverage-set replacement（既有五文件集合、`--fail-under=80`、不得为凑覆盖率修改既有测试文件或新增非目标测试），并同步修正 plan §12 对应行，使 completion signal 与裁决一致。验证点：裁决 artifact 明确引用 plan §12 行号与 replacement 集合；`git show` 复核替换集合各文件在 S3 diff 之外零改动
- **修复风险（低）**: 只写裁决/修正 plan 文本，不触碰生产代码、测试与冻结 evidence
- **严重程度（低）**:

## Adversarial failure pass 逐项记录（按用户指定审查问题逐条回答）

1. **download 是否仍自行校验 common year/full-date**：不再自行校验共同合法性。`_parse_date_bound`（`download_contract.py:771-816`）year-only 分支（799-801）`parse_calendar_year(int(value), field_name=field_name)` 后才做展开；year-month 分支（802-807）同样先委托 year owner；full-date 分支（808-813）构造补零 canonical 文本后只调用 `parse_iso_calendar_date`。public DTO 路径 `_parse_optional_iso_date`（841-861）保留 `_validate_public_text`（transport 安全，download-owned）后只委托 owner。全文件剩余 calendar 构造仅 `download_contract.py:801`（`dt.date(year, 12, 31)` / `dt.date(year, 1, 1)`）与 `806-807`（`calendar.monthrange` + `dt.date`）：两者都在 year 已被 owner 校验之后，属于 plan §5/§6 明确裁决的 wrapper-owned partial inclusive expansion 与真实月末派生语义（`monthrange` 与 owner 使用的 `datetime.date` 同为 stdlib 日历真源，不构成第二套规则）。grep `fromisoformat|dt.date|monthrange` 全文件仅剩上述 3 行，无残留独立 validity 判定
2. **full-date 是否意外套用 fiscal year 下界**：未套用。`download_contract.py:808-813` 分支不调用 `parse_calendar_year`；`parse_iso_calendar_date`（`filing_semantics.py:368-397`）只有 ASCII regex、`datetime.date` 构造与 round-trip，无任何 1000 下界。委托 spy 测试（`tests/cli/test_fins_commands.py:1132-1210`）以 `year_calls == [(1000, "--start"), (2024, "--end")]` 在 full-date 请求后保持不变为直接证据；`("0001-1-1", "0999-12-31") → "0001-01-01"/"0999-12-31"` 参数化 case 通过
3. **partial 是否意外接受 0999**：拒绝。`"0999"` 匹配 `_YEAR_PATTERN`（`^\d{4}$`）→ `parse_calendar_year(999)` 越界抛 `ValueError` → `download_contract.py:814-815` 映射为 exact usage error。`test_download_partial_year_rejects_values_outside_shared_year_domain`（1082-1107）四例（`0999`、`0000`、`0999-12`、`0000-1`）全部断言 exact message `--start 不是有效日期，请使用 YYYY、YYYY-MM 或 YYYY-MM-DD` 且本机 15 例全绿
4. **旧 year/year-month/full-date、外围空白、月末、闰年、显式边界与 ordering 回归**：逐项无回归。(a) shape：`_YEAR_PATTERN`/`_YEAR_MONTH_PATTERN`/`_FULL_DATE_PATTERN`（46-48）diff 未触碰，plan 明令不改；(b) 外围空白：`value = raw_value.strip()`（793）保留，`(" 2024-2-9 ", ...) → "2024-02-09"` case 通过；(c) 月末/闰年：`calendar.monthrange(year, month)[1]`（806）保留，`2024-2 → 2024-02-29` case 通过；(d) 显式边界：`("1000","9999") → 1000-01-01/9999-12-31` case 通过；(e) ordering：`FinsDownloadDateRange.__post_init__`（588-589）未在 diff 中，message `--start 不能晚于 --end，请检查下载日期范围` 由 `test_download_date_range_ordering_remains_owned_by_range_contract`（1274-1290）以 `start="2025"` 展开 `2025-01-01` vs `end="2024-12"` 展开 `2024-12-31` 精确断言。CLI 完整文件 124 passed 且既有 usage matrix（1293-1358）未改
5. **public DTO exact error/type 是否漂移**：无漂移，属本 S3 引入的 contract 保持而非回归。baseline 直接对比：旧 `_parse_optional_iso_date` 为 `date.fromisoformat(value)` + `parsed.isoformat() != value` 时抛 `ValueError(f"{field_name} must be an ISO date")`；新代码（857-861）`_validate_public_text` 仍在 try 外（`TypeError`/transport `ValueError` 行为不变），try 内只把 owner 的 `ValueError` 重抛为同一 exact message（861 行原文保留）。接受集等价性：旧 fromisoformat 的宽松形态（3.11 新增 basic format `YYYYMMDD`、week-date `YYYY-Www-D`）都会被旧 round-trip 检查拒绝，新严格 ASCII regex（`filing_semantics.py:55-59`，`[0-9]{2}` 月日、`fullmatch`）直接拒绝，接受集相同；`2024-2-9`、首尾空白、非闰日等在新旧路径均拒绝。测试 `test_download_public_iso_dates_delegate_shared_full_date_owner`（1213-1272）断言 `ValueError` 且 `match="start_date must be an ISO date"`，并 spy 断言 `[("0001-01-01", "start_date"), ("2024-02-29", "end_date")]` 与 `__post_init__` 调用序（236-237）一致
6. **full-date canonicalization 是否引入溢出/非 ASCII 或隐藏规则**：未引入。(a) 溢出：Python `int` 无溢出，且 `year_text` 已由 `^\d{4}$` 限 4 位（808 分支前置 shape gate），`dt.date` 构造在 owner 内被 `try/except ValueError` 收束；(b) 非 ASCII：`\d` 未加 `re.ASCII` 是 pre-existing wrapper pattern 语义（46-48 行 baseline 未改），baseline 旧代码 `dt.date(int(year_text), ...)` 同样通过 Python `int()` 接受 Unicode 十进制数字（如 `٢٠٢٤`），新旧接受集合完全相同，canonicalization 只把已接受的输入归一为 ASCII 输出，不新增接受面；plan 明令“不改 regex shape”，该收紧不属于 S3 范围；(c) 隐藏规则：补零 `f"{int(...):04d}-{int(...):02d}-{int(...):02d}"` + owner strict regex + `datetime.date` + round-trip，与旧 `dt.date(int, int, int)` 构造的拒绝集合逐类等价（`0000` 年、月 13、日 0、非闰日均拒绝，验证见 `test_download_full_date_rejects_nonexistent_calendar_dates` 1109-1130 四例全绿）
7. **测试是否过拟合**：不过拟合。三个价值型参数化测试（1051、1082、1109）只断言 public 输出（`start_text`/`end_text`）与 exact usage message，不碰内部实现；两个委托 spy（1132、1213）的 record wrapper 调用真实 owner 而非 fake 返回值，断言的是 plan §10 S3 要求的“同源”契约本身（调用值、field_name、full-date 不调 year owner），正是 owner-boundary 测试该锁定的内容；`test_download_date_range_ordering_remains_owned_by_range_contract` 断言 range owner 的 exact message 而非重算顺序。未发现用 fake/mock 固化偶然行为、倒逼兼容分支的断言
8. **README 是否准确**：逐句对照代码，全部准确。(a) 根 README download 段（+261-267）：`1000..9999` partial year ↔ 799-800/803-804 + `parse_calendar_year`；完整日期 `0001..9999` ↔ 808-813 不调 year owner；月日一位或两位 ↔ `_FULL_DATE_PATTERN` `\d{1,2}`；忽略首尾空白 ↔ 793 strip；校验真实月末与闰年 ↔ 806 monthrange + owner `datetime.date`；统一补零显示 ↔ `isoformat()`（602/615）；(b) 根 README upload 段（+316-322）：严格 admission 规则与 S2 accepted 生产代码一致（`cli/commands/fins.py:694-695` 原值直传、`upload_tools.py:312-313` `_optional_raw_nullable_text` 仅 filing 分支），且明确限定 direct `upload_filing`/`start_fins_upload`、排除 `upload_filings_from`，符合 plan §13“不泛化”；(c) `dayu/fins/README.md`（+524、+545、+650）：domain owner 职责（`1000..9999` / `0001..9999` 解耦、非 bool）与 `filing_semantics.py:344-397` 一致；download wrapper 段落与生产逐项一致；direct admission 段落与 S2 代码一致。两份 README 更新均符合各自 `Agent更新约束`（根 README 只写用户可见规则，未写内部模块/治理；Fins README 只写稳定开发者边界，未写 work unit 流水账）
9. **coverage correction 是否合理**：合理且必要，本机独立复现（63% vs 88%，见验证复核表）。plan §12 的 CLI-only 绑定对 `download_contract.py` 不可达是 plan 事实错误，实现侧的替换集合全部是仓库既有、真实到达 `download_contract.py` 的消费者测试文件且零修改；为凑门槛临时加入的两个 result/provider 测试已完整撤销（grep 零残留）。唯一缺口是裁决可追溯性，见 F1
10. **只有允许文件、frozen 未改、UF-PF04 未执行**：全部核对通过。`git diff --name-only 67c34c0f --` 精确等于 4 个 S3 allowed 文件；`docs/cli_ci_oracles.json` / `docs/cli_ci_scenarios.json` 无任何改动；工作区无 staged changes；UF-PF04 无任何产出证据（verified-by-absence），且 S1/S2/S3 全部 artifact 一致声明未执行

## Open Questions

- 无。阻碍 confident judgment 的问题为零；F1 的边界（技术实质已验证合理、仅缺 controller 裁决 artifact）有直接证据支撑。

## Residual Risk

- **pre-existing wrapper shape pattern 的 Unicode digit 宽松**：`_YEAR_PATTERN`/`_YEAR_MONTH_PATTERN`/`_FULL_DATE_PATTERN`（`download_contract.py:46-48`）使用无 `re.ASCII` 的 `\d`，Unicode 十进制数字可进入 int 转换；baseline 行为相同（接受集不变），S3 未触碰且 plan 明令不改 shape，不构成本 slice finding。若未来要收紧，owner 边界在 wrapper pattern（加 `re.ASCII`），建议单独 work unit。
- **`_parse_date_bound` 空/过长分支未覆盖**：`download_contract.py:794-797`（empty 与 too-long usage error）在本机全部可达集合中均为 missed line（pre-existing，S3 diff 未触碰；文件级 88% ≥ 80% gate 已达成）。属于既有测试缺口，不影响本 slice 结论。
- **`FinsDownloadDocumentResult` 委托路径未被 spy 锁定**：`filing_date`/`report_date`（`download_contract.py:284-285`）与 `FinsDownloadEffectiveFilters` 共用同一 `_parse_optional_iso_date` helper，helper 级委托已锁定；DTO 级路径为既有调用，边际覆盖缺口，非 S3 引入。
- **`UF-PF04` 真实 CLI evidence**：未执行（按用户要求），owner=`UF-PF04` later work unit；本审查只能核验“无产出证据”，不能正向证明未执行。
- **S2 遗留项**（owner 已记录，不重复报 finding）：`upload_filings_from` metadata strip parity（batch 生成 strip、direct 执行严格拒绝的中间态）、tool 完整文件唯一 UF-FIX01 baseline failure、S2 的 file-probe 顺序锁定已在 S2 re-review 关闭。
- **coverage correction 的裁决记录**：见 F1，controller 在 S3 裁决 artifact 中正式收束后即可关闭。

## Review 依据文件索引

- 生产：`dayu/fins/domain/filing_semantics.py`（S1 冻结 owner，46-59、344-397、400-422）、`dayu/fins/download_contract.py`（31-48、196-240、556-615、658-701、771-816、841-861、903-920）、`dayu/cli/commands/fins.py`（664-700，只读核对 upload raw 直传）、`dayu/fins/tools/upload_tools.py`（38、257-330，只读核对 filing raw reader）
- 测试：`tests/cli/test_fins_commands.py`（1039-1290 新增六组、1293-1358 既有 usage matrix）
- 文档/裁决：`docs/reviews/wu-upload-filing-calendar-year-validation-plan-codex.md`（§5、§6、§10 S3、§12、§13）、plan-fix、plan-rereview-controller-adjudication、s1/s2-rereview-controller-adjudication、s2-deepreview-ds、s3-implementation-codex；`README.md`（9-23、261-271、316-329）、`dayu/fins/README.md`（16-26、521-525、542-547、645-651）
