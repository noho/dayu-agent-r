# UF-FIX04 S2 deepreview（AgentDS）

- 审查类型：current changes（独立 dual deepreview 之一）
- 审查时间：2026-08-14T15:18:52+0800
- Branch：`codex/upload-filing-oracle`
- Base：`e5d4394ab29ce5d8ec7db0f3aa6bb3c262696c12`（S1 accept 提交）
- 审查范围：相对 base 的全部未提交改动（6 个生产/测试文件）+ 新增 S2 implementation artifact
- 审查输入：`AGENTS.md`（与 `CLAUDE.md` 同源）、`docs/reviews/wu-upload-filing-calendar-year-validation-plan-codex.md`、`docs/reviews/wu-upload-filing-calendar-year-validation-plan-rereview-controller-adjudication.md`（即 plan-accepted 裁决；不存在名为 `plan-accepted.md` 的文件）、`docs/reviews/wu-upload-filing-calendar-year-validation-s2-implementation-codex.md`、生产代码全文走读、测试 diff 全文走读
- 排除范围：`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 等冻结 evidence（核对未改，不审查内容）；MiMo 并行 review artifact（不属于本审查对象）
- 并行审查覆盖：无 subagent，全部由主 reviewer 逐行走读
- 审查动作：只读。未修改生产代码或测试，未 stage、未 commit

## 结论

**Findings（1 个低严重度）**。S2 核心目标全部达成并有直接证据支撑：非法 `fiscal_year` / `filing_date` / `report_date` 在 workspace state read、operation/observation/job 创建、runner/converter 调用与 storage mutation 之前被 typed usage error 拒绝；未发现任何能让非法值穿过静态 admission 或产生 durable/operation side effect 的路径。唯一 finding 是 plan 明确承诺的 date-vs-file-probe 顺序未被测试锁定（测试缺口，无安全后果，见 F1）。

## Scope

- Mode: current changes
- Branch: `codex/upload-filing-oracle`
- Base: `e5d4394a`
- Included scope（相对 base 的 workspace changes）:
  - `dayu/fins/ingestion_runtime.py`（+44/-5）
  - `dayu/cli/commands/fins.py`（+2/-2）
  - `dayu/fins/tools/upload_tools.py`（+35/-3）
  - `tests/fins/test_fins_ingestion_runtime.py`（+387/-6）
  - `tests/fins/test_fins_ingestion_tools.py`（+306/-2）
  - `tests/cli/test_fins_commands.py`（+88/-3）
- Excluded scope: 冻结 oracle/scenario JSON（只核对未改）；`docs/reviews/wu-upload-filing-calendar-year-validation-s2-implementation-codex.md` 为审查输入而非审查对象
- Parallel review coverage: 无

## 验证复核（本机独立执行，全部与 implementation artifact 声明一致）

| 声明 | 复核命令 | 复核结果 | 一致 |
| --- | --- | --- | --- |
| runtime 完整文件 | `pytest tests/fins/test_fins_ingestion_runtime.py -q` | `256 passed, 3 warnings` | ✅ |
| CLI 完整文件 | `pytest tests/cli/test_fins_commands.py -q` | `109 passed, 3 warnings` | ✅ |
| tool 完整文件 | `pytest tests/fins/test_fins_ingestion_tools.py -q` | `82 passed, 1 failed`，唯一失败节点 = baseline `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` | ✅ |
| runtime coverage | `coverage report --include='dayu/fins/ingestion_runtime.py' --fail-under=80` | `2188` statements，`202` missed，**91%**，exit 0 | ✅ |
| CLI coverage | `coverage report --include='dayu/cli/commands/fins.py' --fail-under=80` | `469` statements，`68` missed，**86%**，exit 0 | ✅ |
| tool coverage（精确 deselect 唯一 baseline node） | `coverage report --include='dayu/fins/tools/upload_tools.py' --fail-under=80` | `102` statements，`9` missed，**91%**，exit 0 | ✅ |
| 定向 pyright（6 文件） | `python -m pyright ...`（implementation artifact §Validation.8 同一集合） | `0 errors, 0 warnings, 0 informations`，exit 0 | ✅ |
| diff integrity | `git diff --check` | exit 0，无输出 | ✅ |
| 冻结 registry/evidence | `git status --short` | 仅 6 个 allowed 文件 + S2/MiMo review artifacts；`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 未改 | ✅ |
| UF-PF04 | git status、docs 目录、无任何 evidence/artifact 变化 | 无任何被执行迹象；以“无产出证据”核验其未执行 | ✅（verified-by-absence） |
| 未 stage/commit | `git status --short` | 全部为工作区未提交改动 | ✅ |

## Findings

### F1-未修复-低-date admission 先于 file existence probe 的顺序未被测试锁定

- **入口/函数**: `_validate_fins_upload_filing_static`（`dayu/fins/ingestion_runtime.py:855`）；关联优先级测试 `test_validate_fins_upload_filing_request_preserves_validation_priority`（`tests/fins/test_fins_ingestion_runtime.py:1489-1522`）
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:911-916`（date check 在 911-912，file probes 在 916-926）；测试缺口在 `tests/fins/test_fins_ingestion_runtime.py:1536-1649`、`tests/cli/test_fins_commands.py:1159-1265`、`tests/fins/test_fins_ingestion_tools.py:1092-1278`
- **输入场景**: 同一请求同时包含非法 `filing_date`/`report_date` 与不存在的文件路径（例如 `filing_date="2024-13-01"` 且 `files=(Path("missing.pdf"),)`）。这是唯一能判别 date check 与 file existence probe 先后顺序的输入形态
- **实际分支**: 当前实现先执行 `_validate_optional_upload_iso_date`（`ingestion_runtime.py:911-912`），后执行 `file_path.exists()`/`is_file()` 探测（`ingestion_runtime.py:919-921`），因此该输入报 `INVALID_FILING_DATE` 而非 `FILE_NOT_FOUND`
- **预期行为**: 顺序本身已按 plan 正确实现；plan §10 S2 Invariants 同时要求该顺序“**并用测试锁定**”
- **实际行为**: 顺序未锁定。全部三个文件的新增负向矩阵均使用 `action="delete"` 且无 `files`（runtime 矩阵 `tests/fins/test_fins_ingestion_runtime.py:1545-1620` 的每个 request 都只有 ticker/action/year/period/date；CLI 矩阵同理全部带 `--action delete`；tool 矩阵 base arguments 为 `"action": "delete"`），永远不会走到 file probes；`test_validate_fins_upload_filing_request_preserves_validation_priority` 的优先级矩阵只有 ticker→year→period→files 四个槽位，没有 date 槽位。若未来有人把 date check 移到 file probes 之后，整个测试套件仍然全绿
- **直接证据**: 1) plan §10 S2 invariant 原文：“为更强的确定性，放在 period 后、file checks 前并用测试锁定”；2) 三个测试文件中 grep `filing_date=`/`report_date=` 与 `files=` 的组合用例为零；3) 优先级测试参数表（`test_fins_ingestion_runtime.py:1490-1507`）确认只有 6 个 case、无 date 槽位
- **影响**: 仅错误优先级回归风险，无安全或副作用影响——file probes 是只读文件系统探测，workspace state read / operation / runner / durable mutation 的零副作用边界已被 `_ForbiddenFilingUploadStateRepository`（读即 AssertionError）、`_HoldingExecutor.operations == []`、`_ForbiddenUploadRunner.requests == []`、`runtime._observations == {}` 与 workspace tree byte-for-byte 快照独立锁定，不受本缺口影响。最坏后果是双非法请求的报错文案从“日期非法”变成“文件不存在”，属于 UX 优先级回归
- **建议改法和验证点**: owner-boundary 修复在测试层（顺序契约的 owner 是 admission 边界，锁定测试属于同一 owner 的 contract 断言）：在 `test_validate_fins_upload_filing_request_preserves_validation_priority` 的矩阵中新增一例 `(FinsUploadFilingRequest(ticker="AAPL", fiscal_year=2024, fiscal_period="FY", files=(Path("missing.pdf"),), filing_date="2024-13-01"), FinsUploadUsageCode.INVALID_FILING_DATE)`（report_date 对称一例），断言 date 错误优先于 `FILE_NOT_FOUND`。验证点：新增 case 全绿；把 date check 临时移到 file probes 后该 case 必须失败（mutation 验证可选）
- **修复风险（低）**: 只新增测试，不触碰生产代码；不影响现有 256/109/82 计数与三个 coverage 百分比
- **严重程度（低）**:

## Adversarial failure pass 逐项记录（未发现可通过的非法路径）

1. **非法 fiscal_year 穿入 workspace state read**：不可能。`prevalidate_fins_upload_filing_request_for_workspace`（`service_runtime.py:80`）先调 `_filing_upload_request_identity` → `_validate_fins_upload_filing_static`（year check 在 `ingestion_runtime.py:895-898`），后才构造 `FsFilingUploadStateRepository` 并 read（`service_runtime.py:82-86`）。runtime 路径 `_validate_runtime_upload_request`（`ingestion_runtime.py:4223-4229`）同样先 identity 后 read。bool（`fiscal_year=False`）、`0`、`-1`、`999`、`10000` 全部由 `parse_calendar_year`（`filing_semantics.py:344`，bool/非 int/越界统一拒绝）映射为 `INVALID_FISCAL_YEAR`
2. **非法日期穿入 operation/observation/job/runner/converter**：不可能。`prepare_observed_upload`（`ingestion_runtime.py:3358-3359`）与 `start_upload`（`ingestion_runtime.py:4175`）均先 `_validate_runtime_upload_request` 后创建 observation/job；runner 由 `_ForbiddenUploadRunner`（调用即 AssertionError）证明不可达
3. **CLI/tool adapter 篡改 raw input**：未篡改。CLI 直接传 `args.filing_date` / `args.report_date`（`fins.py:694-695`），argparse 无 `type`/strip（`arg_parsing.py:1108-1109`），`""`、`" "`、`" 2024-02-29 "` 原样进入 admission 并以 typed usage error 拒绝——CLI 测试的空串/纯空白/首尾空白 case 是对“未 strip 未折叠”的真反例（若被 strip，`" "` 会折为 `None` 并穿透 delete 请求到 state read，测试会失败）。tool 侧 `_optional_raw_nullable_text`（`upload_tools.py:337`）missing/null→`None`、string 原样、非 string 抛 `ValueError`，且仅 filing 分支两个日期字段使用
4. **非 string 日期（int/bool）**：tool 边界 `_optional_raw_nullable_text` 拒绝（`upload_tools.py:357-358`）；即使绕过 adapter 直接构造 `FinsUploadFilingRequest(filing_date=0)`（类型契约外），`parse_iso_calendar_date` 首行 `isinstance(value, str)` 拒绝（`filing_semantics.py:382-383`），不存在崩溃或穿透
5. **delete action 绕过 year/date admission**：不绕过。静态校验在 action 分支之前执行（`ingestion_runtime.py:893-912` 先于 914 的 delete 特判），delete 请求同样必须满足 year 与提供日期的合法性，与 plan invariant 一致；三个测试矩阵全部用 delete 形态锁定这一点
6. **date/year 语义重复**：upload 链路上无重复。全仓 grep 证明 `parse_calendar_year` / `parse_iso_calendar_date` 生产消费者只有 `ingestion_runtime.py`（`download_contract.py` 是 S3 planned 范围）；`ingestion_runtime.py` 中唯一 `fromisoformat`（`6937`）是 job cancellation 时间戳解析，与 filing 日期无关；`build_sec_filing_ids`/`build_cn_filing_ids` 只格式化已校验 year，不再做合法性判定。旧码 `FILING_DATE_TOO_LONG` / `REPORT_DATE_TOO_LONG` 与旧文案“必须是非负整数”全仓（dayu/、tests/、docs/、README.md）零残留
7. **usage mapping closed**：`test_fins_upload_usage_failure_mapping_is_closed_bounded_and_path_free` 断言 `{code.value for code in FinsUploadUsageCode} == expected_codes`（精确 24 码集合）且每个 code 都能经 `fins_upload_usage_failure` 构造 1..240 字符、无路径泄漏的 message（缺映射会 KeyError）；三个新 code 额外断言不含 `--`。生产侧 `_USAGE_MESSAGES`（`ingestion_runtime.py:755-780`）与 enum 一一对应
8. **material 分支回归**：未回归。`_upload_request_from_arguments` material 分支仍用 `_optional_nullable_text`（`upload_tools.py:329-330`，strip 语义未动）；CLI `upload_material` 仍用 `_optional_stripped_text`（`fins.py:734-735`）；`upload_filings_from` 仍用 `_optional_stripped_text`（`fins.py:351-352`）；tool 测试用 `filing_date=" 2024-02-29 "` 的 material request 断言 strip 后为 `"2024-02-29"`，锁定既有 contract。共享 helper `_optional_nullable_text`（`_ingestion_tool_helpers.py:138`）未被修改
9. **schema 自足**：fiscal_year 描述含“filing 必填、1000..9999、material 可选”；两个日期字段描述含实际存在日期、无自动去空白、空串/纯空白/首尾空白非法，且都限定“上传 filing 时”，未扩大 material contract；arguments shape 与 `required` 元组未变。`test_upload_tool_calendar_year_schema_and_usage_messages_are_business_neutral` 精确断言三段文案与三个 usage message
10. **测试真反例 vs 假证明**：负向矩阵全部是真实失败输入（bool/边界年、空串/空白/首尾空白/非补零/非闰日/月 13/月 00/April 31/错误分隔符）且断言精确 typed message + 零副作用计数器；delegation guard（`test_filing_calendar_year_static_admission_accepts_boundaries_and_delegates`）的 record wrapper 调用真实 parser 并断言调用次数（`year_calls == [fiscal_year]*4`、`date_calls == ["2024-02-29"]*8`），证明委托而非碰巧一致，未用 fake 返回值制造假证明；合法 `2024-02-29` 与 `1000`/`9999` 产生 deterministic identity 且 `first.request is request` 锁定 validated request 与原请求同源（严格日期文本即 canonical，无第二份派生值，符合 plan §15）
11. **类型/docstring/分层**：pyright 0 errors；所有新增函数有中文 Args/Returns/Raises docstring；改动只发生在 fins domain/runtime/tool 与 CLI 层，无 `dayu.runtime`/Host/Engine 承载业务语义、无反向 import、无 `hasattr/getattr`、无兼容 shim、无魔法数字（`_USAGE_MESSAGES` 是唯一 message 真源，CLI 与 tool 均消费同一 `FinsUploadUsageError`/`FinsUploadUsageFailure`，不存在 channel-specific 重算）
12. **`_optional_raw_nullable_text` 英文消息**（`"filing_date must be a string or null"`）经 `ToolFailedOutcome.message` 投影给 LLM：与 `_ingestion_tool_helpers.py` 全部 adapter 边界错误（`must be an integer`、`must be a non-empty string or null` 等）同一既有约定，且它属于 tool argument 边界的 JSON 类型 admission，不是 year/date domain 语义；plan §8 要求的“domain ValueError 不暴露 raw 文本”已满足（domain 错误全部映射 typed usage code）。判定为一致，不构成 finding
13. **`upload_filings_from` 执行期行为变化**：batch 生成入口的 strip 未改，但生成脚本调用 direct `upload_filing`，非 canonical 日期（如 `2024-2-9`）会从“生成成功、执行成功”变为“生成成功、执行时 usage exit 2”。该后果正是 plan 明示 deferred 的 `upload_filings_from metadata strictness parity` 项，implementation artifact 已如实记录 owner；不重复报 finding，记入 Residual Risk

## Open Questions

- 无。阻碍 confident judgment 的问题为零；唯一 finding 的边界（file probe 顺序无安全后果）已有直接证据支撑。

## Residual Risk

- `UF-PF04` 真实 CLI evidence：未执行（按用户要求），owner=`UF-PF04` later work unit；本审查只能核验“无产出证据”，不能正向证明未执行。
- `upload_filings_from` metadata strip parity：S2 使该 deferred 项的执行期后果提前可见（batch 生成静默 strip、direct 执行严格拒绝的中间态），owner=`upload_filings_from metadata strictness parity`，建议在 S3 后尽快排期。
- tool 完整文件唯一 baseline failure `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`：本 slice 前后失败集合精确相等，owner=`UF-FIX01 follow-up`。
- S3 尚未实现：download 尚未消费 shared owner，`dayu/fins/README.md` 与根 `README.md` 的稳定 contract 更新尚未落地（S2 用户明确不写 README，属计划内）。
- F1 的优先级锁定缺口：见 finding，建议在 S2 fix 或 S3 中补齐两例优先级测试。

## Review 依据文件索引

- 生产：`dayu/fins/domain/filing_semantics.py`（S1 owner，344-422）、`dayu/fins/ingestion_runtime.py`（648-780、855-1013、3339-3375、4148-4236）、`dayu/fins/service_runtime.py`（61-94、200-265）、`dayu/fins/tools/upload_tools.py`（全文）、`dayu/fins/tools/_ingestion_tool_helpers.py`（111-260）、`dayu/cli/commands/fins.py`（303-500、560-740、1297-1310）、`dayu/cli/arg_parsing.py`（1105-1109）、`dayu/fins/upload_batch.py`（532-605）
- 测试：`tests/fins/test_fins_ingestion_runtime.py`（1133-1190、1302-1350、1489-1650、8814-8964）、`tests/fins/test_fins_ingestion_tools.py`（753-789、1092-1286、1885-1940）、`tests/cli/test_fins_commands.py`（1159-1385）
