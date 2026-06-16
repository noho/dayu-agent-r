# WU-CLI-SESSION-01 S1 Fix Report

## Accepted Findings Fixed

- DS F-01：新增 fresh Host durable store 空库边界测试，验证没有任何 Session 时 `list_sessions(command_handle).sessions == ()`。
- DS F-02：将 `_slot_row_from_session_list_host_row` 的 slot alias 读取改为复用现有 durable row decode helper。预期 alias 缺失时现在抛出结构化 `HostRowDecodeError`，字段类型错误也进入同一 row decode 错误边界；正常 LEFT JOIN 全空时仍返回 `None`，部分为空时仍 fail closed。

说明：核对当前代码后，`HostRow.get()` 缺列实际会抛 `KeyError`，不是 `dict.get()` 风格的静默 `None`。本次修复的真实根因是缺列错误没有按 durable row decode 风格结构化，而不是正常路径语义错误。

## Files Changed

- `dayu/host/durable/state.py`
  - `_slot_row_from_session_list_host_row` 改用 `_decode_optional_text` / `_decode_optional_int` 解码 list join slot alias。
  - 更新函数 docstring 的异常说明。
- `tests/host/test_public_session_api.py`
  - 新增空 durable store 的 `list_sessions` 边界测试。
  - 新增 slot join row 缺 alias 时抛 `HostRowDecodeError` 的回归测试。
- `docs/reviews/wu-cli-session-01-s1-fix-codex.md`
  - 记录本 fix gate 的修复、验证与残余风险。

## Validation Results

- `source .venv/bin/activate && pytest tests/host/test_public_session_api.py tests/host/test_package_exports.py -q`
  - 通过：`28 passed in 0.36s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 通过：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 通过：无输出

## Residual Risks

- 按 gate 要求未处理 N+1 query / pagination。
- `_slot_row_from_session_list_host_row` 中 pyright narrowing asserts 保持不变，未做非必要改动。
- README 触发项已检查；本次为局部 fix gate，且允许写文件不包含 README，未做 README 修改。
