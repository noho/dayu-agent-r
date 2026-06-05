# Code Review — WU-TOOLS-01 S1 README Sync Re-Review

## Scope

- Mode: current changes (README sync follow-up only)
- Branch: phaseflow/wu-tools-01
- Base: main
- Output file: docs/reviews/wu-tools-01-slice1-readme-sync-rereview-ds.md
- Included scope: `tests/README.md` diff 中与 `tests/documents/` 相关的三处变更
- Excluded scope: 所有生产代码、测试代码、其他 README、S1 实现 findings（本轮不重新打开）
- Fix artifact: docs/reviews/wu-tools-01-slice1-readme-sync-fix-codex.md
- Parallel review coverage: 无

## 变更概要

`tests/README.md` 三处修改：

1. **常用全量测试命令** (line 17)：在 `tests/contracts` 之后插入 `tests/documents`。
2. **Focused commands** (line 39)：在 `pytest tests/contracts -q` 之后新增 `pytest tests/documents -q`。
3. **当前测试分层** (lines 122-127)：在 `tests/contracts/` 与 `tests/host/` 之间新增 `### tests/documents/` 小节。

## 事实核对

### 测试命令位置

| 检查项 | 结果 |
|--------|------|
| 全量命令中 `tests/documents` 位于 `tests/contracts` 与 `tests/host` 之间 | 通过 |
| Focused command `pytest tests/documents -q` 位于 `pytest tests/contracts -q` 之后 | 通过 |

### tests/documents/ 测试层描述

| README 声明 | 实际代码证据 | 结果 |
|-------------|-------------|------|
| import boundary 阻止反向依赖 Engine/Host/Service/UI/Fins 或具体工具实现 | `test_import_boundary.py:14-21` — `DOCUMENTS_FORBIDDEN_PREFIXES` 包含 `dayu.engine`, `dayu.host`, `dayu.service`, `dayu.ui`, `dayu.fins`, `dayu.tools` | 一致 |
| 确认 Docling runtime 被边界扫描覆盖 | `test_import_boundary.py:87-91` — `test_documents_import_boundary_scan_covers_docling_runtime` 断言 `docling_runtime.py` 在扫描范围内 | 一致 |
| 确认 processors 子包被边界扫描覆盖 | `test_import_boundary.py:94-103` — `test_documents_import_boundary_scan_covers_processors` 断言三个 processor 文件在扫描范围内 | 一致 |
| 使用确定性 fixture 覆盖 Markdown 处理器章节提取、表格读取与搜索片段 | `test_processors.py:45-88` — `test_markdown_processor_sections_tables_and_search` 使用 `tmp_path` fixture，覆盖 `list_sections`, `list_tables`, `read_section`, `read_table`, `search` | 一致 |
| 覆盖 HTML 处理器 | `test_processors.py:91-127` — `test_html_processor_sections_tables_and_search` | 一致 |
| 覆盖 Docling JSON 处理器 | `test_processors.py:130-220` — `test_docling_json_processor_sections_tables_and_search` | 一致 |

### 职责边界检查

| 检查项 | 结果 |
|--------|------|
| 内容属于测试分层、运行命令或维护事实（tests/README.md 固定职责） | 通过 |
| 不包含未来设计、过程历史、review 状态 | 通过 |
| 不包含实现细节或生产代码术语 | 通过 |
| 不写"近期更新""版本记录"等时间敏感内容 | 通过 |
| 无旧术语、旧路径残留 | 通过 |
| 小节按字母序插入（contracts → documents → host） | 通过 |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- 未运行 `pytest tests/documents -q` 验证测试可通过。本轮仅修改 README 与 fix artifact，不改变测试或生产代码行为，此风险为已知且可接受。
- 未运行 `pyright` 验证类型检查。README 变更不涉及代码，无类型风险。
- `dayu/documents/` 目录本身是否存在及其内容未在本轮 scope 内验证；README 描述以 `tests/documents/` 测试文件为真源，测试文件已逐项核对。

## 裁决

**pass** — `tests/README.md` 的 README sync 变更在职责范围内、事实准确、无越界内容。
