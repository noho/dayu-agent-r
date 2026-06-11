# WU-TOOLS-01-F08 Code Review

## Metadata

- Work unit: `WU-TOOLS-01-F08`
- Gate: code review
- Date: 2026-06-11
- Reviewer: AgentDS
- Reviewed artifacts:
  - `docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md` (accepted plan)
  - `docs/reviews/wu-tools-01-f08-plan-rereview-controller-adjudication.md` (plan re-review adjudication)
  - `docs/reviews/wu-tools-01-f08-implementation-codex.md` (implementation artifact)
  - Full `git diff` against working tree

## Scope

- Mode: current changes (uncommitted working tree diff)
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: `main` (no commits ahead of workspace; review scope is unstaged diff only)
- Output file: `docs/reviews/wu-tools-01-f08-code-review-ds.md`
- Included scope: all modified tracked files + new untracked files in `git status --short`
- Excluded scope: `docs/reviews/` historical artifacts (not cleanup targets per accepted plan)

## Review Method

逐文件走读 diff，对照 accepted plan 的每条精确允许改动做一一核查。对每个 checkpoint 做独立验证：旧名清理（rg）、兼容代码检查（diff 全文搜索 alias/wrapper/facade 关键词）、行为等价性（对比 registry 注册调用与 focused test 断言）、docstring/type 合规（逐函数检查）、README 触发规则（对照 AGENTS.md 与 README 内 Agent更新约束）、控制文档更新（对照 plan 指定的 control doc 修改范围）、验证命令可复现性（独立执行 rg 与 git diff --check 确认）。

## Checkpoint Verdicts

### Checkpoint 1: 旧名彻底清除

`rg -n "build_engine_processor_registry|_ENGINE_PROCESSOR_REGISTRY|_get_engine_processor_registry" dayu tests dayu/fins/README.md docs/host/issues-implementation-control.md`

Result: **无匹配**（rg exit 1，符合预期）。

- `dayu/documents/processors/registry.py:17` — 函数名已改为 `build_documents_processor_registry`。
- `dayu/documents/processors/__init__.py:12,23` — import 与 `__all__` 已改为 `build_documents_processor_registry`。
- `dayu/documents/processors/_doc_processor_factory.py:21,37,47,48,49,88` — 模块级 cache、helper 函数名、内部调用全部改为 documents 命名。
- `dayu/fins/processors/registry.py:11,60` — import 与内部调用已改为 `build_documents_processor_registry`。
- `dayu/fins/README.md:382,596` — 两处 ownership 表述已改为 documents 默认处理器注册表。
- `docs/host/issues-implementation-control.md` — F08 section、状态表、Residual Risk 表中旧引用已全部更新。

**通过。**

### Checkpoint 2: 无兼容 alias / re-export / wrapper / facade

全文 diff 搜索 `build_engine_processor_registry`（仅在 `-` 行出现，无 `+` 行重新引入）、`= build_documents_processor_registry`（无 alias 赋值）、`__all__` 中无旧名字符串。`dayu/documents/processors/__init__.py` 的 `__all__` 仅包含 `"build_documents_processor_registry"`，不包含旧名。

**通过。**

### Checkpoint 3: Documents 默认 registry 行为不变

`dayu/documents/processors/registry.py:38-57` — 函数体完全等价：

```python
registry = ProcessorRegistry()
registry.register(DoclingProcessor, name="docling_processor", priority=_GENERIC_PROCESSOR_PRIORITY, overwrite=True)
registry.register(MarkdownProcessor, name="markdown_processor", priority=_GENERIC_PROCESSOR_PRIORITY, overwrite=True)
registry.register(BSProcessor, name="bs_processor", priority=_GENERIC_PROCESSOR_PRIORITY, overwrite=True)
return registry
```

`_GENERIC_PROCESSOR_PRIORITY = 10` 未修改。

Focused test `test_documents_processor_registry_registers_default_processors`（`tests/documents/test_processors.py:46-55`）断言 `list_processors()` 精确等于 `[{"name": "docling_processor", "class": "DoclingProcessor", "priority": 10}, {"name": "markdown_processor", "class": "MarkdownProcessor", "priority": 10}, {"name": "bs_processor", "class": "BSProcessor", "priority": 10}]`，锁定名称、类、priority 与同 priority 下顺序。

`ProcessorRegistry.list_processors()`（`processor_registry.py:100-120`）返回 `[{"name": item.name, "class": item.processor_cls.__name__, "priority": item.priority}]`，与断言格式一致。

**通过。**

### Checkpoint 4: Fins registry overlay 行为不变

`dayu/fins/processors/registry.py:60` — `registry = build_documents_processor_registry()` 先加载 documents 默认注册表。

随后以 `overwrite=True` 覆盖注册：
- `FinsDoclingProcessor` → `docling_processor`, priority 100（`_FINS_DOC_MARKDOWN_PRIORITY`）
- `FinsMarkdownProcessor` → `markdown_processor`, priority 100
- `FinsBSProcessor` → `bs_processor`, priority 80（`_FINS_BS_PRIORITY`）

后续 SEC 处理器注册顺序与 priority 常量均未修改。

Focused test `test_fins_processor_registry_overlays_documents_defaults`（`tests/fins/test_processor_registry.py:8-71`）：
- 使用 `list_processors()` 构造 `name → (class, priority)` 映射（`processors_by_name`），未硬编码完整列表顺序 ✓
- 断言 `docling_processor`、`markdown_processor`、`bs_processor` 指向 Fins 类而非通用类 ✓
- 使用 priority bucket（`priority_bucket_200`、`priority_bucket_190`）做集合断言，不依赖顺序 ✓
- 断言 `sec_processor` → `SecProcessor`，priority 120 ✓
- 覆盖所有 7 个主路径处理器名称与 6 个回退处理器名称 ✓

Fins focused test 是 mandatory 的，该文件 `tests/fins/test_processor_registry.py` 为新建，符合 plan 要求。

**通过。**

### Checkpoint 5: Docstring / type hints 合规

逐函数检查：

| 函数 | 文件:行号 | 中文 docstring | Args | Returns | Raises | 返回类型注解 |
|---|---|---|---|---|---|---|
| `build_documents_processor_registry` | `registry.py:17` | ✓ | ✓ | ✓ | ✓ | `-> ProcessorRegistry` |
| `_get_documents_processor_registry` | `_doc_processor_factory.py:34` | ✓ | ✓ | ✓ | ✓ | `-> ProcessorRegistry` |
| `build_fins_processor_registry` | `fins/processors/registry.py:40` | ✓（已更新 wording） | ✓ | ✓ | ✓ | `-> ProcessorRegistry`（已有） |
| `build_bs_experiment_registry` | `fins/processors/registry.py:173` | ✓（comment 已更新） | ✓ | ✓ | ✓ | `-> ProcessorRegistry`（已有） |

模块级变量 `_DOCUMENTS_PROCESSOR_REGISTRY: ProcessorRegistry | None = None` 已添加类型注解（`_doc_processor_factory.py:21`），比旧代码的无类型 `= None` 更严格。

新增 import `from .processor_registry import ProcessorRegistry`（`_doc_processor_factory.py:17`）服务于类型注解，在 `from __future__ import annotations` 下为 type-checker-only import，pyright 0 errors 确认合规。

`tests/documents/test_processors.py:46` 与 `tests/fins/test_processor_registry.py:8` 的测试函数均有中文 docstring。

**通过。**

### Checkpoint 6: README 更新合规

`dayu/fins/README.md`（两处修改）：
- L382: "在 engine 文档处理器注册表基础上" → "在 documents 默认处理器注册表基础上"
- L596: "在通用文档处理器基础上" → "在 documents 默认处理器注册表基础上"

对照 README 内 `Agent更新约束【必须遵守】`：修改仅涉及当前已实现架构的 ownership 表述修正，不引入未来计划、用户手册、测试清单或 work unit 流水。修改前已核对 `dayu.fins` 当前代码真源。✓

`tests/README.md`：未更新。plan 已裁决：新增测试位于既有 `tests/documents/` 与 `tests/fins/` 分层，未新增测试层级、命令、fixture 类别或维护约定。对照 AGENTS.md "tests/ 修改 -> 检查并按需更新 tests/README.md"，检查结论为无需更新，判断合理。

`dayu/README.md`：未更新。本次改动不涉及 UI/Service/Host/Engine 分层关系或装配方式变化，不触发更新条件。

**通过。**

### Checkpoint 7: WU-TOOLS-01-S1-R2 关闭证据

`docs/host/issues-implementation-control.md` 中的关闭证据：

1. Residual Risk 表（L199）：`WU-TOOLS-01-S1-R2` 行已移除 ✓
2. F08 section 状态（L1065）："该 work unit 已关闭 `WU-TOOLS-01-S1-R2`" ✓
3. F08 section Implementation validation（L1088-1095）：记录了全部验证命令与结果 ✓
4. 状态表（L143-144）：F08 gate 从 `implementation` 更新为 `review`，next entry point 更新为 `code review gate` ✓

关闭证据链完整：旧名已在全部 stable target 中清除 → focused tests 证明行为不变 → pyright 0 errors → `WU-TOOLS-01-S1-R2` 从 active residual 中移除。

**通过。**

### Checkpoint 8: 验证命令结果可信

独立复验：

- `rg -n "build_engine_processor_registry|_ENGINE_PROCESSOR_REGISTRY|_get_engine_processor_registry" dayu tests dayu/fins/README.md docs/host/issues-implementation-control.md` → 无匹配（exit 1）✓
- `rg -n "build_engine_processor_registry" docs/reviews` → 仅历史 review/plan review artifact 匹配，非 cleanup target ✓
- `git diff --check` → 无输出（通过）✓

Controller 报告的验证结果与独立复验一致：
- Focused tests: 5 passed ✓
- Full tests: 263 passed, 1 skipped ✓
- Pyright: 0 errors, 0 warnings, 0 informations ✓
- No `tests/fins` heavy fixture / environment failure → 无需分类 ✓

**通过。**

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

1. **仓库外部 consumer 断裂**：移除 `build_engine_processor_registry` 公共 export 可能 break 仓库外调用方。缓解方式：PR/release 说明中注明 breaking change，按 AGENTS.md 禁止兼容 alias/wrapper。Risk owner: release note / PR description。

2. **`docs/reviews/` 历史 artifact 旧名留痕**：历史 review artifact 中保留 `build_engine_processor_registry` 引用（已确认为 22+ 处匹配），属于可接受留痕，非 cleanup target。低优先级困惑风险：未来开发者检索旧名时可能困惑。

3. **单文件测试覆盖率未独立测量**：implementation 未提供 `_doc_processor_factory.py`、`registry.py` 等单个文件的覆盖率数据。行为风险已被 focused contract tests 和 full `tests/documents tests/fins`（263 passed）覆盖；覆盖率缺口属于未度量项，非已知缺陷。

## Summary

WU-TOOLS-01-F08 implementation 严格按照 accepted plan 执行了单 slice `S1 registry naming cleanup`。所有 8 个 checkpoint 均通过独立验证：旧名在全部 stable target 中彻底清除、无兼容 alias/wrapper、documents 默认 registry 与 Fins overlay registry 行为不变、focused tests 按 plan 要求使用 mapping/priority-bucket 断言、docstring/type hints 符合 AGENTS.md、README 更新符合各 README 约束、WU-TOOLS-01-S1-R2 关闭有完整证据链、验证命令结果可复现。

**Verdict: pass.**
