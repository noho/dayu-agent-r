# WU-CLI-01 / CLI-01-S1 Implementation Review Controller Adjudication

## Gate

- Work unit: WU-CLI-01
- Slice: CLI-01-S1
- Gate: implementation review controller adjudication
- Review artifacts:
  - `docs/reviews/wu-cli-01-s1-implementation-review-mimo.md`
  - `docs/reviews/wu-cli-01-s1-implementation-review-ds.md`
- Implementation report: `docs/reviews/wu-cli-01-s1-implementation-codex.md`

## Controller Verdict

结论：pass-with-fix。

MiMo 未发现实质性问题，DS 确认 S1 scope、命令面、exit code、README、测试和 pyright 均通过，但提出两个 low severity findings。总控接受这两个 finding，要求进入 fix gate 后再 re-review。

## Accepted Findings

| ID | Severity | Finding | Controller decision |
|---|---|---|---|
| S1-IMPL-F01 | low | `dayu/cli/arg_parsing.py` 多个函数签名直接暴露 `argparse._SubParsersAction[...]` 私有类型。 | accepted；应收敛为本模块内部公共描述，避免在多个签名散落依赖 stdlib 私有类型名。 |
| S1-IMPL-F02 | low | `dayu/cli/main.py` 在 `COMMAND_RUNNERS` 缺失 runner 时静默返回 `EXIT_FAILURE`，缺少 stderr 诊断。 | accepted；应输出清晰内部 dispatch 诊断，并补测试。 |

## Non-Blocking Observations

- S1 没有 Host / Fins business execution，符合 accepted plan。
- S1 没有复制旧 dayu-agent 实现代码，仅迁移用户可见 command surface 与 parser/help 语义。
- `interactive --help` 包含 optional `--ticker`。
- 当前验证结果：`pytest tests/cli -q` 24 passed；CLI coverage 98%；`python -m pyright dayu/ tests/ utils/` 0 errors；`git diff --check` clean。

## Fix Gate Requirements

- AgentCodex 只修复 S1-IMPL-F01 与 S1-IMPL-F02，不扩大 S1 scope。
- 不实现 S2-S7，不触达 Host/Fins business execution。
- 更新或补充 `tests/cli/test_arg_parsing.py`，覆盖 runner 缺失 stderr 诊断。
- 修复后运行：
  - `source .venv/bin/activate && pytest tests/cli -q`
  - `source .venv/bin/activate && pytest tests/cli --cov=dayu.cli --cov-report=term-missing -q`
  - `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - `git diff --check`
- 写 fix report：`docs/reviews/wu-cli-01-s1-implementation-fix-codex.md`。
