# WU-CLI-PROMPT-01 S5 Review Fix

- Work unit: `WU-CLI-PROMPT-01`
- Gate: `review fix`
- Slice: `S5 — Complete logging selector and debug-stream contract`
- Owner: `controller`
- Timestamp: `2026-07-31 19:13:28 +0800`
- Review: `docs/reviews/code-review-20260731-191135.md`
- Decision before fix: `needs-fix/re-review`

## Finding 01：log-file 与合法 debug-stream 组合证据缺口

从既有 `_NON_QUIET_LOG_LEVEL_SELECTOR_CASES` 单一 selector 真源派生 14 个 case，并增加无
selector 的 standalone case，共 15 个合法 argv shape。每个 case 同时携带
`--debug-stream --log-file diagnostics.log`，直接断言 canonical ordinary level、
`debug_stream=True` 与 log-file path 三个事实均被保留。没有新增第二份 spelling/spec，也没有
修改生产 parser。

## Finding 02：修改函数 docstring 不完整

为 `test_parse_cli_args_accepts_debug_stream` 与
`test_parse_cli_args_accepts_debug_and_debug_stream_combination` 补齐中文 `:returns:` 和
`:raises:`；测试逻辑不变。

## 验证

- `pytest -q tests/cli/test_arg_parsing.py`：`428 passed`。
- `pytest -q tests/cli/test_arg_parsing.py tests/runtime/test_log.py tests/runtime/test_log_levels.py tests/fins/test_sec_downloader.py`：`592 passed`。
- `pyright tests/cli/test_arg_parsing.py`：`0 errors, 0 warnings, 0 informations`。
- `ruff check tests/cli/test_arg_parsing.py`：通过。
- `git diff --check`：通过。

## Scope 判定

本轮只修改 `tests/cli/test_arg_parsing.py` 并新增 review-fix artifact；没有改生产代码、冻结
oracle/scenario、README 或其它 slice 行为。

## Gate 结论

两项 review finding 已按建议修复，返回同一 S5 reviewer 复审。
