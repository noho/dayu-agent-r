# UF-FIX04 S3 download shared-owner consumer and docs implementation

## Gate record

- Gate: `implementation`
- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Slice: `S3-download-shared-owner-and-closeout`
- Baseline commit: `67c34c0f44bf72ddeea9f1e732808f06245d8044`
- Branch: `codex/upload-filing-oracle`
- Scope: download wrapper 消费 S1 accepted calendar/year owner，锁定 wrapper-owned shape、trim、inclusive expansion 与 ordering，并更新当前稳定用户/开发者 contract。
- Completion status: `implementation complete; review pending`
- Current gate / next entry point: `dual S3 deepreview`
- Artifact path: `docs/reviews/wu-upload-filing-calendar-year-validation-s3-implementation-codex.md`

## First-principles judgment and semantic ownership

- 动机成立且严重性准确。baseline 的 `dayu/fins/download_contract.py::_parse_date_bound` 仍直接用 `datetime.date` / `calendar.monthrange` 同时承担 wrapper shape 与共同 calendar/year validity；`_parse_optional_iso_date` 也独立用 `date.fromisoformat` 校验 full-date。S1 accepted owner 已存在，因此剩余缺口是真实的 consumer ownership drift，不是仅凭测试或错误文案推断。
- calendar year `1000..9999` 与 canonical Gregorian full-date `0001..9999` 的唯一 owner 是 `dayu.fins.domain.filing_semantics`。download wrapper 仍唯一拥有 raw text trim、`YYYY` / `YYYY-M[M]` / `YYYY-M[M]-D[D]` shape、月日补零、partial inclusive expansion 与 download-specific usage projection；`FinsDownloadDateRange` 仍唯一拥有 start/end ordering。
- year-month 的 month validity 与真实月末属于 partial expansion 输入及派生语义，继续由 wrapper 通过 `calendar.monthrange` 处理；没有把 partial parser、range type 或 download error 投影迁入 domain。
- 实现只替换共同 validity 调用，没有新增 service/class/protocol、fallback、兼容分支、重复 calendar rule 或下游重算，属于 accepted owner boundary 的最小接线。

## Changed files

1. `dayu/fins/download_contract.py`
   - year-only 和 year-month 把四位整数年份委托 `parse_calendar_year`，因此 partial year 只接受 `1000..9999`。
   - full-date 保留一至两位 month/day shape，先格式化为补零的 canonical 文本，再只调用 `parse_iso_calendar_date`；没有调用 fiscal/partial year owner，因此实际 Gregorian `0001..9999` 保持合法。
   - `_parse_optional_iso_date` 保留 public text validation 与 public `ValueError` wrapper，calendar/strict ISO validity 改为委托 `parse_iso_calendar_date`。
   - `raw_value.strip()`、长度/shape 分类、partial inclusive expansion、download usage error 分类与 `FinsDownloadDateRange` ordering 均保持原 owner。
2. `tests/cli/test_fins_commands.py`
   - 增加真实 shared owner delegation spy，调用真实 parser而非 fake 返回值，分别证明 partial year 走 year owner、full-date 不走 year owner且在补零后走 full-date owner。
   - 增加 `_parse_optional_iso_date` 的 public DTO delegation guard。
   - 覆盖 partial `1000/9999`、`0999/0000` reject，full-date `0001/0999` accept、`0000` reject，闰年二月、非闰日、非法月日、外围空白、非补零 canonicalization、inclusive expansion 与 ordering。
   - 没有复制闰年、月末或年份范围算法；expected values 只断言 public contract结果。
3. `README.md`
   - 在最终用户 download 段说明 partial year 与 full-date 的不同年份域、一至两位月日、外围空白、真实公历校验、inclusive expansion 与 canonical 输出。
   - 把 strict raw admission 精确限定为直接 `upload_filing` 与 `start_fins_upload` filing 分支，并明确不覆盖 `upload_filings_from` 扫描/脚本生成元数据处理。
4. `dayu/fins/README.md`
   - 更新 `filing_semantics` 稳定 owner contract，区分 `1000..9999` fiscal/partial year 与 `0001..9999` canonical full-date。
   - 记录 download wrapper 与 domain owner 的职责分界，以及直接 upload filing/tool strict admission 边界；不写 work unit、测试流水账或未来能力。
5. 本 implementation artifact。

未修改任何其它 production/docs/tests 文件；未修改 frozen oracle/scenario/evidence，未执行 `UF-PF04`，未处理其它 finding，未 stage、未 commit。

## Control-side coverage-set correction

accepted plan 把 `download_contract.py >=80%` 错误绑定为 `tests/cli/test_fins_commands.py` 单文件集合。直接证据如下：

1. 只运行 CLI 全文件时，calendar/year 测试与全部既有 CLI tests 均通过，但 `download_contract.py` statement coverage 只有 `63%`；missing lines 主要属于 result summary、provider error、public projection 等非 UF-FIX04 contract。
2. 初次观察到该数字后，implementation 曾在 allowed CLI test file 中加入两个 result/provider tests 以尝试满足门槛。控制侧裁决指出该路径会把错误 coverage 假设转化为 goal drift；裁决成立。
3. 已完整撤销 `test_download_result_contract_derives_counts_terminal_and_public_summary`、`test_download_provider_errors_preserve_closed_safe_contract` 及其专用 imports；任何被中断的 coverage 运行均未计入完成证据。
4. 不修改已有 consumer tests，改用当前仓库真实可达集合：
   - `tests/cli/test_fins_commands.py`
   - `tests/fins/test_fins_ingestion_runtime.py`
   - `tests/service/test_fins_direct.py`
   - `tests/service/test_fins_wait_adapter.py`
   - `tests/cli/test_output.py`
5. 该集合覆盖 request、runtime、Service direct/wait 与 CLI public projection 的现有真实 consumers，实测 `download_contract.py` 为 `88%`。因此 coverage 门槛成立，plan 的 CLI-only集合估计已由控制侧直接证据修正；没有用非 calendar/year 新测试凑 coverage，也没有修改上述现有 test files。

## Validation

所有 Python 命令均在仓库根目录执行并先激活 `.venv`；未运行 `UF-PF04`。

1. S3 calendar/year focused tests
   - Command: `pytest tests/cli/test_fins_commands.py -q -k 'download_date_bounds_preserve_shape_canonicalization_and_inclusive_expansion or download_partial_year_rejects_values_outside_shared_year_domain or download_full_date_rejects_nonexistent_calendar_dates or download_date_bound_delegates_shared_year_and_full_date_owners or download_public_iso_dates_delegate_shared_full_date_owner or download_date_range_ordering_remains_owned_by_range_contract'`
   - Result: exit `0`; `15 passed`, `109 deselected`, `3 warnings`。
2. CLI full file
   - Command: `pytest tests/cli/test_fins_commands.py -q`
   - Result: exit `0`; `124 passed`, `3 warnings`。
   - CLI-only coverage rerun: `coverage run -m pytest tests/cli/test_fins_commands.py -q`，exit `0`; `124 passed`, `3 warnings`。
   - Command: `coverage report --include='dayu/cli/commands/fins.py' --show-missing --fail-under=80`
   - Result: exit `0`; `469` statements、`68` missed、**`86%`**。
3. Download contract real reachable coverage set
   - Command: `coverage run -m pytest tests/cli/test_fins_commands.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/service/test_fins_wait_adapter.py tests/cli/test_output.py -q`
   - Result: exit `0`; `458 passed`, `3 warnings`。
   - Command: `coverage report --include='dayu/fins/download_contract.py' --show-missing --fail-under=80`
   - Result: exit `0`; `330` statements、`38` missed、**`88%`**。
4. Full pyright
   - Command: `python -m pyright dayu/ tests/ utils/`
   - Result: exit `0`; 无输出，即全量 `0 errors`。
5. Diff/scope/frozen integrity
   - `git diff --check`: artifact 写入前后均 exit `0`、无输出。
   - `git diff --no-index --check /dev/null docs/reviews/wu-upload-filing-calendar-year-validation-s3-implementation-codex.md`: 无 whitespace-error 输出；exit `1` 只表示新 artifact 相对 `/dev/null` 存在内容差异。
   - `git diff --name-only 67c34c0f --`: artifact 写入前精确为四个 allowed tracked files。
   - `git diff --cached --name-status`: 无输出；没有 staged changes。
   - `git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json`: 无输出；冻结 registry 未改。

三条 pytest warning 均来自 `.venv` 中 `edgar` deprecated imports，与本 slice 改动无关。

## Docs decision

- 根 `README.md`: 更新。download日期输入与直接 upload filing/tool strict admission 是当前最终用户可见 contract；文字不暴露内部模块或治理过程，并明确不承诺 `upload_filings_from` metadata parity。
- `dayu/fins/README.md`: 更新。domain owner、download wrapper ownership 与 direct filing admission 是 `dayu.fins` 当前稳定开发者边界。
- `tests/README.md`: 不更新。只在既有 CLI/Fins contract测试层增加 calendar/year cases，没有新增测试层级、运行方式或维护规则；控制侧采用的 coverage 集合也是现有测试文件组合，不改变手册命令 contract。
- `dayu/README.md`: 不更新。`UI -> Service -> Host -> Engine`、Fins package位置、跨包装配和依赖方向均未改变；本次只在 Fins 内完成 domain owner consumer 接线。
- Host/Engine/Config README: 未触发，对应生产目录和稳定边界均未修改。

## Findings and residual risks

- Implementation self-check findings: 无 blocking finding；正式 finding 状态由下一 gate 的 dual S3 deepreview 裁决。
- CLI-only coverage set 估计错误：`fixed in current slice`；由控制侧裁决撤销非目标 tests，并采用不修改现有 consumer files 的真实可达集合验证 `88%`。
- `UF-PF04` 真实 CLI evidence：`assigned to later work unit`，owner=`UF-PF04`；按用户明确要求未执行。
- 其它 upload findings：`assigned to later work unit`，owner=`UF-FIX01/02/03/05...`；本 slice 未处理。
- `upload_filings_from` raw metadata strictness parity：`assigned to later work unit`，owner=`upload_filings_from metadata strictness parity`；README 已限制 direct contract scope。
- tool 完整文件预存 failure：`assigned to later work unit`，owner=`UF-FIX01 follow-up`；S3 未修改 tool production/test文件，S2 accepted baseline证据保持有效。

没有 `unclassified residual risk`，没有 blocking open question。

## Completion and handoff

S3 download owner delegation、wrapper-owned行为回归、稳定 README contract、CLI full tests、真实可达 download coverage、CLI coverage、全量 pyright与 scope integrity均达到控制侧修正后的 completion signal。本 artifact 只声明 implementation complete，不声明 S3 accepted，不执行 code review，不创建 checkpoint commit。

Next entry point: `dual S3 deepreview`。
