# WU-TOOLS-01-F08 Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-tools-r3-f08`
- Base: `main`
- Output file: `docs/reviews/wu-tools-01-f08-code-review-mimo.md`
- Timestamp: 20260611-105534
- Included scope:
  - `dayu/documents/processors/registry.py`
  - `dayu/documents/processors/__init__.py`
  - `dayu/documents/processors/_doc_processor_factory.py`
  - `dayu/fins/processors/registry.py`
  - `tests/documents/test_processors.py`
  - `tests/fins/test_processor_registry.py`
  - `dayu/fins/README.md`
  - `docs/host/issues-implementation-control.md`
- Excluded scope:
  - `docs/reviews/` 历史 artifact（按 plan 允许保留旧名留痕）
  - `docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md`（plan 文档，描述问题时需引用旧名）
  - `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md`（已完成 WU 的历史 plan artifact）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### Checkpoint 1: 旧名清除

`rg "build_engine_processor_registry|_ENGINE_PROCESSOR_REGISTRY|_get_engine_processor_registry" dayu tests dayu/fins/README.md docs/host/issues-implementation-control.md` 返回 exit 1（无匹配）。旧名在生产代码、测试、稳定 README 和总控文档中已彻底清除。`docs/reviews/` 和 `docs/host/` 下的历史 plan / review artifact 保留旧名属计划内留痕。

### Checkpoint 2: 无旧名兼容 re-export / wrapper / facade

`dayu/documents/processors/__init__.py:12` 仅导出 `build_documents_processor_registry`，无旧名转发。`dayu/documents/processors/registry.py` 未保留旧名别名。符合 AGENTS.md 禁止兼容性代码约束。

### Checkpoint 3: documents default registry behavior 不变

- `registry.py:17-57` 函数体语义等价：`ProcessorRegistry()` + 三个 `register(overwrite=True)` 调用，priority 均为 `_GENERIC_PROCESSOR_PRIORITY = 10`，顺序为 Docling → Markdown → BS。
- `test_documents_processor_registry_registers_default_processors` 断言 `list_processors()` 精确等于 `[{"name":"docling_processor","class":"DoclingProcessor","priority":10}, ...]`，锁定名称、类、优先级和顺序。

### Checkpoint 4: Fins registry overlay contract

- `fins/processors/registry.py:60` 调用 `build_documents_processor_registry()` 作为基础。
- 随后以 `overwrite=True` 覆盖共享名称，FinsDoclingProcessor / FinsMarkdownProcessor priority 100，FinsBSProcessor priority 80。
- SEC 表单处理器 priority 200（主路径）/ 190（回退）/ 120（通用兜底）。
- `test_fins_processor_registry_overlays_documents_defaults` 使用 `name → (class, priority)` 映射断言覆盖行为和 priority bucket，未硬编码完整列表顺序。同时断言共享名称不再指向通用类。

### Checkpoint 5: docstring / type hints

- `_DOCUMENTS_PROCESSOR_REGISTRY: ProcessorRegistry | None = None` 有严格类型注解。
- `_get_documents_processor_registry() -> ProcessorRegistry` 有返回值类型。
- `_get_documents_processor_registry` docstring 为中文，包含 Args / Returns / Raises。
- `build_documents_processor_registry` docstring 为中文，包含 Args / Returns / Raises。
- 所有被改函数均有完整中文 docstring。

### Checkpoint 6: README 更新

- `dayu/fins/README.md:382` 和 `dayu/fins/README.md:596` 从 "engine 文档处理器注册表基础上" 改为 "documents 默认处理器注册表基础上"，符合 README 触发规则和 `dayu/fins/README.md` 的 Agent 更新约束。
- `tests/README.md` 未修改，正确：新测试位于既有 `tests/documents/` 和 `tests/fins/` 分层，未引入新层级或约定。

### Checkpoint 7: WU-TOOLS-01-S1-R2 关闭

`docs/host/issues-implementation-control.md` 中：
- Residual Risk 表已移除 `WU-TOOLS-01-S1-R2` 行（原 line 199）。
- F08 section 明确记录 "已关闭 `WU-TOOLS-01-S1-R2`"。
- F08 工作单元状态从 `implementation` 更新为 `review`。
- 实现验证结果记录在 `Implementation validation` 小节。

### Checkpoint 8: 验证命令结果

独立复验结果与 implementation artifact 声称一致：

| 命令 | 结果 |
|---|---|
| 旧名清理 `rg` | exit 1，无匹配 |
| 历史 artifact `rg` | 仅历史 review artifact 保留旧名 |
| `pytest tests/documents/test_processors.py tests/fins/test_processor_registry.py -q` | 5 passed, 3 warnings |
| `git diff --check` | passed |

注：`pyright` 和 `pytest tests/documents tests/fins` 全量验证未在本次 review 中独立复跑，implementation artifact 声称 0 errors / 263 passed 1 skipped。warnings 为 edgartools 依赖的 deprecation warnings，与本次 rename 无关。

## Open Questions

无。

## Residual Risk

- `docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md` 中仍引用旧名，但作为 plan 文档描述问题的上下文是正确的。
- `docs/host/wu-tools-01-f01-02-r3-retire-legacy-adapter-plan.md` 中仍引用旧名，属已完成 WU 的历史 artifact，不在本 WU 清理范围。
- 移除旧 public export 可能影响仓库外调用方，按 AGENTS.md 禁止兼容 re-export 的规则，由 PR / release 说明缓解。

## Summary

WU-TOOLS-01-F08 implementation 严格遵循 accepted plan，执行了 documents processor registry builder 的命名清理。旧名在生产代码、测试、稳定文档和总控中已彻底清除，无兼容性 wrapper / alias / re-export。documents 默认 registry 和 Fins registry overlay 行为保持不变，有 focused contract tests 覆盖。docstring / type hints 符合 AGENTS.md。README 和总控按触发规则正确更新。`WU-TOOLS-01-S1-R2` 已关闭并记录依据。Verdict: pass。
