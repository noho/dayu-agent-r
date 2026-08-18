# UF-FIX04 S2 review fix

## Gate record

- Work unit: `UF-FIX04 shared-calendar-year-validation`
- Slice: `S2-upload-strict-static-admission`
- Branch: `codex/upload-filing-oracle`
- Base: `e5d4394ab29ce5d8ec7db0f3aa6bb3c262696c12`
- Input decision: `docs/reviews/wu-upload-filing-calendar-year-validation-s2-review-controller-adjudication.md`
- Accepted finding: AgentDS F1，date admission 先于 file existence probe 的顺序缺少 contract guard
- Completion status: `accepted F1 fixed; dual S2 re-review pending`
- Next entry point: `dual S2 re-review by AgentMiMo and AgentDS`

## First-principles judgment and owner boundary

F1 动机成立，严重度为低且评估准确。生产实现已经按 accepted plan 在 period 后、file existence probes 前调用 shared calendar-date owner；缺口不是运行时行为错误，而是 admission owner boundary 的测试未构造“非法日期与缺失文件同时存在”的可判别反例。若未来错误调整校验顺序，原有日期负向矩阵仍可能通过。

因此修复只落在既有 `test_validate_fins_upload_filing_request_preserves_validation_priority` contract test，不修改生产 validator、CLI/tool adapter、其它测试或冻结 evidence。测试使用 `tmp_path` 生成并确认不存在的文件路径，避免依赖仓库当前目录状态。

## Changes

仅修改 `tests/fins/test_fins_ingestion_runtime.py`：

1. 添加 `filing_date="2024-13-01"` 对称 case，同时提供合法 `fiscal_year=2024`、合法 `fiscal_period="FY"` 与缺失文件，断言 `INVALID_FILING_DATE`。
2. 添加 `report_date="2024-13-01"` 对称 case，其余前提相同，断言 `INVALID_REPORT_DATE`。
3. 更新测试 docstring，将既有优先级 contract 明确为 `ticker→year→period→dates→files`。

另新增本 review-fix artifact。未修改任何生产代码、其它测试、README、oracle/scenario/evidence；未 stage、未 commit。

## Finding closure

AgentDS F1 已关闭。新增两例都让日期错误与 `FILE_NOT_FOUND` 形成直接竞争：文件路径确定不存在，但 validator 分别返回 `INVALID_FILING_DATE` 与 `INVALID_REPORT_DATE`。因此 contract 现在能检测日期校验被误移到文件存在性探测之后的回归，并对两个日期字段保持对称。

## Validation

所有命令均在仓库根目录执行并先激活 `.venv`。未运行 `UF-PF04`。

1. 新增优先级测试
   - Command: `pytest tests/fins/test_fins_ingestion_runtime.py::test_validate_fins_upload_filing_request_preserves_validation_priority -q`
   - Result: exit `0`; `8 passed`, `3 warnings`。
2. S2 focused nodes
   - Command: accepted plan §12 的 6 个 focused nodes。
   - Result: exit `0`; `89 passed`, `3 warnings`。
3. Runtime 完整文件
   - Command: `pytest tests/fins/test_fins_ingestion_runtime.py -q`
   - Result: exit `0`; `258 passed`, `3 warnings`。
4. 定向 pyright
   - Command: `python -m pyright dayu/fins/ingestion_runtime.py dayu/cli/commands/fins.py dayu/fins/tools/upload_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/cli/test_fins_commands.py`
   - Result: exit `0`; `0 errors, 0 warnings, 0 informations`。
5. Diff integrity and scope
   - `git diff --check`: exit `0`，无输出。
   - `git diff --cached --name-status`: exit `0`，无输出；没有 staged changes。
   - 相对 base 的 tracked scope 仍精确为原 S2 六文件：三个生产文件与 runtime/CLI/tool 三个测试文件。本 fix 前后对比只为 `tests/fins/test_fins_ingestion_runtime.py` 增加 F1 guard，并新增本 artifact；既有 implementation、两路 deepreview 与 controller adjudication artifacts 保持 untracked。
   - `git status --short -- docs/cli_ci_oracles.json docs/cli_ci_scenarios.json`: exit `0`，无输出；冻结 oracle/scenario/evidence 未改。

三条 pytest warning 均来自 `.venv` 中 `edgar` deprecated imports，不是本次修复产生的失败。

## Docs and residual risk

- `tests/README.md` 只记录测试分层、运行方式与维护约定；本次没有新增测试层级或改变运行方式，且用户明确禁止 README 修改，因此不更新。
- S2 既有唯一 tool baseline failure、S3 download consumer、`upload_filings_from` metadata strictness parity 与 `UF-PF04` 仍由原 owner/work unit 负责；本 fix 没有扩大或重新裁决这些 residual risks。
- 本 artifact 只声明 accepted F1 修复完成，不声明 S2 accepted，不进入 S3。

## Handoff

停在 `dual S2 re-review` 入口，等待 AgentMiMo 与 AgentDS 独立复审。
