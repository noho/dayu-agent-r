# WU-ENGINE-01 PR Follow-up Test Helper Cleanup Review

- **审查者**: AgentMiMo
- **日期**: 2026-06-02
- **结论**: **PASS**

## 审查范围

| 文件 | 角色 |
|------|------|
| `tests/engine/runners/openai/_diagnostic_helpers.py` | 新增共享 helper 模块 |
| `tests/engine/runners/openai/test_diagnostic_payload.py` | 删除本地 `_leaf_strings` / `_serialized_size`，改为导入 |
| `tests/engine/runners/openai/test_http_error_event.py` | 同上 |
| `tests/engine/runners/openai/test_protocol_error.py` | 同上 |
| `docs/reviews/wu-engine-01-pr-followup-test-helper-cleanup-codex-20260602.md` | Codex 自述文档 |

## 审查项逐条结论

### 1. 重复 helper 是否真实清除

**PASS**。

`_leaf_strings` 与 `_serialized_size` 从三个测试文件中完整删除。grep 确认 `tests/engine/runners/openai/` 下不存在 `_leaf_strings` 或 `_serialized_size` 的任何残留引用。

新 helper 的函数体与旧实现逐行等价：
- `leaf_strings`：str → yield / Mapping → recurse values / list → recurse items，逻辑一致。
- `serialized_size`：`json.dumps(value, ensure_ascii=False).encode("utf-8")` + `len`，逻辑一致。

### 2. 测试语义是否保持不变

**PASS**。

所有调用点从 `_leaf_strings(...)` 改为 `leaf_strings(...)`、`_serialized_size(...)` 改为 `serialized_size(...)`，断言逻辑无变化。

额外值得注意：`test_http_error_event.py:551` 将局部变量名从 `leaf_strings` 改为 `leaf_values`，消除了与导入名 `leaf_strings` 的遮蔽。此变更不影响测试语义，反而提升了可读性，属于正面改进。

### 3. 新 helper 类型 / docstring / import 边界是否合规

**PASS**。

- 函数签名完整类型化：`JsonValue` 参数、`Iterator[str]` / `int` 返回值。
- docstring 使用 `:param:` / `:returns:` / `:raises:` 格式，中文描述，符合 AGENTS.md。
- `__all__` 显式导出。
- `JsonValue` 从 `dayu.contracts.json_value` 导入，`Iterator` / `Mapping` 从 `collections.abc` 导入，无反向依赖。

### 4. 是否该用 conftest fixture

**不需要**。

这两个函数是纯工具函数，不是 pytest fixture，不依赖 pytest 生命周期。放在 `_diagnostic_helpers.py`（下划线前缀的私有模块）是正确选择。同目录已有 `_sse_helpers.py`、`_factories.py`、`_fakes.py` 等同模式模块，命名与组织一致。

### 5. 是否引入测试 import 依赖问题

**PASS**。

三个消费文件各自独立导入 `_diagnostic_helpers`，无循环依赖。`_diagnostic_helpers.py` 只依赖 `dayu.contracts.json_value` 和标准库，不依赖任何测试文件或被测生产代码。

### 6. 是否有 vacuous tests 或生产代码改动

**PASS**。

- 未新增、删除或修改任何测试用例。
- 未改动任何生产代码文件。
- `git diff` 确认变更范围严格限定在 4 个测试文件 + 1 个新增 helper 模块。

### 7. `_canonical_metadata` 未提取判断

**合理**。

`_canonical_metadata` 仅在 `test_diagnostic_payload.py` 内使用，其它两个测试文件无调用点。按 YAGNI 原则，不提取为共享 helper 是正确判断。

### 8. README 不更新判断

**合理**。

本次变更是测试目录内部纯 helper 提取，不改变：
- 测试分层结构
- 运行命令
- 目录职责
- 维护约定

`tests/README.md` 无需更新，符合 README 触发规则。

## 未覆盖项

无。

## 剩余风险

无。变更范围限于测试 helper 提取，未改生产代码，测试语义等价，类型与 docstring 合规。
