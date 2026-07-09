# WU-SEMANTIC-OWNERSHIP-01 P2-B S1 Implementation Review - MiMo

## Verdict

`pass`

## Findings

无阻塞 finding。

以下为非阻塞观察项（不构成 required fix gate）：

### Observation 1: `_call_name_lines` scanner 对赋值别名链只追蹤一跳

- 文件: `tests/host/test_import_boundary.py:376-395`
- 直接证据: `_is_named_reference(...)` 只判断 `ast.Name` 和 `ast.Attribute`，赋值别名链 `a = b = ConversationMemorySnapshotVNext` 中 `a` 和 `b` 都会被收集；但 `a = some_func(ConversationMemorySnapshotVNext)` 这种间接包装不会追踪。
- 评估: 当前 `MEMORY_SNAPSHOT_CONSTRUCTOR_SCAN_FILES` 只覆盖 `test_compact_material.py` 和 `test_run_input_builder.py`，这两个文件的源码模式是直接调用或 `as` 别名调用，不需要间接包装追踪。若未来业务测试引入间接包装模式，scanner 需要扩展——但这属于 S1 non-goal 范畴外的 future change guardrail，不阻塞当前实现。

### Observation 2: `_empty_snapshot` 私有常量 `_DIGEST_PLACEHOLDER` 与工厂 placeholder 语义一致

- 文件: `tests/host/memory_snapshot_factories.py:37`
- 直接证据: `_DIGEST_PLACEHOLDER` 是全零 SHA-256 占位，`recalculate_memory_snapshot_digest(...)` 先将 `snapshot_digest` 替换为该占位再用生产 `calculate_memory_snapshot_digest(...)` 回填。
- 评估: 这是一个干净的 two-phase digest 计算模式：先构造带占位的 snapshot，再回填真实 digest。占位值不泄漏到业务测试体（source scan 已确认），且 digest 计算完全依赖生产 helper。设计合理。

### Observation 3: `test_compact_material.py` 和 `test_run_input_builder.py` 保留了 local convenience wrapper

- 文件: `tests/host/test_compact_material.py:2879-2968`, `tests/host/test_run_input_builder.py:3983-4077`
- 直接证据: `_empty_snapshot(...)`、`_snapshot_with_fact(...)`、`_snapshot_with_stable_blocks(...)`、`_rich_memory_snapshot(...)`、`_current_input_memory_snapshot(...)`、`_reference_continuity_only_snapshot(...)` 等 local helper 委托给 shared factory 函数。
- 评估: 这些 wrapper 封装了各业务测试的 session-specific 参数（如 `_SESSION_ID`、`_NOW`、`_policy(...)`），是合理的 test-local convenience layer。wrapper 内部不直接构造 `ConversationMemorySnapshotVNext(...)`，不散落 `snapshot_digest="pending"`。source scan 通过 `MEMORY_SNAPSHOT_CONSTRUCTOR_SCAN_FILES` 约束 `ConversationMemorySnapshotVNext(` 只出现在 factory 中，wrapper 的类型签名引用是 type annotation 而非 constructor call，scanner 正确区分二者。

## Review Details

### 1. 相对 import 解析是否正确覆盖

**结论: 正确覆盖。**

- `_relative_import_module_name(...)` (`test_import_boundary.py:229-276`) 接收 `scanned_file`、`package_root`、`level`、`module`，按确定性算法解析：
  - `level == 1` → 当前 package（文件 parent）
  - `level == 2` → 父 package
  - `node.module is None` → 只返回回溯后的 package prefix
  - 回溯超出 package root → `AssertionError`（fail loudly）
  - 文件不在 package root 下 → `AssertionError`
- `_imported_module_names(...)` (`test_import_boundary.py:279-310`) 现在对 `node.level > 0` 的 `ImportFrom` 调用 `_relative_import_module_name(...)`。
- 测试覆盖: `test_import_scanner_resolves_same_package_relative_import`、`test_import_scanner_resolves_parent_package_relative_import`、`test_import_scanner_resolves_no_module_relative_import`、`test_import_scanner_fails_loudly_for_unresolvable_relative_import` 全部通过。
- 所有现有边界测试 call site 使用 scanner 的新签名（`scanned_file` + `package_root`），验证结果 23 passed。

### 2. import scanner 是否可能产生 false negative

**结论: 不会产生。**

- `_imported_module_names(...)` 现在对 `ast.Import` 和 `ast.ImportFrom`（absolute + relative）统一处理。
- relative import 解析基于文件路径和 package root 的确定性推导，不依赖源码字面格式。
- 若文件不在 package root 下或回溯越界，helper 直接抛 `AssertionError`，不会静默跳过。
- 现有 Host / Runtime / Engine / Projection / Memory / Purge / WaitCallback 边界测试全部继续使用同一个 scanner，relative import 不再被漏扫。

### 3. memory snapshot factory 是否确实成为测试数据 owner

**结论: 是。**

- `memory_snapshot_factories.py` 提供 `empty_memory_snapshot(...)`、`rich_memory_snapshot(...)`、`current_input_memory_snapshot(...)`、`reference_continuity_only_snapshot(...)`、`memory_snapshot_cursor(...)`、`memory_policy_digest(...)`、`recalculate_memory_snapshot_digest(...)` 等工厂函数。
- 工厂内部使用生产 `ConversationMemorySnapshotVNext` dataclass 和 `calculate_memory_snapshot_digest(...)` / `digest_memory_projection_policy(...)` helper。
- 工厂不引入 production hook、兼容性 seam 或弱类型；所有字段类型与生产 dataclass 一致。
- 业务测试通过 `from tests.host.memory_snapshot_factories import ...` 消费工厂函数，不直接构造 snapshot。

### 4. compact / run-input 业务测试是否仍保留业务语义断言

**结论: 保留。**

- `test_compact_material.py` 保留了所有业务断言：segment selection determinism、proactive/reactive selection、recovery segment caps、degrade previous view、duplicate section owner、current input anchor dedup、vNext material mapping、snapshot cursor lag、evidence labels、pre-dispatch source builder 等。
- `test_run_input_builder.py` 保留了所有业务断言：durable user input、descriptor payload、resume wait messages、build determinism、runner-call manifest boundedness、session continuity、tool-enabled/no-tool request、memory snapshot rendering、fallback context messages 等。
- 迁移到 factory 后，测试覆盖范围未缩减；factory 只替代了 snapshot 构造和 digest 回填的重复模式。

### 5. AST source-scan 是否足够约束 pending digest 和直接 snapshot 构造

**结论: 足够。**

- `_string_keyword_value_lines(...)` 使用 AST call keyword 扫描，不依赖源码字面格式（`test_string_keyword_value_scan_uses_ast_not_literal_format` 证明空格、单引号和换行格式都能识别）。
- `_call_name_lines(...)` 使用 AST call 扫描，支持直接调用、属性调用、`as` 导入别名和简单赋值别名（`test_call_name_scan_uses_ast_not_literal_format` 证明）。
- `test_memory_snapshot_business_tests_do_not_scatter_pending_digest` 覆盖 `MEMORY_SNAPSHOT_BUSINESS_TEST_FILES` 中的 `snapshot_digest="pending"`。
- `test_memory_snapshot_constructor_stays_in_shared_factory` 覆盖 `MEMORY_SNAPSHOT_CONSTRUCTOR_SCAN_FILES` 中的 `ConversationMemorySnapshotVNext(` 直接调用。
- controller 补强了 scanner 从字符串匹配到 AST 扫描的升级，并新增了两个 scanner 单元测试。

### 6. `tests/README.md` 更新是否符合 README 约束且不过度扩写

**结论: 符合。**

- `tests/README.md:212` 在 Host P12.6 memory semantic smoke 段落追加了一句维护约定："Conversation Memory snapshot 测试数据应优先通过 `tests/host/memory_snapshot_factories.py` 构造并回填 digest，避免业务测试直接散落 snapshot digest 中间态或重复手写 `ConversationMemorySnapshotVNext(...)`。"
- 这是对既有测试维护约定的最小补充，符合 README 的写作边界（只描述当前事实），不扩写用户手册或设计文档。
- 未触发其它 README 更新条件（无 production `dayu/` 代码修改、无 CLI/Service/Host 行为变化）。

### 7. 是否有违反 AGENTS.md 的类型、docstring、owner boundary、LLM-facing 文本或分层约束

**结论: 无违反。**

- `memory_snapshot_factories.py` 提供完整中文 docstring，参数、返回值、异常齐全。
- `_imported_module_names(...)` 和 `_relative_import_module_name(...)` 提供完整中文 docstring。
- 无 `object`、`Any`、无类型参数或无类型返回值。
- 无 LLM-facing 文本变更（本次只修改测试文件）。
- 无分层约束违反（测试文件不引入生产依赖方向违反）。
- 无兼容性代码。

## Residual Risks

1. **S2 terminal answer continuity 未处理**: S1 未触碰 `dayu/host/_terminal_answer.py`、`dayu/host/durable/memory.py`、`dayu/host/run_input.py` 等 S2 范围。这是 plan 明确的 scope boundary，不是 S1 residual。

2. **`_call_name_lines` scanner 间接包装追踪**: 若未来业务测试引入 `a = some_func(ConversationMemorySnapshotVNext)` 这种间接包装模式，当前 scanner 不会追踪 `a` 的调用。这属于 future change guardrail，当前被扫描文件无此模式。

3. **`test_memory_projection.py` 未纳入 `MEMORY_SNAPSHOT_CONSTRUCTOR_SCAN_FILES`**: 当前 source scan 只覆盖 `test_compact_material.py` 和 `test_run_input_builder.py`。`test_memory_projection.py` 的 `snapshot_digest="pending"` 检测通过 `MEMORY_SNAPSHOT_BUSINESS_TEST_FILES` 覆盖，但直接构造扫描未覆盖。controller validation 确认该文件当前无 pending sentinel 散落；若后续新增直接构造，需扩展 scan scope。

## Validation

已运行并确认通过的命令：

- `source .venv/bin/activate && pytest tests/host/test_import_boundary.py`: 23 passed
- `source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_memory_projection.py`: 203 passed
- `source .venv/bin/activate && pyright`: 0 errors, 0 warnings, 0 informations
- `git diff --check`: passed
- Source scan: `snapshot_digest="pending"` 在 compact/run-input/memory projection 业务测试中无残留；`ConversationMemorySnapshotVNext(` 在 `test_compact_material.py` 和 `test_run_input_builder.py` 中只出现在 type annotation 和 local wrapper signature，不直接构造。
