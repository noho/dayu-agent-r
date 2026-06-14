# WU-CLI-01 / CLI-01-S7 implementation re-review controller adjudication

## Gate

- gate: implementation re-review
- slice: CLI-01-S7 init current-schema workspace bootstrap
- fix artifact: `docs/reviews/wu-cli-01-s7-implementation-fix-codex.md`
- re-review artifacts:
  - `docs/reviews/wu-cli-01-s7-implementation-rereview-mimo.md`
  - `docs/reviews/wu-cli-01-s7-implementation-rereview-ds.md`

## Controller decision

pass。

## Finding status

- S7-RV-F02：已修复。
  - `ParsedCliArgs` 已声明 `reset: bool`。
  - `_new_default_namespace()` 已初始化 `namespace.reset = False`。
  - `tests/cli/test_arg_parsing.py::test_default_namespace_initializes_reset_false` 覆盖 init 与非 init parser path 下的
    `reset=False` 默认值。

## New findings

无。

## Rejected findings status

- S7-RV-F01：保持 rejected-with-reason。fix 未修改 legacy asset guard，未出现新直接证据证明它变成当前阻塞问题。
- S7-RV-F03：保持 rejected-with-reason。fix 未修改 workspace/config 文件错误路径，未出现新直接证据证明它变成当前阻塞问题。

## Validation

Controller 复核：

- `source .venv/bin/activate && pytest tests/cli/test_arg_parsing.py tests/cli/test_init_command.py -q`：35 passed，3 条 edgar deprecation warnings。
- `source .venv/bin/activate && pytest tests/cli -q`：94 passed，3 条 edgar deprecation warnings。
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`：0 errors。
- `git diff --check`：clean。

Re-review artifacts 均记录 S7-RV-F02 已修复，未发现新问题。

## Residual risks

- reset 过程中 SIGINT 可能形成白名单路径部分删除状态；白名单路径均为可重建路径，后续可重新执行
  `init --reset --overwrite` 恢复，classified as accepted low residual risk。
- config copy 是逐文件 temp + `os.replace`，不是目录级事务；复制阶段 SIGINT 返回 130 且不输出成功，
  classified as accepted low residual risk。

## Next gate

Accepted slice commit。随后进入 WU-CLI-01 aggregate deepreview gate。
