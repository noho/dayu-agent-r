# WU-CLI-01 / CLI-01-S7 implementation review controller adjudication

## Gate

- gate: implementation review
- slice: CLI-01-S7 init current-schema workspace bootstrap
- design source: `docs/host/design.md`, `docs/engine/design.md`
- plan source: `docs/host/wu-cli-01-cli-entrypoint-plan.md`
- implementation report: `docs/reviews/wu-cli-01-s7-implementation-codex.md`
- review artifacts:
  - `docs/reviews/wu-cli-01-s7-implementation-review-mimo.md`
  - `docs/reviews/wu-cli-01-s7-implementation-review-ds.md`

## Controller decision

pass-with-fix。

S7 implementation 迁移的是旧 `init` 的用户可见 workspace bootstrap 业务语义，并适配当前 `ConfigLoader`
schema；未搬迁旧 provider interactive、旧 workspace migrations、旧 `llm_models.json` / `run.json`
兼容实现。Host / Service / Fins 边界未被突破。

## Finding adjudication

### S7-RV-F01：legacy asset guard 对 prompts 子目录同名文件存在误伤风险

- 来源：DS review。
- 裁决：rejected-with-reason。
- 理由：当前 slice 要求复制当前包内 `dayu/config/prompts` assets，当前 prompts 资产不存在 `run.json` /
  `llm_models.json` 同名文件，现实现不会影响当前 success signal。该 guard 是防止 legacy config filename
  进入生成结果的 fail-closed 防御；未来若确实需要新增同名 prompt asset，应由 prompt asset/schema owner
  先裁决命名语义，而不是在当前 init slice 放宽防线。

### S7-RV-F02：`reset` 未在 `ParsedCliArgs` 默认 namespace 中显式初始化

- 来源：DS review。
- 裁决：accepted。
- 理由：`run_init_command` 读取 `args.reset`，`reset` 与 `overwrite` 同属 init 布尔参数。虽然生产路径经
  argparse `store_true` 会设置该属性，但 `ParsedCliArgs` 是 CLI runner 之间共享的 typed namespace，应显式声明
  并在 `_new_default_namespace()` 中初始化，避免 typed contract 与 runtime attribute 不一致。
- Fix 要求：
  - 在 `ParsedCliArgs` 中补充 `reset: bool`。
  - 在 `_new_default_namespace()` 中设置 `namespace.reset = False`。
  - 补充或调整测试，证明 synthetic / default namespace 下 `reset` 存在且默认为 `False`。

### S7-RV-F03：`workspace/config` 为普通文件时错误消息不够精确

- 来源：DS review。
- 裁决：rejected-with-reason。
- 理由：该场景当前已安全失败并返回 exit 1，不会覆盖用户文件、不会生成半成品成功状态，也不会突破 reset 或
  config schema 边界。错误消息精细化属于低价值 UX polish，不影响本 slice 的 current-schema bootstrap、
  reset data-loss 防线或 Host / Fins 边界。

## Residual risks

- reset 过程中 SIGINT 可能形成白名单路径部分删除状态；白名单路径均为可重建路径，后续可重新执行
  `init --reset --overwrite` 恢复，当前 classified as accepted low residual risk。
- config copy 是逐文件 temp + `os.replace`，不是目录级事务；复制阶段 SIGINT 返回 130 且不输出成功，当前
  classified as accepted low residual risk。

## Validation evidence reviewed

- `source .venv/bin/activate && pytest tests/cli/test_init_command.py tests/cli/test_arg_parsing.py tests/runtime/test_config_loader.py -q`：74 passed。
- `source .venv/bin/activate && pytest tests/cli -q`：93 passed。
- `source .venv/bin/activate && pytest tests/cli/test_init_command.py tests/cli/test_arg_parsing.py --cov=dayu.cli.commands.init --cov=dayu.cli.main --cov-report=term-missing -q`：34 passed；`dayu/cli/commands/init.py` 88%，`dayu/cli/main.py` 95%。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

## Next gate

AgentCodex fix gate，修复 accepted finding S7-RV-F02。禁止进入 re-review、commit、push 或 PR。
