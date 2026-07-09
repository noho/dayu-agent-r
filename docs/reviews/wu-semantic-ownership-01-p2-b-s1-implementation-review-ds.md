# WU-SEMANTIC-OWNERSHIP-01 P2-B S1 Implementation Review — AgentDS

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub WU: `P2-B`
- Slice: `S1`
- Gate: implementation review
- Accepted plan commit: `823ee002`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-p2-b-s1-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p2-b-s1-implementation-controller-validation.md`

## Verdict

**pass**

无阻塞 finding。

## Review Evidence

### 1. `_relative_import_module_name(...)` 语义正确性

**结论：正确，无阻塞 finding。**

逐项验证：

- **`level > 0` 入口守卫**（`test_import_boundary.py:246-247`）：`level <= 0` 直接 `raise AssertionError`，防止把绝对 import 误传入相对解析路径。

- **文件不在 package root 下**（`:252-256`）：通过 `relative_to(...)` 检测，若 `ValueError` 则 fail loudly。覆盖了 `from ..outside import value` 在 package root 级文件中的越界 case（`test_import_scanner_fails_loudly_for_unresolvable_relative_import` 已验证）。

- **非 `.py` 文件**（`:258-259`）：若 `relative_file.suffix != ".py"` 则 fail。因 `_iter_python_files` 只收集 `.py` 文件，此检查为防御性安全网，不会误杀合法扫描路径。

- **回溯越界**（`:263-266`）：`climb_count > len(relative_package_parts)` 时 fail。包根 `__init__.py` 中 `from .. import x`（`level=2, parent_parts=()`）会触发此分支，正确拒绝。

- **`module is None` 处理**（`:272-273`）：`module is None` 时只返回回溯后的 package prefix，不做拼接。`test_import_scanner_resolves_no_module_relative_import` 已验证 `from . import sibling` → `samplepkg.subpkg`。

- **package prefix 确定性**（`:206-226` `_package_name_from_root`）：从 `package_root` 向上沿 `__init__.py` 链逐级收集 package name parts，拒绝无 `__init__.py` 的目录和非 package 根。

- **package_parts 空列表守卫**（`:274-275`）：在 `module is None` 且 package_parts 意外为空时 fail。此分支在当前合法路径下不可达（`_package_name_from_root` 已保证非空），但作为防御性安全网合理。

**root cause 判定**：相对 import 解析的 owner 是 `_relative_import_module_name`（AST scanner 内），所有边界测试通过 `_imported_module_names` 统一消费，无特判分支。

### 2. 所有 import-boundary 测试消费相对 import 结果

**结论：全覆盖，无旧 scanner call site 残留。**

- `_imported_module_names` 的 `ast.ImportFrom` 分支（`:296-309`）：`level == 0` 走绝对路径，`level > 0` 走相对解析。原有的 `node.level == 0` 条件不再构成漏扫屏障——它现在是绝对 import 分支的条件，不再是唯一过滤条件。

- 16 处 `_imported_module_names` call site（边界测试 + 单元测试）全部通过 `scanned_file` 和 `package_root` 关键字传参，不再依赖旧的两参数签名。

- 回滚验证点通过：
  - `rg -n "snapshot_digest=\"pending\"" tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py` → 无命中。
  - `rg -n "node\.level == 0" tests/host/test_import_boundary.py` → 仅剩 `:297` 一处（绝对 import 分支条件），不再是相对 import 漏扫条件。

- Host 生产代码中若存在 `from .durable import memory` 这类相对 import，现在会被解析为 `dayu.host.durable.memory` 并参与 `HOST_FORBIDDEN_PREFIXES` 匹配，不再被静默跳过。

### 3. `tests/host/memory_snapshot_factories.py` 作为唯一 tests-only snapshot 真源

**结论：形成唯一真源，digest 回填 canonical，placeholder 不泄漏。**

- **digest 回填 canonical**：`recalculate_memory_snapshot_digest`（`:74-87`）使用 `replace(snapshot, snapshot_digest=_DIGEST_PLACEHOLDER)` 后调用生产函数 `calculate_memory_snapshot_digest(...)`。验证确认 `_snapshot_digest_json_value`（`dayu/host/memory.py:2375-2382`）通过 `include_digest=False` 显式排除 `snapshot_digest` 字段，因此 placeholder 值不影响最终 digest 结果。最终 snapshot 的 `snapshot_digest` 是 self-verifying 的——对同一 snapshot 重新计算会得到相同 digest。

- **placeholder 不泄漏**：`_DIGEST_PLACEHOLDER` 是 factory 模块级私有常量（`memory_snapshot_factories.py:37`），仅被 `recalculate_memory_snapshot_digest` 和 `empty_memory_snapshot` / `rich_memory_snapshot` 等 factory 函数内部消费。业务测试通过 `recalculate_memory_snapshot_digest(...)` 回填 digest，不直接引用 placeholder。业务测试体无 `snapshot_digest="pending"` 散落。

- **factory 使用生产 dataclass 与 digest helper**：所有 factory 函数使用 `ConversationMemorySnapshotVNext(...)` 直接构造（factory 是 snapshot 构造的允许位置），并用 `calculate_memory_snapshot_digest` 和 `digest_memory_projection_policy` 等生产函数。没有新增仅供测试的 production hook。

- **compact/run-input 业务测试消费同源 snapshot**：
  - `test_compact_material.py` 的 `_empty_snapshot` → `empty_memory_snapshot(...)`：来自 factory。
  - `test_compact_material.py` 的 `_snapshot_with_fact` → `_empty_snapshot` + `recalculate_memory_snapshot_digest(replace(...))`：扩展 factory 基础 snapshot，digest 回填通过 factory 的 `recalculate_memory_snapshot_digest`。
  - `test_run_input_builder.py` 的 `_rich_memory_snapshot` → `rich_memory_snapshot(...)`：来自 factory。
  - `test_run_input_builder.py` 的 `_current_input_memory_snapshot` → `current_input_memory_snapshot(...)`：来自 factory。
  - `test_run_input_builder.py` 的 `_reference_continuity_only_snapshot` → `reference_continuity_only_snapshot(...)`：来自 factory。

- **`test_memory_projection.py` 状态**：
  - 无 `snapshot_digest="pending"` 散落、无 `ConversationMemorySnapshotVNext(` 直接构造。
  - 使用 `calculate_memory_snapshot_digest`（生产函数）做 digest 正确性断言，这是正当的 digest invariant 测试，属于允许位置。

### 4. AST source scan 覆盖范围与剩余规避方式

**结论：覆盖充分，剩余规避方式均为病理 case，不构成 S1 必修 finding。**

覆盖的构造模式（`_call_name_lines`，`:365-395`）：

| 模式 | 检测机制 | 覆盖 |
|---|---|---|
| `ConversationMemorySnapshotVNext(...)` | `ast.Name` id 匹配 | ✅ |
| `factory.ConversationMemorySnapshotVNext(...)` | `ast.Attribute` attr 匹配 | ✅ |
| `from x import ConversationMemorySnapshotVNext as Alias` + `Alias(...)` | `ast.ImportFrom` alias 收集 | ✅ |
| `Alias = ConversationMemorySnapshotVNext` + `Alias(...)` | `ast.Assign` + `ast.Name` 收集 | ✅ |

覆盖的 pending digest 模式（`_string_keyword_value_lines`，`:337-362`）：
- `snapshot_digest="pending"`、`snapshot_digest='pending'`、`snapshot_digest = "pending"` 等字面变体均通过 `ast.Constant` 值匹配捕获，不依赖源码字面格式。

未覆盖的规避方式：
- `getattr(module, "ConversationMemorySnapshotVNext")(...)`: 需要刻意使用反射，在测试代码中属病理行为。
- `eval("ConversationMemorySnapshotVNext")(...)`: 同上。
- 通过中间变量链式赋值（`A = B = ConversationMemorySnapshotVNext`）：`ast.Assign` 的 `targets` 包含多个 target，当前只检查每个 target 是否为 `ast.Name`，`A = B = ...` 中两个 target 都会是 `ast.Name`，所以实际会被覆盖。

以上未覆盖方式均为刻意规避的病理 case，不构成 S1 必修 finding。若后续发现需要允许专门 digest invariant 测试直接构造 snapshot，应按 controller validation 的建议先收敛到 factory 或明确命名的 digest invariant 测试，再调整 scanner。

### 5. 迁移后测试仍验证原业务语义

**结论：业务语义保留，无误删覆盖或 false confidence。**

- `test_compact_material.py` 中的 snapshot 构造从手写 `ConversationMemorySnapshotVNext(...)` + `snapshot_digest="pending"` + `calculate_memory_snapshot_digest(...)` 迁移为 `empty_memory_snapshot(...)` + `recalculate_memory_snapshot_digest(replace(...))`。snapshot 字段内容（cursor、policy_digest、trace_memory、evidence_fact_memory 等）保留不变，只改变了 digest 回填路径。

- `test_run_input_builder.py` 中的 `_rich_memory_snapshot` 等 helper 从直接构造 `ConversationMemorySnapshotVNext(...)` 迁移为调用 factory 的 `rich_memory_snapshot(...)`。内部字段等价——factory 的 `rich_memory_snapshot` 提供了与迁移前测试相同的 selected recent window、reference continuity、evidence fact、session summary、answer anchor、forward intent 数据。

- 全部 203 个 memory 相关测试均通过，证明业务语义未被破坏。

### 6. README 触发与更新

**结论：适当。**

- `tests/README.md` 变更：在 P12.6 memory semantic smoke 段落末尾追加一句维护约定："Conversation Memory snapshot 测试数据应优先通过 `tests/host/memory_snapshot_factories.py` 构造并回填 digest，避免业务测试直接散落 snapshot digest 中间态或重复手写 `ConversationMemorySnapshotVNext(...)`。"

- 判断依据：本次新增 tests-only shared memory snapshot factory，属于测试维护约定变更。`tests/README.md` 的职责包含描述测试组织方式与维护约定，追加一句维护指引符合其文档职责。无需同步其它 README（无 `dayu/host/` 生产代码变更，无 CLI/Web/WeChat 入口变更，无分层关系变更）。

- `docs/host/issues-implementation-control.md` 变更：`gate` 从 `accepted-plan` 更新为 `review`，`next entry point` 更新为 "P2-B S1 implementation review in progress"。这是 control doc 的状态同步，不属于 README 触发范畴，更新正确。

### 7. AGENTS.md 约束检查

**结论：无违反。**

- **语义所有权与修复边界**：import scanner 修复落在 AST scanner owner（`test_import_boundary.py`），snapshot fixture 集中在 tests-only factory（`memory_snapshot_factories.py`）。未在下游消费者或测试夹具中用特例分支掩盖错误语义。compact/run-input/memory projection 的业务测试消费同源 factory，符合"多个消费者需要同一语义时抽取同一个 source-of-truth"。

- **LLM-facing 文本约束**：本次未修改任何 LLM-facing prompt、tool schema、memory/compact/trace/evidence material 或 Host 投影给 LLM 的文本。不受此约束影响。

- **架构硬约束**：变更全部在 `tests/` 下，无分层违反。`dayu.runtime` 未被修改，无反向依赖。

- **编码硬约束**：
  - 所有新增函数提供完整中文 docstring（参数、返回值、异常）。
  - 所有新增函数有完整类型注解，无 `object`、`Any`、无类型参数。
  - 无 `hasattr`/`getattr` 滥用。
  - 无魔法数字/字符串（`_DIGEST_PLACEHOLDER` 有明确语义，不是魔法值）。
  - 无兼容性代码、兼容性 re-export、兼容性 wrapper。
  - 无 God object/function/dataclass/bag/builder。

- **测试与验证**：新增 import scanner 单元测试覆盖 absolute/same-package relative/parent-package relative/no-module relative/unresolvable 五个 case。新增 AST scanner 单元测试覆盖 `_string_keyword_value_lines` 和 `_call_name_lines`。所有受影响测试通过。

- **S1 未越界触碰 S2 production Host semantic owner**：`dayu/host/` 下无任何文件被修改。未修改 `_terminal_answer.py`、`durable/memory.py`、`run_input.py`、`docs/host/design.md` 或任何 production memory/terminal answer continuity 语义。S2 的 stop condition 未被触发。

## Residual Risks

1. **`_required_memory_cursor` 直接构造 `MemorySnapshotCursor`**（`tests/host/test_run_input_builder.py:3973`）：`_required_memory_cursor` 直接调用 `MemorySnapshotCursor(...)` 而非 factory 的 `memory_snapshot_cursor(...)`。原因合理——该 helper 从数据库读取 cursor 参数，不是从已知值构造。plan 只要求不直接构造 `ConversationMemorySnapshotVNext`，未要求不直接构造 `MemorySnapshotCursor`。低风险，不影响 S1 验收。

2. **S2 cross-path equivalence test 需要 S1 fixture**：S1 的 shared factory 是 S2 的前置依赖。S2 实施时需确保 `test_memory_projection.py` 的 cross-path equivalence test 复用 S1 factory，不重新引入 pending digest 或直接 snapshot 构造。此风险由 S1 source-scan 持续约束（`test_memory_snapshot_business_tests_do_not_scatter_pending_digest` 已覆盖 `test_memory_projection.py`）。

3. **AST source scan 对 `ast.Name` 别名检测依赖赋值语句顺序**：`_call_name_lines` 先收集别名再扫描调用。若别名赋值出现在调用之后（同一模块内），该调用不会被检测到。但此类代码在 Python 中会导致 `NameError`，因此不构成实际风险。

## Validation

实际运行的验证命令及结果：

```bash
# import boundary 测试
source .venv/bin/activate && pytest tests/host/test_import_boundary.py -v
# → 23 passed

# memory 相关业务测试
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compact_material.py tests/host/test_memory_projection.py -v
# → 203 passed

# 类型检查
source .venv/bin/activate && pyright
# → 0 errors, 0 warnings, 0 informations

# diff 格式检查
git diff --check
# → passed

# 回滚验证点
rg -n 'snapshot_digest="pending"' tests/host/test_compact_material.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py
# → No matches

rg -n "ConversationMemorySnapshotVNext\(" tests/host/test_compact_material.py tests/host/test_run_input_builder.py
# → No matches

rg -n "node\.level == 0" tests/host/test_import_boundary.py
# → 仅剩 :297 一处（绝对 import 分支条件，不再是相对 import 漏扫条件）
```

## Propagation Audit (S1 Scope)

1. import-boundary tests 从被扫描源码文件和 package root 产生 import fact → scanner 统一解析 absolute/relative import 为绝对模块名 → Host/Runtime/Engine boundary tests 消费绝对模块名并匹配 forbidden prefix。
2. memory snapshot 测试事实由 `tests/host/memory_snapshot_factories.py` 产生 → factory 使用生产 dataclass + `calculate_memory_snapshot_digest` 生成 canonical digest → compact material / RunInputBuilder 业务测试通过 thin wrapper 消费同源 snapshot。
3. AST source-scan 测试持续约束 compact/run-input/memory projection 不新增 pending digest 散落，并约束 compact/run-input 不绕过 shared factory 直接构造 snapshot。

三条路径语义一致，无 propagation gap。
