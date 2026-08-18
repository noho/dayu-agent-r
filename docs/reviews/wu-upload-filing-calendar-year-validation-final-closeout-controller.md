# UF-FIX04 Gateflow final closeout

## Gate record

- Work unit：`UF-FIX04 shared-calendar-year-validation`
- Branch：`codex/upload-filing-oracle`
- Decision：`Final closeout Pass`
- PR / push：按用户要求均不执行

## Outcome

本 work unit 已完成唯一 calendar/year 语义 owner、upload_filing 前置静态准入、download 共享 owner 委托、测试与必要文档更新。实现保持 download wrapper 对 year、year-month、full-date shape 及 inclusive start/end 展开的所有权，没有把部分日期语义泄漏给 upload_filing。

## Accepted commits

- `f609a4d8`：accepted plan
- `e5d4394a`：S1 shared calendar/year owner
- `67c34c0f`：S2 upload_filing strict static admission
- `0dfc9f34`：S3 download shared-owner delegation and closeout
- `39ccf73f`：accepted aggregate deepreview

## Contract achieved

1. `dayu.fins.domain.filing_semantics` 是完整公历日期与四位年份合法性的唯一 owner。
2. 日期只接受 ASCII `YYYY-MM-DD` 且必须是实际存在的 Gregorian date，闰年由标准库日期构造校验。
3. fiscal year 只接受非 bool 的整数 `1000..9999`。
4. upload_filing 在 operation、converter、state/storage probe 与 durable mutation 前完成静态准入，并以 typed usage error 失败。
5. download 的完整日期和年份合法性委托 shared owner；download wrapper 继续独占 partial shape 与 inclusive bound 展开。
6. CLI/tool adapter 只保留原始输入传递与错误投影，没有新增 fallback、loose parsing 或重复 domain validation。
7. 非法年份不能进入 source meta、manifest 或其它 durable state；历史 durable invalid year 读取路径 fail closed。

## Final verification

控制侧在 accepted deepreview 提交后重新执行：

- `pytest tests/fins/test_fiscal_normalization_contracts.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q`：`98 passed`
- `pytest tests/fins/test_fins_ingestion_runtime.py -q`：`258 passed`
- `pytest tests/cli/test_fins_commands.py -q`：`124 passed`
- `pytest tests/fins/test_fins_ingestion_tools.py -q`：`82 passed, 1 failed`；唯一失败为冻结范围外既有 UF-FIX01 case `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect`
- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`
- `git diff --check`：通过

aggregate 双路 reviewer 独立复现的 coverage gate：

- `filing_semantics.py`：`87%`
- `ingestion_runtime.py`：`91%`
- `download_contract.py`：`88%`
- `dayu/cli/commands/fins.py`：`86%`
- `upload_tools.py`：`91%`

## README and frozen-scope check

- 已按职责更新根 `README.md` 与 `dayu/fins/README.md`。
- `tests/README.md` 与 `dayu/README.md` 不需更新：没有新增测试层级/运行协议，也没有改变分层或装配关系。
- 未刷新 `docs/cli_ci_oracles.json` 或 `docs/cli_ci_scenarios.json`，未修改既有冻结 evidence。
- 未执行 `UF-PF04` 真实 CLI evidence。
- 未处理其它 `upload_filing` finding。

## Review result

- Plan：AgentMiMo / AgentDS 双路 review、fix、re-review 后 Pass。
- S1 / S2 / S3：逐 slice 实现、双路 review、fix、re-review 后 accepted。
- Aggregate：AgentMiMo Pass；AgentDS 提出两个 low finding。控制侧接受并由 AgentCodex 修正测试 contract，双路 aggregate re-review 一致 Pass。

## Residual risk / explicitly deferred

- tool 完整文件的 UF-FIX01 预存失败仍存在；与 calendar/year owner 无关，按本 work unit scope 不修复。
- `upload_filings_from` metadata strictness parity 是独立后续项，不在本 work unit 内扩展。
- download partial-shape regex 的 Unicode digit 宽松是 baseline 行为；本任务只共享完整 date/year 合法性，不改变该 wrapper shape 接受集。
- `_parse_date_bound` 的 empty/too-long pre-existing missed lines 不影响本次 contract 与 `>=80%` coverage gate。
- UF-PF04 真实 CLI evidence 未运行，因此不对该证据作完成声明。

## Final decision

代码、测试、必要文档与 Gateflow artifacts 均已完成，双路审查无 remaining finding，类型检查与受影响测试满足 gate。允许在当前分支提交本 closeout artifact 后结束 work unit。
