# Code Review

## Scope

- Mode: current changes
- Branch: `phaseflow/wu-tools-01`
- Base: `main` (commit `ee2bc693`)
- Output file: `docs/reviews/wu-tools-01-slice1-code-review-mimo.md`
- Included scope: WU-TOOLS-01 Slice S1 implementation — uncommitted workspace changes for `dayu/documents/`, `tests/documents/`, `dayu/README.md`, `tests/engine/contracts/test_import_boundary.py`, `tests/engine/test_import_boundary.py`, and `docs/reviews/wu-tools-01-slice1-implementation-codex.md`
- Excluded scope: Doc/Fins/Web providers, ToolDefinition adapter, Host changes, Engine implementation changes, Fins storage, OLD ToolRegistry, OLD TruncationManager, OLD fetch_more, OLD tool runtime owner
- Parallel review coverage: 无

## Findings

### 01-未修复-低-migrate 函数名 build_engine_processor_registry 仍保留 engine 语义

- **入口/函数**: `dayu/documents/processors/registry.py:17` `build_engine_processor_registry()`
- **文件(行号)**: `dayu/documents/processors/registry.py:17`，docstring 行 18-36
- **输入场景**: 任何调用方导入或调用该函数时
- **实际分支**: 函数名和 docstring 均保留 "engine" 与 "核心层" 术语
- **预期行为**: 迁移到 `dayu.documents` 后，函数名和 docstring 应反映 documents 层语义，而非 engine 层语义
- **实际行为**: 函数名 `build_engine_processor_registry` 暗示该注册表属于 engine 层；docstring 中"仅负责构建'核心层可用'的处理器注册表"使用 engine 内部术语"核心层"
- **直接证据**: `registry.py:17` 函数名；`registry.py:18` docstring "本模块仅负责构建"核心层可用"的处理器注册表"；OLD 源 `dayu/engine/processors/registry.py` 对比 diff 确认仅改了模块级 docstring 两行，函数名未改
- **影响**: 代码阅读者会误认为该注册表属于 engine 层或仅服务于 engine；上层（Doc tools、Fins）调用时语义不清晰
- **建议改法和验证点**: 将函数名改为 `build_documents_processor_registry`（或 `build_default_processor_registry`），更新 docstring 去掉"核心层"；grep 确认所有调用方同步更新
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-测试仅覆盖 happy-path fixture

- **入口/函数**: `tests/documents/test_processors.py` 全文件
- **文件(行号)**: `tests/documents/test_processors.py:45-220`
- **输入场景**: 运行 `pytest tests/documents/test_processors.py`
- **实际分支**: 3 个测试各覆盖一种处理器的基础 happy path（章节列表、表格读取、搜索命中）
- **预期行为**: 共享文档基础包的测试应覆盖边界条件和失败路径，包括空文档、无标题文档、搜索无命中、malformed JSON、超大表格等
- **实际行为**: 每个处理器仅有一个 happy-path 测试；无空文档、无标题、搜索无命中、malformed 输入、表格为空等边界测试
- **直接证据**: `test_processors.py` 全文仅 3 个 test function，每个构造最小 fixture 并断言基础输出
- **影响**: 后续修改处理器逻辑时缺少回归保护；边界条件行为（如空文档返回单 section、无标题文档 fallback）未被验证
- **建议改法和验证点**: 为每个处理器补充至少：空文档、无标题/无 heading、搜索无命中、表格为空的测试用例
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- `_doc_processor_factory.py` 已复制到 `dayu/documents/processors/` 但未在 `processors/__init__.py` 的 `__all__` 中导出。它是 Doc tools 的内部工厂，当前无调用方。后续 Slice 引入 Doc tools 时需确认是否仍需要该文件以及是否应暴露。
- Docling PDF 转换运行时已迁移且 import/type 检查通过，但 S1 测试有意不执行真实 PDF/OCR 转换。后续 Doc/Fins/Web 转换路径的集成测试将覆盖此区域。
- 测试覆盖代表性 Markdown、HTML 和 Docling JSON fixture，不覆盖完整 OLD parity corpus。后续 provider/tool 迁移 Slice 和更广泛回归套件将覆盖。

## Validation Commands

```bash
# 测试
source .venv/bin/activate && pytest tests/documents tests/engine/contracts/test_import_boundary.py tests/engine/test_import_boundary.py -v
# 结果: 11 passed

# pyright
source .venv/bin/activate && python -m pyright dayu/documents/
# 结果: 0 errors, 0 warnings, 0 informations
```

## Migration Principle Compliance (Direct Evidence)

- `base.py`: OLD vs NEW diff 仅一处尾部空行差异，函数签名和业务逻辑体完全保留
- `source.py`: OLD vs NEW diff 仅 docstring 从"engine 核心层"改为"documents 处理器层"
- `docling_runtime.py`: OLD vs NEW diff 仅 `from dayu.log import Log` → `import logging` + `_LOGGER`，`Log.debug/warn` → `_LOGGER.debug/warning`，移除 `module=_MODULE` 参数；函数签名和业务逻辑体完全保留
- `registry.py`: OLD vs NEW diff 仅模块级 docstring 两行从"engine 核心层"改为"documents 处理器层"
- `perf_utils.py`: OLD vs NEW diff 仅 `from dayu.contracts.env_keys` → 模块级常量，`from dayu.log import Log` → `import logging`，`Log.info()` → `_LOGGER.info()`
- 无 compatibility re-export under `dayu.engine`：grep 确认 `dayu/engine/` 下无 `dayu.documents` 引用
- 无 top-level `dayu.log` compatibility module：`dayu/log.py` 和 `dayu/log/__init__.py` 均不存在
- Engine import boundary 测试已收紧：`dayu.documents` 已加入 `ENGINE_CONTRACTS_FORBIDDEN_PREFIXES` 和 `ENGINE_CORE_FORBIDDEN_PREFIXES`

## Verdict

**pass-with-findings**

Implementation can proceed to fix gate or accepted slice commit. Findings are low-severity maintainability issues that do not block S1 acceptance. The `build_engine_processor_registry` naming issue should be addressed in a follow-up cleanup or as part of the next slice that consumes this function.
