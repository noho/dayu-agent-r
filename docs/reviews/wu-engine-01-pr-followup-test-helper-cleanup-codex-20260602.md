# WU-ENGINE-01 PR Follow-up Test Helper Cleanup

## 结论

RR-ENGINE-01-01 指出的测试 helper 重复真实存在，重复点为
`tests/engine/runners/openai/test_diagnostic_payload.py`、
`tests/engine/runners/openai/test_http_error_event.py`、
`tests/engine/runners/openai/test_protocol_error.py` 中的
`_leaf_strings` 与 `_serialized_size`。本次已提取为同目录共享测试 helper，
测试断言语义保持不变。

## 修改

- 新增 `tests/engine/runners/openai/_diagnostic_helpers.py`：
  - `leaf_strings(value: JsonValue) -> Iterator[str]`
  - `serialized_size(value: JsonValue) -> int`
- 更新三处 OpenAI runner 测试文件，删除本地重复 helper，改为显式导入共享 helper。
- `_canonical_metadata` 仅在 `test_diagnostic_payload.py` 内使用，未提取。

## 验证

- `source .venv/bin/activate && pytest -q tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_http_error_event.py tests/engine/runners/openai/test_protocol_error.py`
  - 结果：`48 passed in 0.21s`
- `source .venv/bin/activate && pyright tests/engine/runners/openai/test_diagnostic_payload.py tests/engine/runners/openai/test_http_error_event.py tests/engine/runners/openai/test_protocol_error.py`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && pyright`
  - 结果：`0 errors, 0 warnings, 0 informations`

## README 判断

本次变更只提取测试目录内部纯 helper，不改变测试分层、运行命令、目录职责或维护约定。
按 README 触发规则检查后，`tests/README.md` 无需更新。

## 剩余风险

- 变更范围限于测试 helper 与三处调用点，未改生产代码。
- 未发现未覆盖项；后续等待 controller review。
