# UF-FIX04 聚合 re-review（AgentDS）

- 审查类型：current changes（UF-FIX04 聚合双路 re-review 之一，AgentDS 路；对 accepted F1/F2 修复的复核）
- 审查时间：2026-08-14T16:32:41+0800
- Work unit：`UF-FIX04 shared-calendar-year-validation`
- Branch：`codex/upload-filing-oracle`
- Reviewed HEAD：`0dfc9f341ad105a8df6dbba823be365dd7cb23da`（S3 accepted 提交，即修复 diff 的基线）
- 审查输入：本路 aggregate deepreview（F1/F2）、controller adjudication、AgentCodex aggregate review fix artifact、工作树相对 HEAD 的完整 diff
- 排除范围：AgentMiMo 的 `wu-upload-filing-calendar-year-validation-aggregate-rereview-mimo.md`（保持双路独立性，未读取）；冻结 oracle/evidence JSON（未改动，见 scope 核对）
- 审查动作：只读。未修改生产代码或测试，未 stage、未 commit；仅新增本 artifact。

## 结论

**Pass。** 两项 accepted finding 的修复均正确落地、裁决对 F1 输入类的事实区分准确、scope 与验证声明全部独立复现。无 remaining findings，无新增 findings。

- 裁决对 `2024-2-9`（baseline 本来就拒绝，message 未漂移）与 `20240229`/week-date（baseline 走 canonical 分支，wording 真实变化）的区分，经 baseline 代码逐行核对与 Python 3.11.15 实测双重确认，**裁决事实准确**；本路原 F1 中"`2024-2-9` 可被 3.11 fromisoformat 解析"的示例表述不准确，已被裁决纠正，但原 finding 核心（basic/week-date 类 wording 被静默统一、plan §6 承诺未被 artifact 显式记录）成立，修复覆盖了正确的漂移类别。
- F1 修复测试对 `20240229` 锁定 exact message `start_date must be an ISO date`——该输入在 baseline 会抛另一条 message，因此该断言构成对"统一 message"的有效锁定；测试经真实 owner spy 委托、未复制生产校验逻辑。
- F2 修复测试不再锁定 4/8 次调用；两个不同合法日期 + 集合相等断言在数学上保证 fiscal year、filing date、report date 三者均至少委托 owner 一次、值原样、无额外值；identity/action/request 断言全部保留。
- scope：工作树相对 HEAD 的 diff 精确为 controller 允许的两个测试文件（+10/-3），生产代码、README、冻结 registry/evidence 零改动，无 staged changes。
- 验证：两个修改测试 3 passed、plan §12 六个 focused nodes 89 passed、runtime 完整文件 258 passed、CLI 完整文件 124 passed、pyright 0/0/0、`git diff --check` 干净，与 fix artifact 声明逐项一致。

## 验证复核（本机独立执行）

### F1 事实核对：裁决准确区分两类输入

| 输入 | baseline 行为（`f609a4d8:dayu/fins/download_contract.py` 原 `_parse_optional_iso_date`） | 当前行为（统一委托 `parse_iso_calendar_date`） | message 是否变化 |
| --- | --- | --- | --- |
| `2024-2-9` | `dt.date.fromisoformat` 抛 `ValueError`（3.11.15 实测）→ except 分支抛 `must be an ISO date` | strict owner 拒绝 → `_parse_optional_iso_date` except 分支抛 `must be an ISO date` | 否（无漂移） |
| `20240229`（basic format） | 3.11 `fromisoformat` 解析成功 → `parsed.isoformat() != value` → 抛 `must use canonical ISO format` | strict owner 拒绝 → 抛 `must be an ISO date` | 是（真实漂移类） |
| `2024-W08-4`（week-date） | 3.11 `fromisoformat` 解析成功 → canonical 分支 → `must use canonical ISO format` | strict owner 拒绝 → 抛 `must be an ISO date` | 是（同类，未单独加测试，controller 标记为可选） |

- 直接证据 1：baseline 代码（`git show f609a4d8:dayu/fins/download_contract.py` 839-856 行）存在 `fromisoformat` try/except（`must be an ISO date`）与 `parsed.isoformat() != value`（`must use canonical ISO format`）双分支。
- 直接证据 2：Python 3.11.15 实测——`date.fromisoformat('2024-2-9')` 抛 `ValueError`；`'20240229'` 与 `'2024-W08-4'` 均解析成功且 `isoformat()` 与原文不一致。
- 直接证据 3：当前代码 `dayu/fins/download_contract.py:858-861` 唯一 except 分支统一映射 `must be an ISO date`。
- 结论：controller adjudication 的区分（"`2024-2-9` 在 baseline 本来就拒绝并使用后一文案，不是实际漂移样例；真正发生 wording 变化的是 basic/week-date 类"）**完全准确**；本路原 F1 的示例选取有误，被裁决正确纠正。

### F1 修复核对：锁定统一 message 且未复制生产校验

- 新测试块位于 `tests/cli/test_fins_commands.py:1273-1281`：构造 `FinsDownloadEffectiveFilters(start_date="20240229", ...)`，断言 `str(basic_format_exc.value) == "start_date must be an ISO date"`（exact equality，非 regex match）。
- 锁定有效性：`20240229` 在 baseline 会得到另一条 message，因此若生产代码恢复双文案，本断言必失败——构成对统一 contract 的有效回归锁。
- 未复制生产校验：测试不重实现任何 regex / `fromisoformat` / 日期逻辑；测试文件内 spy（`tests/cli/test_fins_commands.py:1228-1248`）记录后调用**真实** `parse_iso_calendar_date`，生产校验仍由唯一 owner 执行。
- exact message 只能来自 `download_contract.py:861` 的映射分支（`_validate_public_text` 的报错文案均不匹配该字符串），无错误来源混淆。

### F2 修复核对：去除调用次数固化，委托 contract 仍完整成立

- 修改位于 `tests/fins/test_fins_ingestion_runtime.py:1754, 1770-1773`：`report_date` 改为与 `filing_date` 不同的 `"2024-03-01"`；删除 `year_calls == [fiscal_year] * 4` 与 `date_calls == ["2024-02-29"] * 8`。
- 新断言逐一证明原 owner contract 的全部要素：
  - `assert year_calls` + `set(year_calls) == {fiscal_year}`：fiscal year **至少委托一次**、全部委托值为当前 `fiscal_year`、**无额外值**。
  - `assert date_calls` + `set(date_calls) == {"2024-02-29", "2024-03-01"}`：两个值互不相同，集合相等 ⇒ 每个值至少出现一次 ⇒ filing date 与 report date **各自至少委托一次**，值原样未改写，**无其它值**。
  - 保留断言：`first.document_id == second.document_id`（确定性 identity）、`first.internal_document_id == second.internal_document_id`、`first.resolved_action == "delete"`（进入 state-aware path）、`first.request is request`。
- 无调用次数承诺：全仓 grep 确认 `year_calls == [fiscal_year, ...]` 与 `["2024-02-29"] * 8` 零残留。`tests/cli/test_fins_commands.py:1196-1207, 1259` 的 exact-list 断言为 S3 已审内容（单次公开入口 start/end 各一次的委托序列契约），锁的是"谁收到什么值"，不是内部重复结构，与本 F2 无关、不在本修复范围。
- spy（`tests/fins/test_fins_ingestion_runtime.py:1709-1747`）记录后调用真实 owner，非 fake 返回值。

### 复跑结果（对照 fix artifact §验证）

| 声明 | 命令 | 复核结果 | 一致 |
| --- | --- | --- | --- |
| 两个修改测试 | `pytest tests/cli/test_fins_commands.py::test_download_public_iso_dates_delegate_shared_full_date_owner tests/fins/test_fins_ingestion_runtime.py::test_filing_calendar_year_static_admission_accepts_boundaries_and_delegates -q` | `3 passed, 3 warnings`，exit 0（runtime 节点按 `fiscal_year=(1000, 9999)` 参数化，合计三例，与 artifact 声明一致） | ✅ |
| S2 focused 六节点（accepted plan §12 节点列表） | 六个 node 显式展开运行 | `89 passed, 3 warnings`，exit 0 | ✅ |
| runtime 完整文件 | `pytest tests/fins/test_fins_ingestion_runtime.py -q` | `258 passed, 3 warnings`，exit 0 | ✅ |
| CLI 完整文件 | `pytest tests/cli/test_fins_commands.py -q` | `124 passed, 3 warnings`，exit 0 | ✅ |
| 全量类型检查 | `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations`，exit 0 | ✅ |
| Diff integrity | `git diff --check` | 无输出，exit 0 | ✅ |

### Scope 核对

- `git diff 0dfc9f34` 精确为 `tests/cli/test_fins_commands.py`（+10）与 `tests/fins/test_fins_ingestion_runtime.py`（+8/-3），与 controller 允许的修复边界一致。
- 生产代码、README、`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json` 零改动；无 staged changes；未执行 `UF-PF04`（verified-by-absence，工作树无任何执行产出）。

## Findings

未发现实质性问题。

## Open Questions

- 无。

## Residual Risk

- 本路原 F1 示例（`2024-2-9`）不准确，已由裁决纠正并记录于本 artifact；原 S3 DS 审查中"wording 原样保留"表述不再被引用，治理上由聚合裁决 artifact supersede（历史 artifact 不回写，符合既有治理约定）。
- F1 测试只锁定 `start_date` 单字段 exact message；其余字段（`end_date` / `filing_date` / `report_date`）共用同一 `_parse_optional_iso_date` 单一映射分支，属同一 contract 模板，风险边际可忽略。
- 既有 residual 不变：`UF-FIX01 follow-up` tool 预存失败、`_parse_date_bound` pre-existing missed line、download shape Unicode digit 宽松、`upload_filings_from` metadata strictness parity、`UF-PF04` 真实 CLI evidence 未执行（用户 scope 排除）。
- AgentMiMo re-review artifact 未读取（双路独立性）；按 controller gate 约定，需 MiMo 亦 Pass 后方可 close。
