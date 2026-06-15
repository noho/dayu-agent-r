# WU-CLI-01 / CLI-01-S6 Implementation Report

## Gate

- 当前 gate：implementation。
- Slice：CLI-01-S6 upload_filings_from batch plan generation。
- 设计真源：`docs/host/design.md`、`docs/engine/design.md`。
- Accepted plan：`docs/host/wu-cli-01-cli-entrypoint-plan.md`。

## First-principles judgment

问题成立。`upload_filings_from` 是本地目录到上传脚本的计划生成能力，不应启动 Fins ingestion job，也不应创建 Host Run 或写 Host EventLog。原实现只保留 parser 并在执行期 fail fast，无法满足当前 CLI command surface。

实现路径选择：

- Fins 业务识别真源放在 `dayu.fins.upload_batch`，CLI 不承担 filing/material 识别。
- CLI 只把 argparse 结果转换为 `UploadBatchPlanRequest`，并把结构化 entries 渲染成 `dayu-cli upload_filing ...` / `dayu-cli upload_material ...`。
- 未修改 parser；当前 parser 已具备本 slice 要求的 `--from`、`--recursive`、`--action {create,update}`、`--material-forms`、`--output` 和 metadata flags。
- 未修改 `dayu/service/fins_direct.py`；Service import boundary 当前只允许少量 Fins runtime/ingestion boundary，直接在 Service 新增 `dayu.fins.upload_batch` import 会扩大边界，当前 slice 没有必要。

## Changed files

- `dayu/fins/upload_batch.py`
  - 新增 `UploadBatchPlanRequest`、`UploadBatchPlanEntry`、`UploadBatchPlanResult`。
  - 新增 `generate_upload_batch_plan(...)`，扫描本地源目录并生成结构化 upload entries。
  - 错误类型：`UploadBatchPlanUsageError`、`UploadBatchPlanEmptyError`。
- `dayu/cli/commands/fins.py`
  - 移除 `upload_filings_from` unsupported 分支。
  - 新增 batch plan 调用、stdout / `--output` 输出和 shell quoting formatter。
  - 保持 direct job 命令原有 start / wait / cancel 路径不变。
- `tests/fins/test_upload_batch.py`
  - 覆盖 recursive / non-recursive、filing/material 识别、空结果、source dir 不存在、import boundary。
- `tests/cli/test_upload_filings_from_command.py`
  - 覆盖 stdout、`--output`、quoting、错误码、SIGINT 130、不创建 Fins direct service、CLI import boundary。
- `dayu/fins/README.md`
  - 按 README 约束最小同步当前 `dayu.fins.upload_batch` capability。
- `tests/README.md`
  - 按 README 约束更新 CLI 测试分层说明。

## Boundary decisions

- Host / Engine：新增实现没有导入 Host / Engine，没有创建 Host Run，没有写 Host EventLog。
- Fins storage：新增 helper 只扫描调用方显式传入的本地源目录，不导入或读取 `dayu.fins.storage`。
- Service：本 slice 没有新增 Service helper，避免扩大 `dayu.service` 对 Fins 的 allowed import boundary。
- State：无 durable job state；生成脚本是纯本地 plan generation。
- Recognition：采用当前 Fins domain 可自洽的保守识别规则：
  - 只处理 upload 类命令可接受后缀的普通文件。
  - 文件名匹配常见 filing form token 时生成 `upload_filing`。
  - 文件名匹配用户传入的 `material_forms` token 时生成 `upload_material`。
  - 无法识别的文件跳过；全部跳过时 exit 1 并输出原因。

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py tests/cli/test_fins_commands.py -q`
  - 结果：28 passed，3 warnings（第三方 `edgar` deprecation warnings）。
- `source .venv/bin/activate && pytest tests/cli tests/fins/test_upload_batch.py -q`
  - 结果：89 passed，3 warnings（第三方 `edgar` deprecation warnings）。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：0 errors，0 warnings，0 informations。
- `git diff --check`
  - 结果：通过，无输出。
- `source .venv/bin/activate && pytest tests/fins/test_upload_batch.py tests/cli/test_upload_filings_from_command.py --cov=dayu.fins.upload_batch --cov=dayu.cli.commands.fins --cov-report=term-missing -q`
  - 结果：15 passed；`dayu/fins/upload_batch.py` 覆盖率 96%。
- `source .venv/bin/activate && pytest tests/cli/test_fins_commands.py tests/cli/test_upload_filings_from_command.py --cov=dayu.cli.commands.fins --cov-report=term-missing -q`
  - 结果：22 passed；`dayu/cli/commands/fins.py` 覆盖率 90%。

## README decision

- 已更新 `dayu/fins/README.md`：新增 `Batch upload plan` 小节，只记录当前已实现 capability 和边界。
- 已更新 `tests/README.md`：把 CLI 测试说明从 `upload_filings_from` unsupported 更新为目录扫描、识别、quoting、output、错误码和 SIGINT 覆盖。
- 未更新 `dayu/service/README.md`：本 slice 未新增或改变 Service public helper。
- 未更新 `dayu/README.md`：本 slice 没有改变跨层关系或装配方式。

## Residual risks

- `fixed in current slice`：`upload_filings_from` 不再启动 ingestion job，不创建 Host Run，不写 Host EventLog，测试通过禁止创建 Fins direct service。
- `fixed in current slice`：source dir 不存在映射 exit 2；无可识别文件与 output 写失败映射 exit 1；扫描期 `KeyboardInterrupt` 映射 exit 130。
- `deferred-with-owner`：文件名识别规则是当前 Fins domain 下的保守规则，不迁移旧实现的隐式识别细节。若后续需要旧 CLI 完全 parity，应由 Fins owner 定义更完整的 typed recognition contract；当前 owner 仍为总控中的 `WU-CLI-01-RR-04`。

## Completion status

CLI-01-S6 implementation 完成。未 commit、未 push、未进入 review gate。
