# WU-CLI-01 / CLI-01-S5 Implementation Report

## Gate / Scope

- Gate: implementation。
- Work unit: WU-CLI-01。
- Slice: CLI-01-S5，Fins direct job Service boundary and direct commands。
- 设计真源: `docs/host/design.md`、`docs/engine/design.md`。
- 总控文档: `docs/host/ui-implementation-control.md`。
- Accepted plan: `docs/host/wu-cli-01-cli-entrypoint-plan.md`。

## 第一性原理裁决

本 slice 动机成立：Fins direct commands 是数据入口，不是 Host Run。它们需要复用 Fins runtime 的 durable job、poll 与 cancel 真源，否则 CLI 会复制 ingestion 编排或绕过 `dayu.fins.storage` 仓储协议。当前实现按 accepted Service/Fins boundary 收敛到 `dayu.service.fins_direct`，CLI 只做参数转换、轻量用户输入校验和 SIGINT 映射。

## 实施内容

- 新增 `dayu/service/fins_direct.py`：
  - `FinsDirectCommandService` 封装 `start_download`、`start_preprocess`、`start_upload_filing`、`start_upload_material`、`wait_for_terminal`、`request_cancel`。
  - upload wrapper 构造 `FinsUploadFilingRequest` / `FinsUploadMaterialRequest` 后调用 `runtime.start_upload(request)`。
  - poll 默认 `DEFAULT_FINS_DIRECT_POLL_INTERVAL_SECONDS = 1.0`；`QUEUED` / `RUNNING` / `CANCELLING` 继续等待，`SUCCEEDED` / `FAILED` / `CANCELLED` 映射到 0 / 1 / 130。
- 新增 `dayu/cli/commands/fins.py`：
  - 接入 `download`、`upload_filing`、`upload_material`、`process`、`process_filing`、`process_material`。
  - `upload_filings_from` 保留 parser，执行时报 unsupported，归属 CLI-01-S6。
  - `--infer` / `--ci` fail fast，exit 2。
  - ticker CSV 解析为 canonical ticker + aliases；aliases 只传 upload request 支持字段。
  - upload file path 前置校验仅覆盖存在性、普通文件和扩展名 allowlist。
  - 第一次 SIGINT after job id 调用 `request_cancel(job_id)` 并继续 poll；第二次 SIGINT 本地 130 并打印 job id。
- 更新 `dayu/cli/output.py` 的 Fins direct terminal / cancel 输出。
- 更新 `dayu/cli/arg_parsing.py` 的 Fins command 字段默认值，避免命令 runner 读取未注册字段时报错。
- 更新 `dayu/cli/main.py` 注册 Fins direct command runner。
- 更新测试：
  - `tests/service/test_fins_direct.py` 覆盖 typed request、upload wrapper、poll sleep、cancel、terminal mapping。
  - `tests/cli/test_fins_commands.py` 覆盖六个 command 参数转换、unsupported、cancel path、terminal mapping、no CLI direct `dayu.fins.storage` import。
  - `tests/cli/test_arg_parsing.py` 将 S1 placeholder runner 断言从已实现的 `download` 改为仍未实现的 `init`。
  - `tests/service/test_import_boundary.py` 将 approved Fins direct Service boundary 加入 import whitelist。
- README 同步：
  - `dayu/README.md`：记录 Fins direct job 不创建 Host Run，经 Service/Fins boundary 启动 / poll / cancel。
  - `dayu/service/README.md`：记录 `dayu.service.fins_direct` 当前 public helper。
  - `tests/README.md`：记录新增 CLI/Service Fins direct 覆盖和 Service import boundary 变化。

## 额外文件说明

- `dayu/cli/main.py`：必须修改，原因是 S5 要让 direct commands 从占位 runner 切换到真实 runner。
- `tests/cli/test_arg_parsing.py`：必须修改，原因是旧 S1 断言把 `download` 当作 not-implemented；S5 后该断言已过期。
- `tests/service/test_import_boundary.py`：必须修改，原因是 accepted plan 新增 approved Service/Fins boundary；旧测试只允许 wait adapter Fins import，会误判本 slice 正常依赖。
- README 文件：按 AGENTS.md README 触发规则同步。

## 验证

- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q`
  - 22 passed。
- `source .venv/bin/activate && pytest tests/cli -q`
  - 74 passed。
- `source .venv/bin/activate && pytest tests/service -q`
  - 80 passed。
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`
  - 41 passed。
- `source .venv/bin/activate && pytest tests/cli tests/service tests/fins/test_fins_ingestion_runtime.py -q`
  - 195 passed。
- `source .venv/bin/activate && pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py --cov=dayu.service.fins_direct --cov=dayu.cli.commands.fins --cov-report=term-missing -q`
  - `dayu/service/fins_direct.py`: 92%。
  - `dayu/cli/commands/fins.py`: 88%。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 0 errors。
- `git diff --check`
  - passed。

## Residual Risks

- `upload_filings_from` 未实施：covered by later approved slice CLI-01-S6，owner 为 Fins / CLI owner。
- `--infer` alias inference 未实施：deferred-with-owner，沿用总控 `WU-CLI-01-RR-01`，owner 为 Fins owner / 后续 alias inference WU。
- `--ci` process snapshot 未实施：deferred-with-owner，沿用总控 `WU-CLI-01-RR-02`，owner 为 Fins / tooling owner。
- Fins cancel responsiveness 仍取决于 ingestion runtime 与具体 pipeline checkpoint：deferred-with-owner，沿用总控 `WU-CLI-01-RR-06`，owner 为 Fins runtime owner。

## Completion Status

CLI-01-S5 implementation complete。本报告不包含 commit、push 或 PR 动作。
