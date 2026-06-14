# WU-CLI-01 / CLI-01-S7 implementation report

## Gate

- gate: implementation
- slice: CLI-01-S7 init current-schema workspace bootstrap and docs/tests closure
- design source: `docs/host/design.md`, `docs/engine/design.md`
- accepted plan: `docs/host/wu-cli-01-cli-entrypoint-plan.md`

## Motivation check

问题真实存在：当前 CLI parser 已注册 `init`，但命令 runner 仍是占位行为，无法按当前
`ConfigLoader` schema 初始化 workspace。严重性评估成立，因为后续 `prompt` /
`interactive` 默认会使用 `workspace/config` overlay；若 init 仍生成旧 schema 或继续占位，
会破坏 current runtime assembly。

本 slice 没有实现旧 init 的 provider catalog interactive 体验。原因是该体验若要写回模型选择，
需要先裁决当前 `models.json` typed records 与 execution profile 的写入语义；这命中本任务 stop
condition，应回到 schema/design gate，而不是在 CLI 中硬编码兼容。

## Changed files

- `dayu/cli/commands/init.py`
  - 新增 `dayu-cli init` runner。
  - 创建 workspace root。
  - 复制当前 `dayu/config` 的 `config_file_names()` 配置文件和 `prompts/` 资产到
    `workspace/config`。
  - 使用 temp file + `os.replace` 逐文件原子替换。
  - 默认拒绝覆盖已有目标文件；`--overwrite` 允许替换。
  - `--reset` 只删除硬编码白名单路径。
- `dayu/cli/main.py`
  - 将 `init` 接入真实 runner 分发。
- `tests/cli/test_init_command.py`
  - 新增 init 行为测试。
- `tests/cli/test_arg_parsing.py`
  - 把旧的 `init` 占位 runner 断言改为 synthetic future command，避免与 S7 真实实现冲突。
- `dayu/config/README.md`
  - 按 README 职责补充 `dayu-cli init` 对 current schema workspace config 的 bootstrap 语义。
- `tests/README.md`
  - 记录新增 CLI init 测试覆盖面。
- `docs/reviews/wu-cli-01-s7-implementation-codex.md`
  - 本 implementation artifact。

## Boundary decisions

- CLI init 只做 filesystem bootstrap；不打开 Host，不创建 Fins job，不触达 Service helper，不执行旧
  workspace migrations。
- 不生成 `llm_models.json` / `run.json`。
- 不写 API key 明文，不做 provider interactive 写回。
- 未新增 Service helper，因此不更新 `dayu/service/README.md`。
- 未新增 `dayu/fins/upload_batch.py`，因此不更新 `dayu/fins/README.md`。
- 未改变 UI / Service / Host / Engine 边界说明，因此不更新 `dayu/README.md`。
- 虽然 allowed files 未单列 `dayu/cli/main.py` 与 `tests/cli/test_arg_parsing.py`，但真实实现
  `dayu-cli init` 必须接入 main 分发，且旧测试对 `init` 占位行为的断言必须同步迁移；改动已限制在
  直接必要范围。

## Reset safety

`--reset` 删除白名单为硬编码路径：

- `<workspace>/config/`
- `<workspace>/.dayu/host/`
- `<workspace>/.dayu/artifacts/`
- `<workspace>/.dayu/web_tools_storage_states/`

删除前先对全部白名单做预检：

- 白名单路径本身是 symlink：fail fast，exit 2。
- resolve 后不在 workspace root 内：fail fast，exit 2。
- 任一白名单不安全时，不执行任何删除。
- 不存在的白名单路径跳过。

测试显式确认以下路径保留：

- `<project_root>/.dayu/fins_ingestion/jobs/`
- `<project_root>/.dayu/sec_cache/`
- `<workspace>/fins/`
- `<project_root>/fins/`
- `<workspace>/.dayu/runtime/runtime_lanes.sqlite3`
- workspace 普通用户文件

## Validation

- `source .venv/bin/activate && pytest tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/runtime/test_config_loader.py -q`
  - 73 passed
- `source .venv/bin/activate && pytest tests/cli -q`
  - 93 passed
- `source .venv/bin/activate && pytest tests/cli/test_init_command.py tests/cli/test_arg_parsing.py --cov=dayu.cli.commands.init --cov=dayu.cli.main --cov-report=term-missing -q`
  - `dayu/cli/commands/init.py`: 88%
  - `dayu/cli/main.py`: 95%
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 0 errors, 0 warnings

## Residual risks

- provider interactive 体验未实现；这是刻意 deferred，因为需要当前 config schema/design 先裁决写回语义。
- copy 是逐文件原子替换，不是整个 `workspace/config` 目录级事务；SIGINT 不输出成功，可能残留未替换的临时文件或已成功替换的部分文件。该行为符合当前 slice 的 cancel 要求。
