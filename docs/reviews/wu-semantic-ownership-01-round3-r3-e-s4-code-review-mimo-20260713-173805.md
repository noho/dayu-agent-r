# R3-E Slice S4 Code Review（AgentMiMo）

## Scope

- Mode: current changes (S4 diff only)
- Branch: `phaseflow/host-issues-control`
- Base: uncommitted S4 diff
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s4-code-review-mimo-20260713-173805.md`
- Included scope:
  - `dayu/documents/processors/bounded_source.py`（新增）
  - `dayu/documents/processors/_doc_processor_factory.py`（Source 接入）
  - `dayu/tools/doc_tools.py`（producer caps、partial fields）
  - `tests/documents/test_processors.py`
  - `tests/documents/test_import_boundary.py`
  - `tests/tools/test_doc_tools_provider.py`
  - S4 artifacts
- Excluded scope: Fins、tool-security、file-authority、symlink-race、S5/aggregate/control bookkeeping
- Parallel review coverage: 3 个 subagent（BoundedSourceSnapshot 实现、doc_tools producer caps、processor factory 与 boundaries）

## Findings

未发现实质性问题。

以下三项为测试覆盖建议，不构成阻塞性 findings：

1. `DocResourceBudget` 的 `__post_init__` 拒绝 `value <= 0`，测试覆盖了 `0`、`True`、`False`，但未显式覆盖负数（如 `-1`）。实现逻辑正确，补充参数化用例可增强回归保护。
2. `search_files` 中 `source_limit` 与 `result_limit` 存在赋值交叠：若先有文件超预算（设 `source_limit`），后累计 match 达上限（设 `result_limit`），则 `source_limit` 被覆盖。但 `skipped_oversized_files` 计数仍保留此信息，且 `result_limit` 是更可操作的原因。
3. `read_file` 中 `start_line > total_lines` 时 `line_range` 的 end < start，语义不太直觉但功能正确（content 为空）。无测试覆盖此边界。

## Verified Patterns

以下审查点经 3 个 subagent 并行验证确认安全：

**BoundedSourceSnapshot（7 项）：**
1. 只依赖 `Source.open()` 同流 chunk copy，不调用 `read()`/`readlines()` ✅
2. `limit+1` byte 抛出 typed `SourceBudgetExceeded` ✅
3. 正常/异常/取消/resource failure cleanup 均成立 ✅
4. materialize temp 有界且只在系统 `TMPDIR`，无 workspace durable temp ✅
5. `content_length` 早拒绝为纯可选优化，实读流仍是最终裁决 ✅
6. `SpooledTemporaryFile(max_size)` 使用 `min(max_bytes, 1MB)` 防止大文件内存峰值，合理设计 ✅
7. 只依赖标准库 + 本地 `Source` protocol ✅

**doc_tools producer caps（9 项）：**
8. `DocResourceBudget` frozen、拒绝 bool/零/负数、只在 `build_doc_tool_definitions` 创建 ✅
9. `read_file` raw reader 使用 incremental decoder，单行超长最多累积 `max_chars+1` ✅
10. `scan_complete`/`total_lines` 语义正确：完整扫描精确整数，cap 命中时 `null` ✅
11. `list_files` directory iterator cap + 固定大小 heap 排序 ✅
12. `list_files` 的 `total`/`scan_complete`/`truncated_reason` 正确 ✅
13. `search_files` 三维计数（directory entries / Source bytes / matches）✅
14. `truncated_reason` 封闭为 `result_limit`/`directory_entry_limit`/`source_limit`/`null` ✅
15. LLM-facing descriptions 自解释，未暴露内部实现术语 ✅
16. Tests 断言 owner contract，未用旧 fixture 固化偶然行为 ✅

**Processor factory & boundaries（6 项）：**
17. `create_doc_file_processor` 改为接收 `Source`，不再重开未治理路径 ✅
18. Factory 无 compatibility wrapper/re-export ✅
19. Processor constructors 不重开原路径 ✅
20. import boundary 测试覆盖 `bounded_source.py` ✅
21. 禁止 dayu.tools/Host/Engine/Service/UI/Fins 依赖 ✅
22. 无新增 `Any`、`object`、`getattr`、`hasattr`、`type: ignore` ✅

## Scope & Boundary Confirmation

- `git diff --name-only` 只包含 S4 允许的 6 个生产/测试文件 + S4 artifacts。
- 无 Fins（`dayu/fins/`）修改或 Fins processor public contract/shim。
- 无 tool-security、file-authority、symlink-race、SSRF/TLS policy 实现。
- 无 S5、aggregate、control bookkeeping。
- `search_utils.py` 的 `extract_query_anchored_snippets` 从 `doc_tools.py` 移除后，该模块仍被 processors 内部使用，无遗留死代码。

## Open Questions

无。

## Residual Risk

沿用 S4 implementation artifact 已记录的 accepted residual risks，无新增：

| 分类 | residual | owner / destination |
| --- | --- | --- |
| accepted operational limitation | SIGKILL/主机崩溃可能留下至多 `max_source_bytes` 的系统命名 temp。 | `dayu.documents.processors.bounded_source`；依赖系统 temp lifecycle。 |
| accepted bounded-complexity limitation | 32 MiB 输入 ceiling 限制原始字节，但 parser 内存表示可能高于输入大小。 | 各通用 Documents processor；后续 processor complexity budget WU。 |
| assigned authority residual | 路径校验到 `open()` 之间 symlink/rename TOCTOU 仍可能。 | 后续 file-authority/symlink-race WU；S4 保证 byte cap on actually opened handle。 |
| accepted partial semantics | directory entry cap / source skip 使 total 未知。 | `dayu.tools.doc_tools` partial fields；通过 `scan_complete=false`、`total=null` 与稳定 reason 明示。 |
| validation tooling residual | pytest-cov dotted source 在当前环境触发同进程重复加载。 | 仓库 coverage invocation toolchain；等价 coverage 证明 88%/81%。 |

---

**PASS。** 未发现实质性问题。S4 准备接受。
