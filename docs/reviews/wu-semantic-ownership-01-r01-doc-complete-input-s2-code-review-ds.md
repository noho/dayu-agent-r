# WU-SEMANTIC-OWNERSHIP-01 / R01-S2 Code Review — AgentDS 第二路独立审查

## Scope

- **Mode**: current changes (slice base → working tree)
- **Umbrella WU**: 既有 `WU-SEMANTIC-OWNERSHIP-01`
- **Internal remediation sub-WU**: `R01 Doc complete input`, slice `R01-S2`
- **Accepted plan commit**: `54e35231`
- **Slice base**: `547c926e`（`docs: enter R01-S2 directory completeness implementation`）
- **Working tree HEAD**: 脏工作区，含 S2 implementation + controller validation follow-up（formatter churn 恢复）
- **Output file**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-s2-code-review-ds.md`
- **Included scope**: `dayu/tools/doc_tools.py`、`tests/tools/test_doc_tools_provider.py`、`tests/README.md` 的完整 S2 diff（110 行生产改动，350 行测试改动，6 行 README）
- **Excluded scope**: `docs/host/issues-implementation-control.md` 仅 gate status 行更新（无生产语义变更）；S1 已接受的 `source_snapshot.py`/`test_processors.py` 非本 slice diff
- **Parallel review coverage**: 无；本路独立完成全量走读

## 审查方法

1. 完整逐行阅读 `dayu/tools/doc_tools.py`（3216 行）、`tests/tools/test_doc_tools_provider.py` 的 S2 diff 与全文件上下文、`tests/README.md` 改动段落。
2. 独立运行全部 provider tests（66 passed）、real smoke（1 passed, 2.06s）、key adversarial tests（10 passed）、ToolRuntime owner boundary tests（4 passed, 3 warnings）。
3. 独立运行 pyright（0 errors）、全部删除语义/LLM/security/Issue-177 propagation scans（均零命中或仅预期命中）。
4. 逐项走读 controller validation §6 指定的五个 review focus area，并对 iterator、heap、search partial、containment、cancellation、symlink、ToolTruncateSpec/fetch_more、Issue 177 边界做 adversarial failure pass。
5. 检查是否存在 unrelated change、下游补偿、兼容 shim、统一 authorization framework 偷带或 deferred Issue creep。

## Findings

### 未发现实质性问题

经完整逐行走读、独立验证与 adversarial failure pass，本 slice 的 **shared iterator 稳定顺序**、**取消观察完整覆盖**、**目录/文件 symlink 行为**、**list 有界 heap 精确 total/scanned_entries**、**search 仅 result_limit partial**、**containment 不漂移**、**source/directory cap 全链删除**、**真实阈值 smoke**、**ToolTruncateSpec/fetch_more 边界保持**、**Issue 177 零进入** 均正确实现 accepted plan contract。以下逐项记录覆盖范围、验证证据与 residual risk。

---

### 覆盖范围与验证证据

#### 1. 共享 iterator 的稳定 depth-first 顺序

**代码位置**: `dayu/tools/doc_tools.py:1416-1469`（`_directory_entry_sort_key` + `_iter_directory_entries`）

**实现**:
- 每层收集全部 entry 后按 `(name.casefold(), name)` 排序（line 1459）。
- 按排序后顺序 yield，并在递归普通子目录前检查 `not entry.is_symlink() and entry.is_dir()`（line 1464），与 Python 3.11 `Path.rglob("*")` 的 directory-symlink 不递归语义一致。
- 非递归模式仅产出顶层 entry，不进入任何子目录。

**验证**:
- `test_list_and_search_order_is_stable_across_reversed_creation_order` 创建两棵内容相同但创建顺序相反的目录树，断言 list records 与 search matches 完全相同，且顺序为 `Alpha.txt, bravo.txt, Charlie.txt, zeta.txt`（casefold 优先，原名 tiebreak）。
- `test_directory_symlink_entry_is_yielded_without_recursing_target` 断言 directory symlink 可见 (`linked-directory`) 但其 target 内容不可见 (`linked-directory/inside.txt` 不在 entries 中)。

**adversarial pass**: iterator 每层先全量收集再排序，对极大扁平目录（10 万+ entry）内存开销是 entry 数量级；这是确定性排序的必要代价，已被 accepted plan 接受为产品语义而非回归。取消检查覆盖列前（line 1455）、每 entry 收集时（line 1457）、每次 yield 前（line 1462）、每次递归入口（line 1465 进入的下一帧 line 1455）。OSError 沿既有异常路径透出，最终由 `_execute_doc_business_value` 的 `except Exception` 转为 `execution_error`，与旧 `rglob` 行为一致。

**结论**: 无 finding。

---

#### 2. 取消/异常/symlink 行为

**取消观察覆盖**:

| 检查点 | 位置 | 触发条件 |
|---|---|---|
| `_iter_directory_entries` 入口 | line 1455 | 每层递归入口 |
| `iterdir()` 循环内 | line 1457 | 每 entry 收集 |
| yield 前 | line 1462 | 每 entry 产出 |
| `_list_files_business` 入口 | line 1507 | 遍历前 |
| `_list_files_business` 出口 | line 1548 | 结果返回前 |
| `_search_files_business` 入口 | line 1651 | 遍历前 |
| `_search_files_business` 出口 | line 1699 | 结果返回前 |

`test_list_files_directory_iteration_observes_cancellation` 注入 `ImmediateCancellationToken`，断言取消后 `_DocCancelledError` 抛出且不返回伪造 complete。

**目录异常**: `iterdir()` 的 `OSError` 不做局部 catch，沿既有路径透出为 `execution_error`。旧 `rglob("*")` 对不可读子目录行为相同。

**Symlink 行为**（三条不同 owner boundary，与 accepted plan §3.2/§4.2/§9.4/§10 一致）:

| owner boundary | 行为 | 证据 |
|---|---|---|
| list file-symlink | `is_file()` 跟随 symlink，以 symlink entry 自身 relative path/name 和 `stat()` 返回 metadata；不做 per-entry resolve/containment | `test_list_files_keeps_allowed_file_symlink_as_directory_entry`: `alias.txt` 列在 `target.txt` 前，path=`alias.txt`, size=target stat |
| search candidate resolve | `_resolve_search_files_candidate` 在正文读取前 resolve/containment；outside symlink target 被跳过 | `test_search_files_does_not_read_symlink_escape` 保留并通过 |
| direct read path projection | `_project_doc_paths` 对 canonical resolved path 做 containment；outside symlink 在输入边界拒绝 | real smoke: `test_doc_complete_input_real_smoke_above_legacy_thresholds` 对 outside symlink 的 direct read 返回 `permission_denied` |

**结论**: 无 finding。三条 owner boundary 未被包装成统一 authorization contract，符合 accepted plan 的明确禁止。

---

#### 3. list 有界 heap 的精确 total/scanned_entries 与稳定前 N

**代码位置**: `dayu/tools/doc_tools.py:1472-1555`

**实现**:
- `scanned_entries` 对每个 iterator 产出的 entry（含目录、symlink）递增（line 1513），在 `is_file()` 与 pattern match 之前。
- `matched_files` 对每个匹配文件递增（line 1527），与 heap 大小无关。
- `sort_key` 从旧 2-tuple `(name.lower(), relative_path.lower())` 扩展为 4-tuple `(name.casefold(), name, relative_path.casefold(), relative_path)`（line 1529-1533），补足同名字文件在不同子目录时的确定性 tiebreak。
- heap 维护 `actual_limit` 个最小候选（`__lt__` 反向比较，line 152）；达到容量后仅当新候选小于堆顶时替换（line 1538）。
- `filtered_files` 按 sort_key 升序排列（line 1544-1547）。
- `total = matched_files`（完整匹配数），`returned = len(filtered_files)`（首屏记录数），删除 `scan_complete`/`truncated_reason`。

**验证**:
- `test_list_files_observes_all_entries_and_omits_partial_only_fields`: 4 entries、3 匹配、limit=2 → `scanned_entries=4`, `total=3`, `returned=2`，且 `scan_complete`/`truncated_reason` 不在 keys 中。
- `test_list_files_result_limit_keeps_exact_total_after_complete_scan`: 3 entries、3 匹配、limit=2 → `scanned_entries=3`, `total=3`, `returned=2`，files 顺序为 `a.txt, b.txt`（c 被 heap 裁剪）。
- real smoke: 10,003 entries（10,001 小文件 + 1 大文件 + 1 symlink），pattern 仅匹配大文件 → `scanned_entries=10003`, `total=1`, `returned=1`。

**adversarial pass**:
- `actual_limit=0` 时 heap 不 push 任何候选（line 1538 `actual_limit > 0` guard），`filtered_files` 为空，`total` 仍正确报告完整匹配数。
- `OSError` 在 `stat()` 时被 catch 并 `continue`（line 1540-1542），不影响其它 entry 的 total/scanned_entries 计数——这是一个 **已知的可用性权衡**：一个不可读文件不阻断整个目录遍历，但 `scanned_entries` 包含该 entry 而 `matched_files` 不包含。这与旧代码行为一致。

**结论**: 无 finding。

---

#### 4. search 只有 result_limit partial 且 containment 不漂移

**代码位置**: `dayu/tools/doc_tools.py:1613-1708`

**实现**:
- 消费同一 `_iter_directory_entries`，`recursive=True`（与旧 `rglob("*")` 一致）。
- 每个候选先经 `_resolve_search_files_candidate`（line 1660-1665）做 resolved containment/file 检查。该函数 resolve 后比对 allowed_roots，再确认 `is_file()`；任一失败跳过。**containment 不因 iterator 共享而漂移**。
- `scan_complete` 初始 `True`，`truncated_reason` 初始 `None`（line 1649-1650）。
- 仅当 `len(matches) >= actual_limit` 时设为 `scan_complete=False, truncated_reason="result_limit"` 并 break（line 1693-1696）。
- 遍历到 EOF 时保持 `scan_complete=True, truncated_reason=None`。
- 删除 `directory_entry_limit` 分支、`skipped_oversized_files`、`source_limit`。

**验证**:
- `test_search_files_scans_to_eof_when_result_limit_is_not_reached`: 3 entries（2 无匹配 + 1 命中），limit=5 → `scanned_entries=3`, `total_matches=1`, `scan_complete=true`, `truncated_reason=null`。
- `test_search_files_cumulative_match_limit_returns_result_partial`: limit=2 且 3 个命中 → `scan_complete=false`, `truncated_reason=result_limit`。
- real smoke: 10,003 entries，唯一 tail marker 命中 → `scanned_entries=10003`, `total_matches=1`, `scan_complete=true`, `truncated_reason=null`。outside symlink 零命中。

**adversarial pass**:
- search 始终 `recursive=True`，无可选 recursive 参数。这是旧代码行为保留，不是 S2 引入的限制。旧 `rglob("*")` 同样始终递归。
- `_resolve_search_files_candidate` 对 broken symlink（`OSError` on `resolve(strict=True)`）返回 `None`，candidate 被跳过。这与旧代码行为一致。
- `total_matches` 永远是 `len(matches)`——即返回命中数，不是目录中的总命中数。这是 search 的现有 contract，在 schema description 中自解释（"total_matches 等于返回命中数"），不伪装为 complete total。

**结论**: 无 finding。

---

#### 5. source/directory cap 的 schema/prompt/test/production 传播清零

**Propagation scans（全部零命中或仅预期命中）**:

| scan | 范围 | 结果 |
|---|---|---|
| `DocResourceBudget\|SourceBudgetExceeded\|...\|skipped_oversized_files` | `dayu tests README.md` | **零命中** |
| `bounded_source\|BoundedSourceSnapshot\|dayu-doc-bounded` | `dayu tests` | **零命中** |
| `max_directory_entries` | `dayu tests README.md` | **零命中** |
| `_DOC_DIRECTORY_MAX_ENTRIES` | `dayu tests` | **零命中** |
| legacy `10_000` literal | Doc scope (`doc_tools.py`, `processors/`, test documents/provider) | 仅 `html_extraction.py:323,333` 的 `-10_000` HTML 评分哨兵，不控制 entry/source/budget |
| legacy `32.*MiB\|33554432` | Doc scope | **零命中** |
| `scan_complete\|truncated_reason` | 全生产 `.py` | list producer/result 零命中；仅 search `result_limit`（line 791,793,1649-1650,1694-1695,1706-1707）、read 字符输出（line 161,864-865,936,1790,1858,2311,2336）——全部合法 owner |
| `directory_entry_limit` | `dayu tests README.md` | **零命中** |
| `source_limit\|skipped_oversized_files` | `dayu tests README.md` | **零命中** |
| rejected LLM guidance（较小文件/拆分文件/缩小文件范围/缩小目录） | `doc_tools.py`, prompts, provider tests | **零命中** |

**Schema description 验证**:
- `test_doc_tool_descriptions_explain_only_retained_output_facts` 做 exact string 断言：list description 不再含 `scan_complete`/`truncated_reason`/`directory_entry_limit`；search description 只解释 `result_limit` 且不含 `directory_entry_limit`；read description 保留 `content_truncated`/`scan_complete`。
- 参数 schema 的 `limit`/`maximum` 字段保持不变，仍为 output/argument contract。

**结论**: 无 finding。source/directory cap 在 producer、result、schema、LLM-facing text、tests 和 README 中全部清零，无残留。

---

#### 6. 真实 10,001 文件与 >33 MiB smoke 确经 discovery→callable

**代码位置**: `tests/tools/test_doc_tools_provider.py` — `test_doc_complete_input_real_smoke_above_legacy_thresholds`

**实现事实**:
- 创建 10,001 个真实普通 `.txt` 小文件（逐文件 `write_bytes`）。
- 创建 `zzzz-large-tail.txt`：34 次 1 MiB chunk + 换行 + 36-byte tail marker = 35,651,621 bytes（~34 MiB），>33 MiB threshold。
- 创建 outside symlink 指向 outside root 中含相同 marker 的文件。
- 调用链为 `ToolsDiscoveryProviderSpec → discover_tools → ToolDefinition.callable`，不经 monkeypatch 或伪 declared length。
- list: `total=1, returned=1, scanned_entries=10003`，大文件 tail path 命中。
- read: 成功返回 2,000 chars，`content_truncated=true`，`ToolTruncateSpec.target_field=content` 保留。
- search: tail marker 命中，`scanned_entries=10003, total_matches=1, scan_complete=true`。
- direct read outside symlink: `permission_denied`。

**独立验证**: `pytest ...::test_doc_complete_input_real_smoke_above_legacy_thresholds -q` → `1 passed in 2.06s`。

**结论**: 无 finding。smoke 真实覆盖 discovery→callable、list tail、read success-with-truncation、search tail、symlink containment。

---

#### 7. ToolTruncateSpec/fetch_more、安全机制与 Issue 177 边界

**ToolTruncateSpec/fetch_more 边界保持**:
- `read_file` 的 `truncate=_text_content_truncate(limits.read_file_max_chars)` 不变（line 871）。
- `read_file_section` 的 `truncate=_text_content_truncate(limits.read_file_section_max_chars)` 不变（line 942）。
- `TruncationManager\|FetchMoreToolCallable\|fetch_more` 对 `doc_tools.py`/`doc_provider.py` **零命中**。
- 四个 ToolRuntime owner tests（`test_truncated_result_exposes_only_cursor_and_scope_token`、`test_fetch_more_dispatches_as_normal_tool_and_is_single_use`、`test_enabled_fetch_more_injects_schema_and_callable_when_truncation_enabled`、`test_combined_truncate_specs_and_fetch_more_owner`）全部通过。

**安全机制保持**:
- `allowed_paths`、`_project_doc_paths`、`_resolve_search_files_candidate`、`_raise_if_doc_cancelled`、`ProcessBackedToolExecutionCapability` 均有预期命中且对应测试通过。
- `test_disallowed_path_returns_failed_outcome`、`test_search_files_does_not_read_symlink_escape` 保留并通过。

**Issue 177 边界**:
- 对 `dayu/host dayu/runtime dayu/contracts dayu/config/tool_discovery.json` 零 diff。
- Doc producer 未接入 `TruncationManager`/remainder store/cursor/scope token/framework `fetch_more`。
- R01-S2 未声称 Issue 177 已关闭。

**结论**: 无 finding。

---

#### 8. 不存在 unrelated change、下游补偿、兼容 shim、统一 authorization framework 或 deferred Issue 偷带

**Unrelated change scan**:
- `git diff --name-only 547c926e --` 仅含 `dayu/tools/doc_tools.py`、`tests/tools/test_doc_tools_provider.py`、`tests/README.md`、`docs/host/issues-implementation-control.md`。control doc 仅 gate status 行更新（"R01-S2 implementation" → "R01-S2 dual code review"），无生产语义变更。
- Host、runtime、contracts、config、Engine、Service、UI、Fins 零 diff。

**下游补偿/兼容 shim scan**:
- 无 `hasattr`/`getattr`、无旧类名 alias、无 re-export、无 compatibility wrapper。
- `_ListedFileCandidate.sort_key` 从 2-tuple 改为 4-tuple 是语义增强（补足嵌套目录 tiebreak），不是兼容旧调用方。
- S1→S2 过渡签名（`max_directory_entries` 临时传递）已在 S2 完全删除，无遗留参数或常量。

**统一 authorization framework scan**:
- `unified.*authoriz\|authorization.*framework` 对 S2 changed files 零命中。
- list/search/direct-read 三条 symlink owner boundary 未被包装成统一权限 contract，符合 accepted plan 的明确禁止。

**Deferred Issue creep scan**:
- `deferred.*Issue\|Issue.*deferred` 对 S2 changed files 零命中。
- Issue 142/151/175/177/178 均未进入 changed files。
- Topic 8（Engine 240 chars）零触及。
- Topic 9（unified authorization）零触及。

**结论**: 无 finding。

---

## Open Questions

无。所有 controller review focus area 均可通过直接代码证据和独立验证闭合。

## Residual Risk

| residual | classification | owner / destination |
|---|---|---|
| 极大扁平目录（10 万+ entry）下 iterator 全量收集排序的内存开销 | `accepted product tradeoff` | 确定性顺序是 controller accepted contract；内存开销是排序必要代价，不恢复 entry cap。后续 input governance 设计可考虑 streaming sort，但当前无证据表明需要 |
| search `total_matches` 仅是返回命中数，不是目录完整匹配数 | `tracked by existing issue` | GitHub Issue #177 若未来以 complete result + fetch_more 重构时统一处理；当前 schema description 已自解释 |
| `OSError` 在 `stat()` 时被静默跳过（line 1540-1542），不可读文件的 `scanned_entries` 包含但 `matched_files` 不包含 | `pre-existing behavior` | 旧代码同样在 `stat()` 异常时继续；当前无证据表明需要差异化处理。list result 的 `scanned_entries` 语义已是"已检查目录项数"，包含 stat 失败的 entry 忠实于这一语义 |
| 真实 smoke 的 10,001+ 文件创建时间（~2s）在 CI 或极慢文件系统可能超时 | `operational monitoring` | 当前 pytest 2.06s 通过；如 CI 环境显著更慢，调整 fixture 规模或标记为 slow 即可，不改变 production contract |

以上 residual 均不降低 R01-S2 accepted contract；不构成 material finding。

## 审查结论

**PASS** — 未发现实质性问题。R01-S2 的目录 entry cap 全链删除、确定性 cancellable iterator、list 完整事实、search 合法 result-limit partial、symlink owner 保持、真实阈值 smoke、ToolTruncateSpec/fetch_more/security 边界保持、Issue 177 零进入、全部 propagation scans 清零——均符合 accepted plan `54e35231` 与 controller discussion Topic 1 的最终裁决。

审查覆盖了 controller validation §6 的全部五个 review focus area，并额外执行了 unrelated change、下游补偿、兼容 shim、deferred Issue creep 与统一 authorization framework 扫描，均无发现。
