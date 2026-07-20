# WU-SEMANTIC-OWNERSHIP-01 / AR-F07 WIN4-S1 implementation

## Gate identity

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01`。
- Continuation：`AR-F07` 第四轮真实 Windows evidence remediation；本次是同一 umbrella 内的
  `WIN4-S1`，不是新 WU。
- Accepted plan commit：`15979f5d32738148bf53daf9defe2dca59b8360c`。
- Accepted plan：`docs/host/wu-semantic-ownership-01-ar-f07-win4-remediation-plan.md`。
- 当前 gate：WIN4-S1 implementation；未进入 code review、accepted slice commit 或真实 Windows closure。
- Completion status：`IMPLEMENTED_AND_LOCALLY_VALIDATED / REAL_WINDOWS_PENDING /
  STOPPED_AT_USER_AUTHORIZED_IMPLEMENTATION_BOUNDARY`。

## First-principles and owner judgment

修改动机成立。直接代码与既有真实 evidence 同源证明：fresh storage 的 `create/update` 请求若没有
`company_name`，唯一业务 owner
`dayu/fins/pipelines/upload_company_meta.py::upsert_company_meta_for_upload()` 必须 fail closed；当前
Windows real-smoke generation argv 没有提供该字段，而既有 POSIX real workflow 明确提供
`Apple Inc.`。因此本次失败是 Windows real-smoke 构造了无效请求，不是 Windows newline、Docling、storage
publication 或 production renderer 缺陷。

本 slice 的正确 owner 是
`tests/cli/test_upload_filings_from_command.py::test_windows_generated_script_runs_real_cli_into_temp_storage`：
它负责向 public CLI 提交合法 real-smoke 输入并在执行前验证生成的业务 argv。Fins 仍拥有字段必填规则，CLI
renderer 仍只机械投影 typed batch plan。本实现没有在 production、adapter、结果投影或 fixture 增加默认公司名、
ticker 推导、FMP/network infer、preseeded meta、message parsing、fallback 或兼容分支，因此不是 test fallback。

## Changed paths and exact implementation

### `tests/cli/test_upload_filings_from_command.py`

- Windows real-smoke generation argv 显式增加 `--company-name`、`Apple Inc.`。
- 在真实 `cmd.exe /d /c` 执行前读取生成脚本的 strict UTF-8 bytes，并按 CRLF physical line fail closed：
  精确验证并排除固定 Windows batch header，单独排除唯一 `REM Regenerate:` 行，只允许一条业务命令及固定
  error/exit control lines。
- 业务命令不使用 POSIX parser。test-local oracle 按 renderer 的 batch percent/caret 和 Windows CRT
  backslash/quote 语义逐 token 恢复 fixed argv，要求唯一命令 token 精确为 `upload_filing`，要求
  `--company-name` token 恰好一次且下一 token 精确为 `Apple Inc.`。
- 增加平台无关 owner test：验证合法命令通过；regeneration comment 含 company name 但业务命令缺失、零条
  `upload_filing` 业务命令、多条业务命令及重复 `--company-name` token 全部 fail closed。它不依赖 real
  Windows skip。
- Windows 成功 oracle artifact 从同一逐 token 断言结果写入
  `company_name_supplied=true`；没有从 execution result、stdout、storage result 或 whole-file substring 反推。
- 保留 fresh storage、真实 `cmd.exe /d /c`、execution exit 0、`Fins result` terminal success 与
  portfolio source artifact count。

### 本 artifact

- `docs/reviews/wu-semantic-ownership-01-ar-f07-win4-s1-implementation-codex.md`：记录 implementation、验证、
  docs decision 与 residual risk；不拥有 control transition。

## Validation

所有 Python 命令均先执行 `source .venv/bin/activate`。

### Focused and broader tests

- Target file：`pytest tests/cli/test_upload_filings_from_command.py -q`：
  `20 passed, 2 skipped, 3 warnings`。
- Focused owner set：计划 §6.1 的五个文件：`182 passed, 7 skipped, 3 warnings`。
- Required owner nodes：stale company-meta fail-closed + POSIX real CLI storage：
  `2 passed, 3 warnings`。
- Broader CLI：`pytest tests/cli -q`：`520 passed, 7 skipped, 3 warnings`。
- Broader Fins：计划 §6.2 的两个文件：`95 passed, 3 warnings`。
- 三条 warning 都来自已安装 `edgar` 包的既有 deprecation warning，不来自本 slice。
- 本机不是 Windows；target file 中两个 real `cmd.exe` nodes 按既有条件 skip。新增 oracle 正/负测试实际通过，
  但 local skip 不能替代真实 R11/R12 closure。

### Type and lint

- `python -m pyright tests/cli/test_upload_filings_from_command.py`：`0 errors, 0 warnings, 0 informations`。
- `python -m ruff check tests/cli/test_upload_filings_from_command.py`：`All checks passed`。
- Ruff version：`0.15.11`。
- Entry/final full Ruff exact baseline comparison：按
  `(filename, row, column, code, message, fix-applicability)` 排序归一化；入口与最终均为
  `142` 条既有诊断，tuple SHA-256 均为
  `bcb9e45754ecb183a69859480a286c2c5e3504fb10b1db3958bf44a9deaa2be3`；新增或扩散为零。

### Diff, allowlist and integrity

- `git diff --check`：PASS。
- `git diff --cached --name-only`：零输出，staged tree empty。
- S1 test diff stat：`1 file changed, 174 insertions(+), 1 deletion(-)`。
- S1 test diff SHA-256（`git diff --binary -- tests/cli/test_upload_filings_from_command.py`）：
  `9c16a8c737eac8f0bdc816dd8e400a4987957fcbc03b1d70bcf661e0a00712e6`。
- 未修改 production、workflow、根 README、`dayu/README.md` 或 `tests/README.md`；后者按 accepted plan 只属于
  WIN4-S3。
- Controller 既有未提交 `docs/host/issues-implementation-control.md` 状态保持在 implementation ownership 外；
  其 working-file SHA-256 为
  `bd96ab5f2ba611297536554f7d1a08d20c8324c0f72badb31917a1f91d81a434`，其 unstaged diff SHA-256 为
  `02d843ec711cb08368a03ffac12f35b31e3618672f173e5c2b623f2177fda344`。

### Source and security scans

- S1 added-lines scan对 `.count(`、`shlex` 与 execution-result/company-name 反推模式：零输出。
- production/workflow/README diff scan：零输出。
- Deferred-term scan（Issue 142/151/175/177/178、`web_tools_storage_states`）：零输出。
- `shell=True` / `errors=replace` scan：零输出。
- accepted plan 的 aggregate scan 在当前 S1 tree 仍显示一个既有
  `dayu/cli/init_environment.py:419 capture_output=True`；与 accepted plan commit 的结果逐行相同，owner/destination
  是后续已批准 WIN4-S2，本 slice 按 allowlist 不得修改。
- aggregate native-tool scan仍显示 `tests/cli/test_init_smoke.py` 中七处既有 `reg.exe` 说明/调用；与 accepted
  plan commit 的结果逐行相同，owner/destination 是后续已批准 WIN4-S3，本 slice 没有新增或改写。
- 未读取 GitHub Secrets 或 configured production values；未产生或记录 raw source、registry value、sentinel、
  API key、FMP key 或环境 snapshot。

## README and design decision

- 不更新 README。WIN4-S1 只修正 test input/oracle，不改变 Fins production contract、CLI grammar、最终用户工作流、
  分层或稳定设计。
- `tests/README.md` 的真实 Windows evidence 说明按 accepted plan 明确归 WIN4-S3；用户也禁止本 slice 修改它。

## Residual risks and uncovered areas

- 真实 Windows R11 与 R12 embedded-R11 尚未运行；状态是
  `REAL_WINDOWS_PENDING`，不能据本机 skip 宣称 WIN4-F01 或 AR-F07 closure。Owner/destination：所有批准 slices
  accepted 后由 Controller 按 plan §8/§9.3 dispatch 并验证 same-run evidence。
- aggregate scan中的既有 `capture_output=True` 由已批准 WIN4-S2 负责；既有 `reg.exe` scan结果由已批准
  WIN4-S3 负责。二者均未被本 slice 新增或扩散。
- WIN4-S2/WIN4-S3、其 code review、accepted commit、aggregate deepreview 与真实 Windows closure 均未进入。
- 无未分类 residual risk。

## Stop boundary

本轮严格停止在用户授权的 WIN4-S1 implementation gate：未 stage、commit、push、dispatch workflow、创建或修改
PR，也未修改 Controller control doc；下一入口由 Controller 决定，不由本 artifact 推进。
