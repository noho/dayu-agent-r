# WU-CLI-INIT-01 S1 Implementation

## Gate metadata

- Gate：`implementation`
- Work unit：`WU-CLI-INIT-01`
- Slice：`S1 — CLI public parser contract`
- 日期：2026-07-30
- Scope：移除 init `--config` 与 `--model-name`，建立正式
  `--model/-m`，并保持非 init runtime 命令的 `--config` command 前后位置语义。
- Artifact path：
  `docs/reviews/wu-cli-init-01-s1-implementation-codex.md`

## Semantic owner decisions

- CLI 可见参数、help 与 parser usage exit 2 的唯一 owner 是
  `dayu.cli.arg_parsing`。
- invocation-local 主模型 override 的 typed source of truth 是
  `ParsedCliArgs.model`。
- CLI typed namespace 到 Service assembly 的唯一共享映射点是
  `dayu.cli.session_execution._prepare_session_runtime(...)`，映射目标为
  `ServiceAssemblyOverrides.model_id`。
- init runner、command runner 与 Service 不增加忽略参数、fallback、alias 或
  compatibility shim。

## Changed files

- `dayu/cli/arg_parsing.py`
- `dayu/cli/session_execution.py`
- `tests/cli/test_arg_parsing.py`
- `tests/cli/test_prompt_command.py`
- `tests/cli/test_interactive_command.py`
- `tests/cli/test_session_command.py`
- `docs/reviews/wu-cli-init-01-s1-implementation-codex.md`

## Implemented contract

1. parser 建立不含 `--config` 的 common parent，以及在 common parent 上增加
   `--config` 的 runtime parent。
2. 顶层 parser 与所有非 init command/action 使用 runtime parent；init child
   只使用 common parent，因此 `init --help` 不展示 `--config`。
3. `init --config PATH` 由 init child 直接拒绝；`--config PATH init` 在 typed
   namespace 返回前由同一 parser owner 调用 `parser.error(...)` 拒绝；两者均
   exit 2。
4. `prompt`、`interactive`、`session resume` 的 `--config PATH` 在 command
   前后均继续精确映射到 `ParsedCliArgs.config_dir`。
5. 正式模型参数为 `--model/-m`，typed 字段为 `ParsedCliArgs.model`；
   `--model-name` 与 `ParsedCliArgs.model_name` 均删除且不保留兼容。
6. 三个 Agent surface 的模型参数均经共享 session execution owner 精确映射到
   `ServiceAssemblyOverrides.model_id`；空白诊断字段同步为 `--model`。

## Tests and validation

- Focused tests：

  ```text
  source .venv/bin/activate
  pytest tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py \
    tests/cli/test_interactive_command.py tests/cli/test_session_command.py -q
  ```

  结果：`211 passed`。关键断言覆盖 init help absence、init `--config`
  command 前后 exit 2、三个非 init surface 的六个 `--config` 正向位置、
  三个 surface 的 `--model/-m` help/parse、旧参数 exit 2，以及三条
  `ServiceAssemblyOverrides.model_id` conversion。

- Coverage：

  ```text
  coverage run -m pytest tests/cli/test_arg_parsing.py \
    tests/cli/test_prompt_command.py tests/cli/test_interactive_command.py \
    tests/cli/test_session_command.py -q
  coverage report \
    --include='dayu/cli/arg_parsing.py,dayu/cli/session_execution.py'
  ```

  结果：`arg_parsing.py 100%`，`session_execution.py 80%`，合计 `89%`。

- Pyright：

  ```text
  python -m pyright dayu/cli/arg_parsing.py dayu/cli/session_execution.py \
    tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py \
    tests/cli/test_interactive_command.py tests/cli/test_session_command.py
  ```

  结果：`0 errors, 0 warnings, 0 informations`。

- Ruff：

  ```text
  python -m ruff check dayu/cli/arg_parsing.py dayu/cli/session_execution.py \
    tests/cli/test_arg_parsing.py tests/cli/test_prompt_command.py \
    tests/cli/test_interactive_command.py tests/cli/test_session_command.py
  ```

  结果：`All checks passed!`。

- Residual scan：
  - production 与 current CLI typed consumers 中无 `args.model_name`、
    `namespace.model_name` 或 `ParsedCliArgs.model_name`；
  - `--model-name` 只保留在明确断言 exit 2 / help absence 的负向 contract
    tests 中，不构成公开 alias。
- `git diff --check`：通过。

## Docs decision

- README：本 slice 不更新。用户明确限制 S1 不修改 README；accepted plan 已把
  work-unit 级 README 与 `docs/cli_ci.md` 更新分配给后续 approved S6。
- accepted oracle、goal artifact 与 plan artifact：未修改。

## Findings fixed

- Controller A03（非 init `--config` 回归面）：`已修复`，六个正向位置与两个
  init 反向位置均有 owner contract test。
- Controller R04（argparse post-parse 可达性）：`证据有效`，两条拒绝路径与
  非 init command-before 保留行为均已由 focused tests 证明。

## Residual risks

- S2-S6 的 model-family、init interaction、package defaults、workspace
  transaction、provider matrix 与 docs 工作均未在本 slice 实施。
  - classification：`covered by later approved slice`
- 当前 S1 owner boundary 内无未分类 residual risk。

## Completion

- Completion signal：`pass`
- Stop condition：`none`
- 未修改 S2+、README、accepted oracle 或 accepted plan。
- 未提交。
