# Code Review — WU-TOOLS-01 Slice S1

## Scope

- Mode: current changes (workspace uncommitted)
- Branch: `phaseflow/wu-tools-01`
- Base: `main` (current workspace diff only; commits ahead of main are plan-acceptance commits, not implementation)
- Output file: `docs/reviews/wu-tools-01-slice1-code-review-ds.md`
- Included scope:
  - `dayu/documents/` (new shared document processing package, 18 `.py` files)
  - `tests/documents/` (import boundary + processor fixture tests, 2 test files)
  - `tests/engine/contracts/test_import_boundary.py` (added `dayu.documents` to forbidden prefixes)
  - `tests/engine/test_import_boundary.py` (added `dayu.documents` to forbidden prefixes)
  - `dayu/README.md` (added `dayu.documents` section)
- Excluded scope:
  - `docs/reviews/wu-tools-01-slice1-implementation-codex.md` (implementation report, treated as reference)
  - `docs/host/wu-tools-01-migration-plan.md` (plan, treated as reference)
  - `docs/host/issues-implementation-control.md` (control doc, not fully read due to size)
  - Committed changes on this branch (plan-acceptance commits only)
  - `__pycache__/` directories
- Parallel review coverage: 无（单 reviewer 全量走读）

## Review Method Summary

沿以下路径逐条走读了 `dayu.documents` 的完整入口链：

1. `dayu/documents/__init__.py` → `processors/__init__.py` 公共导出
2. `processors/source.py` → `Source` 协议定义
3. `processors/base.py` → `DocumentProcessor` / `PageAwareProcessor` 协议 + TypedDict 类型
4. `processors/processor_registry.py` → `ProcessorRegistry` 注册/查找/创建链路
5. `processors/registry.py` → `build_engine_processor_registry()` 默认注册
6. `processors/_doc_processor_factory.py` → `LocalFileSource` → `ProcessorRegistry` 工厂
7. `processors/markdown_processor.py` → `MarkdownProcessor` 完整实现（875 行）
8. `processors/bs_processor.py` → `BSProcessor` 完整实现（2008 行）
9. `processors/docling_processor.py` → `DoclingProcessor` 完整实现（1795 行）
10. `docling_runtime.py` → Docling 运行时装配与回退链（667 行）
11. `processors/html_extraction.py` / `html_normalization.py` / `html_markdown.py` / `html_pipeline.py` → HTML 四段流水线
12. `processors/text_utils.py` / `search_utils.py` / `table_utils.py` / `perf_utils.py` → 共享工具模块
13. `tests/documents/test_import_boundary.py` → import 边界 AST 测试（3 tests）
14. `tests/documents/test_processors.py` → 处理器 fixture 测试（3 tests）

对每条链路做了入参 → 条件判断 → 下游调用 → 返回值/副作用 展开。对 `ProcessorRegistry.resolve_candidates` 的分支覆盖、`_plan_conversion_attempts` 的平台回退策略、`_build_sections` 的 heading/非 heading 分叉、以及 `_render_section_text` / `get_full_text_with_table_markers` 的 DOM 副作用与恢复做了重点审查。

## Findings

### F1-未修复-中-测试覆盖率显著不足

- **入口/函数**: 多个公开导出的模块和核心 runtime 模块未被测试覆盖
- **文件(行号)**:
  - `dayu/documents/docling_runtime.py` — 151 语句 / 0% 覆盖
  - `dayu/documents/processors/html_extraction.py` — 191 语句 / 23% 覆盖
  - `dayu/documents/processors/html_normalization.py` — 79 语句 / 24% 覆盖
  - `dayu/documents/processors/html_markdown.py` — 39 语句 / 26% 覆盖
  - `dayu/documents/processors/html_pipeline.py` — 59 语句 / 36% 覆盖
  - `dayu/documents/processors/_doc_processor_factory.py` — 25 语句 / 0% 覆盖
  - `dayu/documents/processors/processor_registry.py` — 68 语句 / 29% 覆盖
- **输入场景**: 任何依赖 `DoclingProcessor.docling_runtime` 模块、HTML 四段流水线、`ProcessorRegistry.create_with_fallback` 或 `_doc_processor_factory` 的调用方
- **实际分支**: S1 fixture 测试仅覆盖 MarkdownProcessor、BSProcessor、DoclingProcessor 的 happy-path（章节、表格、搜索），未触及 HTML 流水线模块、ProcessorRegistry 回退路径、Docling runtime 设备策略分支
- **预期行为**: 公开导出的模块应有基础确定性测试覆盖关键路径
- **实际行为**: 覆盖率为 56%，多个公开模块完全未测试
- **直接证据**: `pytest --cov=dayu/documents --cov-report=term`（见 review method 中覆盖率报告）
- **影响**: 后续 S3/S4/S5 若依赖这些未覆盖模块，会在集成阶段才发现回归；HTML 流水线在 S5 Web 工具迁移前无回归保护
- **建议改法和验证点**:
  - `docling_runtime.py` 的 0% 覆盖可接受——计划明确允许 S1 不做真实 PDF/OCR 转换测试，Docling 依赖在 CI 环境可能不可用
  - `html_extraction` / `html_normalization` / `html_markdown` / `html_pipeline` 在 S1 作为"可复用原语"被导入但未测试——建议在 S5 (Web 工具) 或更早添加确定性 HTML fixture 测试
  - `processor_registry.py` 的 `create_with_fallback`、`unregister` 路径未覆盖——建议在 S2 (adapter) 或后续 slice 补充
  - `_doc_processor_factory.py` 在 S1 无直接消费方——测试可在 S3 (Doc tools) 补
- **修复风险（低）**: 添加确定性 fixture 测试不改变生产代码
- **严重程度（中）**: migration 阶段可接受，但需要在后续 slice 关闭；如果在 S6 集成前仍未覆盖，升级为高

### F2-未修复-低-`PageAwareProcessor` 不在 `__all__` 中

- **入口/函数**: `dayu.documents.processors.__init__` 的公开导出
- **文件(行号)**: `dayu/documents/processors/__init__.py:6`（import），`__all__` (行 18-40) 中缺失
- **输入场景**: 调用方使用 `from dayu.documents.processors import PageAwareProcessor`
- **实际分支**: 显式 import 正常（`from .base import PageAwareProcessor`），但 `from dayu.documents.processors import *` 不会导出 `PageAwareProcessor`
- **预期行为**: `__all__` 应包含所有公开导出的符号
- **实际行为**: `PageAwareProcessor` 被 import 但不在 `__all__` 中，导致 `import *` 语义不完整
- **直接证据**: `processors/__init__.py:6` 有 `from .base import DocumentProcessor, PageAwareProcessor`；`__all__` (行 18-40) 包含 `DocumentProcessor` 但不含 `PageAwareProcessor`
- **影响**: 仅影响 `import *` 用户（pyright/strict mode 下不推荐）；不影响显式 import
- **建议改法和验证点**: 在 `__all__` 中添加 `"PageAwareProcessor"`
- **修复风险（低）**: 单行修改，不影响任何现有调用
- **严重程度（低）**: 公共 API 不一致，但不阻塞功能

### F3-未修复-低-`build_engine_processor_registry` 命名含 OLD "engine" 前缀

- **入口/函数**: `dayu.documents.processors.registry.build_engine_processor_registry()`
- **文件(行号)**: `dayu/documents/processors/registry.py:17`
- **输入场景**: 调用方通过 `from dayu.documents.processors import build_engine_processor_registry` 使用
- **实际分支**: 函数名保留 OLD `engine` 前缀，但实际位置已在 `dayu.documents.processors`
- **预期行为**: 函数名应反映当前位置（如 `build_documents_processor_registry` 或 `build_default_processor_registry`）
- **实际行为**: 函数名误导性地暗示与 Engine 层有关联
- **直接证据**: `dayu/documents/processors/registry.py:17` 函数定义，`processors/__init__.py:23` 公开导出
- **影响**: 可能误导开发者认为该函数归属 Engine 层或需要 Engine 上下文；实际只是一个 documents 层默认注册构建器
- **建议改法和验证点**: 重命名为 `build_documents_processor_registry` 或 `build_default_processor_registry`，同步更新 `processors/__init__.py` 和 `_doc_processor_factory.py` 的引用。实施报告将此列为已知 residual risk，指定由后续 work unit 或 review decision 处理
- **修复风险（低）**: 纯重命名，无行为变更
- **严重程度（低）**: 命名误导但不影响功能正确性

### F4-未修复-低-`search_utils.py` `TypeVar` import 位置偏离常用惯例

- **入口/函数**: 模块级 import
- **文件(行号)**: `dayu/documents/processors/search_utils.py:13`
- **输入场景**: 静态分析工具检查
- **实际分支**: `TypeVar` 仅在行 712 使用（`_TitledSectionT`），但被放在模块顶层的 `from typing import ...` 中
- **预期行为**: 与技术无关，TypeVar 在 typing import 中包含是合理的
- **实际行为**: 与 `base.py`/`bs_processor.py`/`docling_processor.py` 对 `TypeVar` 的使用模式一致（模块顶层 import）
- **直接证据**: `TypeVar` 在 `search_utils.py:712` 处被使用
- **影响**: 无
- **建议改法和验证点**: 无需修改
- **修复风险（低）**: N/A
- **严重程度（低）**: 此 finding 仅为记录 import 审计结果，非实际缺陷

## Constraint Compliance Verdict

逐条对照 key constraints 的审查结果：

| 约束 | 合规 | 证据 |
|-------|---------|----------|
| S1 未实现 Doc/Fins/Web providers | ✅ | `grep -rn "provider\|discover_tools" dayu/documents/` 无匹配 |
| S1 未实现 ToolDefinition adapter | ✅ | 无 `ToolDefinition`, `ToolCallable`, `ToolCallRequest` import |
| S1 未实现 Host changes | ✅ | workspace diff 仅触及 `dayu/README.md` 和测试文件 |
| S1 未实现 Engine implementation changes | ✅ | 无 Engine `.py` 文件修改（仅测试边界文件） |
| S1 未实现 Fins storage | ✅ | 无 `dayu/fins/` 目录 |
| S1 未实现 OLD ToolRegistry | ✅ | 无 `ToolRegistry`, `register_allowed_paths`, `file_path_params` |
| S1 未实现 OLD TruncationManager | ✅ | 无 truncation manager import |
| S1 未实现 OLD fetch_more | ✅ | 无 `fetch_more` 字符串或函数 |
| `dayu.documents` 不 import Host/Engine/Service/UI/Fins/tools | ✅ | `test_documents_do_not_import_forbidden_layers` 通过；grep 无匹配 |
| Engine 和 Engine contracts 不 import `dayu.documents` | ✅ | Engine 边界测试通过；grep `dayu/documents` 在 `dayu/engine/` 无匹配 |
| 复制的 OLD processor 签名和函数体保留 | ✅ | 实施报告确认仅改 import/package/logging 引用 |
| 无 `dayu.engine` 下的兼容性 re-export | ✅ | 未创建 `dayu/engine/processors/` 重导出 |
| 无顶层 `dayu.log` 兼容模块 | ✅ | grep `dayu.log` 在 `dayu/documents/` 无匹配 |

## Validation Commands Run

| 命令 | 结果 |
|-------|--------|
| `pytest tests/documents/ tests/engine/contracts/test_import_boundary.py tests/engine/test_import_boundary.py -v` | 11 passed |
| `pytest --cov=dayu/documents --cov-report=term` (同上范围) | 56% 覆盖率 |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `grep -rn "dayu\.engine\|dayu\.host\|dayu\.service\|dayu\.ui\|dayu\.fins\|dayu\.tools" dayu/documents/ --include='*.py'` | 无匹配（干净） |
| `grep -rn "dayu\.documents" dayu/engine/ --include='*.py'` | 无匹配（干净） |
| `grep -rn "dayu\.documents" dayu/engine/contracts/ --include='*.py'` | 无匹配（干净） |
| `grep -rn "dayu\.log" dayu/documents/ --include='*.py'` | 无匹配（无 OLD log 依赖） |
| `grep -rn "register_allowed_paths\|file_path_params" dayu/documents/ --include='*.py'` | 无匹配（无 path safety logic） |

## Open Questions

- 无。

## Residual Risk

1. **Docling runtime 0% 覆盖**: `docling_runtime.py` 的 `run_docling_pdf_conversion` 回退链（backend × device 二维尝试）仅在真实 Docling 环境下可验证。S1 有意不做真实 PDF 转换测试，该路径的行为正确性依赖后续 S3/S4/S5 的集成测试或手动验证。风险等级：低——Docling runtime 代码是从 OLD 工作副本直接迁移的，OLD 中已验证；迁移只改了 logging import。

2. **HTML 流水线模块未验证**: `html_extraction` / `html_normalization` / `html_markdown` / `html_pipeline` 在 S1 中作为公开 API 导出但无任何测试。这些模块将在 S5（Web 工具）被真实消费。如果在 S5 之前这些模块被意外修改，无回归测试保护。风险等级：低——这些模块在当前分支上无消费方。

3. **`_doc_processor_factory.py` 0% 覆盖**: 该工厂模块使用模块级单例 `_ENGINE_PROCESSOR_REGISTRY`（mutable global），在 S3（Doc 工具）之前无测试。若 S3 实现时发现工厂行为与预期不符，需要回退修改 S1 代码。风险等级：低——S1 交付的是文件布局和 import 边界，不是最终行为契约。

4. **`base.py` 中的 TypedDict 类型未导出**: `SectionSummary`、`TableSummary` 等 TypedDict 类型仅在 `base.py` 中定义，不通过 `processors/__init__.py` 导出。调用方需直接从 `dayu.documents.processors.base` import。这可能在后续 slice 中造成 import 路径不一致。风险等级：低——可在后续 slice 按需添加导出。

5. **`perf_utils.py` 中 `FINS_PROCESSOR_PROFILE` 环境变量名**: 性能打点环境变量保留了 OLD `FINS` 前缀，但模块现在位于共享 `dayu.documents` 包。实施报告将此记录为 intentional——避免为单个环境变量名添加跨契约依赖。风险等级：低——纯命名问题，不影响功能。

## Verdict

**pass-with-findings**

S1 实施严格遵循了迁移计划的约束边界。核心 deliverable——`dayu.documents` 作为共享文档处理基础包——正确建立了 import 边界（不依赖 Host/Engine/Service/UI/Fins/tools），Engine 侧也正确添加了反向隔离。处理器签名和函数体按迁移原则保留，无兼容性 re-export 或 OLD `dayu.log` 模块。所有测试通过，pyright 零报错。

四个 findings 中无一为 correctness 或 architecture 级别的阻断问题。F1（覆盖率不足）是 S1 有意为之的范围决策，剩余覆盖缺口有明确的后续 slice owner。F2/F3 是低严重度的公共 API 命名不一致问题。

**可以推进到 fix gate 或 accepted slice commit**。建议在 fix gate 中修复 F2（`PageAwareProcessor` 加入 `__all__`），F3（`build_engine_processor_registry` 重命名）可推迟到后续 slice 或接受为已知 residual。
