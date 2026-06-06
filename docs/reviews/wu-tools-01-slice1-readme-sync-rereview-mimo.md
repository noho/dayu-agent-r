# WU-TOOLS-01 Slice 1 README Sync Re-review

- Work unit: WU-TOOLS-01
- Gate: re-review
- Slice: S1 README sync follow-up
- Reviewer: AgentMiMo
- Review date: 2026-06-05T23:08:19

## Scope

- Mode: current changes (re-review target: `tests/README.md` diff only)
- Base: main
- Target artifact: `docs/reviews/wu-tools-01-slice1-readme-sync-fix-codex.md`
- Included: `tests/README.md` README sync changes for new `tests/documents/` test layer
- Excluded: implementation findings (out of scope per re-review contract)

## Findings

未发现实质性问题。

逐项核对结果：

1. **常用命令更新**（L17, L20）：`Documents` 已加入测试层级列表，`tests/documents` 已加入全量 pytest 命令。与实际目录 `tests/documents/` 存在事实一致。

2. **focused commands 新增**（L39）：`pytest tests/documents -q` 已插入 `tests/contracts` 与 `tests/host` 之间，位置与字母序一致。

3. **测试分层新增 `tests/documents/` 小节**（L122-L127）：
   - README 描述："阻止 `dayu.documents` 反向依赖 Engine、Host、Service、UI、Fins 或具体工具实现"。实际代码 `test_import_boundary.py:14-21` 的 `DOCUMENTS_FORBIDDEN_PREFIXES` 包含 `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`、`dayu.fins`、`dayu.tools`，与 README 描述一致。
   - README 描述："确认 Docling runtime 与 processors 子包被边界扫描覆盖"。实际代码 `test_import_boundary.py:87-103` 的 `test_documents_import_boundary_scan_covers_docling_runtime` 和 `test_documents_import_boundary_scan_covers_processors` 与此一致。
   - README 描述："使用确定性 fixture 覆盖 Markdown、HTML 与 Docling JSON 处理器的章节提取、表格读取与搜索片段输出"。实际代码 `test_processors.py` 包含 `test_markdown_processor_sections_tables_and_search`（章节、表格、搜索）、`test_html_processor_sections_tables_and_search`（章节、表格、搜索）和 `test_docling_json_processor_sections_tables_and_search`（章节、表格、搜索），与 README 描述一致。

4. **职责边界**：README 只描述测试分层、运行命令和维护事实，未包含未来设计、过程历史、review 状态或实现细节。

5. **无生产/测试代码变更**：本次 README sync fix 只修改 `tests/README.md` 和 fix artifact，未触及生产代码或测试代码。

## Validation Commands

- 未运行 `pytest tests/documents -q`：本次变更只修改 README 文档，不改变测试或生产代码行为，与 fix artifact 中声明的验证范围一致。
- 未运行 `pyright`：无代码变更，不引入类型风险。

## Residual Risk

- 无。
