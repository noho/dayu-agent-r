# WU-ENGINE-01 PR Follow-up Test Helper Cleanup — AgentDS Review

## 结论：PASS

无 blocking / high / medium finding。一项 low-observation 供参考。

---

## 1. 重复 helper 是否真实清除，测试语义是否保持不变

### 证据

对比三个测试文件的 git diff：

| 文件 | 删除 `_leaf_strings` | 删除 `_serialized_size` | 清理未使用 import | 调用点更新 |
|---|---|---|---|---|
| `test_diagnostic_payload.py` | 18 行 | 9 行 | `Iterator, Mapping` | `_leaf_strings` → `leaf_strings`, `_serialized_size` → `serialized_size` |
| `test_http_error_event.py` | 16 行 | 9 行 | `Iterator`（`Mapping` 保留，另有他用） | 同上；额外修复变量名遮蔽：`leaf_strings = tuple(_leaf_strings(...))` → `leaf_values = tuple(leaf_strings(...))` |
| `test_protocol_error.py` | 16 行 | 9 行 | `Iterator, Mapping` | 同上 |

共享实现 `tests/engine/runners/openai/_diagnostic_helpers.py` 的 `leaf_strings` / `serialized_size` 与删除的三份副本逻辑完全一致（均使用 `isinstance(value, str/Mapping/list)` 递归遍历 + `json.dumps(value, ensure_ascii=False).encode("utf-8")`）。

`_canonical_metadata` 仅在 `test_diagnostic_payload.py` 中使用，未提取——正确，避免过早抽象。

### 判定：PASS

重复已彻底清除。所有测试断言语义不变。`test_http_error_event.py` 中额外修复了局部变量名遮蔽函数名的隐患，属于净收益。

---

## 2. 新 helper 类型/docstring/import 边界是否符合 AGENTS.md

### 模块级 helper vs conftest fixture

选择模块级 `_diagnostic_helpers.py` 而非 `conftest.py` fixture 是正确的：

- `tests/README.md` 第 186 行明确约定："测试 helper 可以放在对应测试子目录内，例如 `_fakes.py`、`_factories.py`、`_sse_helpers.py`。"
- 同目录已有 `_fakes.py`、`_factories.py`、`_sse_helpers.py` 遵循完全相同的模式：纯函数模块，由测试文件显式 import 使用。
- `conftest.py` fixture 会被 pytest 自动发现并注入到该目录下所有测试函数的作用域，而 `leaf_strings` / `serialized_size` 仅在 3 个文件的少数测试中使用，不需要全局注入。
- 这两个 helper 是纯函数，不依赖 pytest fixture 生命周期，不持有状态——做成 fixture 是过度设计，不符合 AGENTS.md "不做过度设计，以最小化满足需求为标准"。

### 类型与 docstring

`_diagnostic_helpers.py`:

- 模块级中文 docstring："OpenAI runner 诊断测试通用 helper。" — 符合要求。
- `leaf_strings(value: JsonValue) -> Iterator[str]` — 无 `Any`/`object`/裸容器返回。符合"禁止使用 `object`、`Any`、无类型参数、无类型返回值"。
- `serialized_size(value: JsonValue) -> int` — 同上。
- 两个函数均提供完整中文 docstring，含 `:param`、`:returns`、`:raises`。符合"函数必须提供完整中文 docstring"。
- `from __future__ import annotations` — 与项目约定一致。
- `__all__` 显式声明公开符号 — 良好的模块边界实践。

### import 边界

- `_diagnostic_helpers.py` 依赖 `dayu.contracts.json_value.JsonValue`（公共契约层）、`json`（标准库）、`collections.abc`（标准库）——无反向依赖，无跨层泄漏。
- 三个测试文件的 import 从 `tests.engine.runners.openai._diagnostic_helpers` 导入，与从 `_factories`、`_fakes` 导入的模式一致。

### 判定：PASS

设计完全符合 AGENTS.md 和项目既有约定。

---

## 3. 是否引入测试 import 依赖问题、vacuous tests 或生产代码改动

### import 依赖

- 无循环依赖风险：`_diagnostic_helpers.py` 只依赖标准库 + 公共契约层；三个测试文件单向依赖它。
- 无跨目录 import 逃逸：所有 import 在 `tests/engine/runners/openai/` 包内闭环。

### vacuous tests

- 未删除任何测试用例或断言。删除的仅是私有 helper 定义，调用点全部迁移到共享实现。
- 共享 helper 本身不需要独立单元测试——它们被 3 个文件的 10+ 个测试用例充分覆盖（每次 `serialized_size(diagnostic) <= _DIAGNOSTIC_PAYLOAD_MAX_BYTES` 和 `leaf_strings(diagnostic)` 调用都间接验证了 helper 正确性）。

### 生产代码改动

- 零改动。diff 仅触及 `tests/` 目录。

### 判定：PASS

无 import 问题、无 vacuous tests、无生产代码改动。

---

## 4. README 不更新判断是否合理

### Codex 判断

> 本次变更只提取测试目录内部纯 helper，不改变测试分层、运行命令、目录职责或维护约定。按 README 触发规则检查后，`tests/README.md` 无需更新。

### AgentDS 验证

按 AGENTS.md README 触发规则"`tests/` 修改 -> 更新 `tests/README.md`"，但规则同时要求"先检查变更是否属于该 README 的职责范围与目标读者；只有属于时才实际修改，不做机械同步。"

`tests/README.md` 的职责是"测试分层、运行方式、约定与维护规则"：

1. **测试分层**：未变化——仍在 `tests/engine/runners/openai/`。
2. **运行方式**：未变化——`pytest tests/engine/runners/openai/` 仍可运行。
3. **维护约定**：第 186 行已记录模式——"测试 helper 可以放在对应测试子目录内，例如 `_fakes.py`、`_factories.py`、`_sse_helpers.py`。" `_diagnostic_helpers.py` 完全遵循此模式，无新增约定。

### 判定：PASS

README 不更新判断合理。新增文件遵循已有文档约定，不改变测试分层或维护规则。

### Low Observation（可选）

`tests/README.md` 第 176 行："本目录内已有 `_fakes.py`、`_factories.py`、`_sse_helpers.py` 作为局部测试 helper。" 这是一个事实描述语句，现在多了一个 `_diagnostic_helpers.py`。该语句是描述性举例而非规范性白名单，不更新不会造成误导。如需追求描述完整，可追加 `_diagnostic_helpers.py`，但这不是必须的——README 约定已通过第 186 行通用规则覆盖。

---

## 总结

| 审查维度 | 判定 |
|---|---|
| 重复 helper 清除 & 语义保持 | PASS |
| 设计符合 AGENTS.md | PASS |
| import / vacuous tests / 生产代码 | PASS |
| README 判断 | PASS + 1 low observation |

**最终结论：PASS。** 变更范围精准、实现正确、符合项目架构与编码约束。48 个测试全部通过，pyright 零报错。无需阻塞项。
