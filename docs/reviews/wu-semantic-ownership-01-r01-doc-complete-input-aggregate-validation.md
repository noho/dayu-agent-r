# WU-SEMANTIC-OWNERSHIP-01 / R01 Doc Complete Input Aggregate Validation

## 1. Gate 与身份

- umbrella WU：既有 `WU-SEMANTIC-OWNERSHIP-01`；不是新 WU。
- internal remediation sub-WU：`R01 Doc complete input`。
- accepted umbrella plan：`227317a0`。
- accepted R01 plan：`54e35231`。
- accepted slices：R01-S1 `1a94d798`；R01-S2 `aa875ea5`。
- aggregate validation base：accepted R01 plan `54e35231`；validation HEAD `26a65b0e`。

本 artifact 是 controller 对 S1+S2 组合行为的独立验证，授权范围只到双路 aggregate deepreview。它不替代 R01 completion/final closeout，不授权 Issue 177、R02/R03、统一 tool authorization framework 或其它 umbrella remediation。

## 2. 组合 owner contract

R01 的 root cause 与 owner 在组合状态中闭合：

1. `dayu.documents.processors.source_snapshot.SourceSnapshot` 是 source 完整输入的唯一 owner：单次打开 `Source`，复制到真实 EOF，提供独立 cursor、精确 active size、受控 materialization 和统一 cleanup；不存在 byte budget、oversized failure 或 source skip。
2. `dayu.tools.doc_tools` 是目录观察与 list/search 业务事实的 owner：共享 deterministic cancellable depth-first iterator 完整观察目录；不存在 entry cap 或 `directory_entry_limit` partial。
3. list 返回完整观察后的精确 `total/scanned_entries` 与稳定有界前 N；不再承诺 list `scan_complete/truncated_reason`。
4. search 只允许 output `result_limit` 产生 partial；未达到 limit 时扫描到 EOF。search containment 仍在 candidate resolve 边界，direct read containment 仍在 path projection 边界。
5. read/read-section 的字符 output truncation、`ToolTruncateSpec` 与 Host-owned `fetch_more` 保留；Doc 五工具完整接入 `TruncationManager` 仍只由 Issue 177 追踪。

没有下游 consumer 重新计算完整性，没有 schema/README 隐藏 producer cap，没有 compatibility wrapper/alias/fallback，也没有把三条 symlink 行为统一成新 authorization contract。

## 3. Controller aggregate 验证

在 Python 3.11 venv 中重跑 accepted plan §14.2 exact matrix：

```text
pytest tests/documents tests/tools/test_doc_tools_provider.py -q
84 passed

pytest <5 个 combined ToolTruncateSpec/fetch_more/representative-provider owner nodes> -q
5 passed, 3 third-party edgar deprecation warnings

pytest <real threshold smoke + disallowed path + search symlink escape> -q
3 passed

coverage run -m pytest tests/documents tests/tools/test_doc_tools_provider.py -q
84 passed

dayu/documents/processors/source_snapshot.py
144 / 154 statements, 93.50649350649351%

dayu/tools/doc_tools.py
620 / 770 statements, 80.51948051948052%

python -m pyright
0 errors, 0 warnings, 0 informations

git diff --check 54e35231..HEAD
pass
```

真实 smoke 重建并通过：

- 10,001 个真实普通文件；
- 一个 35,651,621-byte 文件，尾部有 36-byte marker；
- 一个 allowed root 内指向 outside root 的 file symlink；
- discovery→provider definitions→`ToolDefinition.callable` 真实调用；
- list 完整观察 10,003 entries；read 成功且只发生合法字符 output truncation；search 在大文件尾部命中并扫描到 EOF；outside symlink 正文零泄漏，direct read 返回 `permission_denied`。

## 4. Propagation 与 allowed-file audit

### 4.1 删除语义与 LLM-facing

- `DocResourceBudget|SourceBudgetExceeded|max_source_bytes|max_directory_entries|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files` 在 `dayu tests README.md` 零命中。
- `bounded_source|BoundedSourceSnapshot|dayu-doc-bounded` 在 `dayu tests` 零命中。
- rejected LLM guidance `directory_entry_limit|source_limit|skipped_oversized_files|source_budget_exceeded|较小文件|拆分文件|缩小文件范围|缩小目录` 在 Doc tool、prompts 与 provider tests 零命中。
- Doc scoped legacy numeric scan仅命中未修改的 `dayu/documents/processors/html_extraction.py:323,333` 两个 `-10_000` HTML 评分哨兵。它们给 HTML candidate 评分，不参与 source bytes、directory entries、遍历停止、result partial 或 LLM-facing contract；故保留并分类为 unrelated unchanged literal。

### 4.2 `scan_complete/truncated_reason` 生产分类

生产命中全部位于 `dayu/tools/doc_tools.py`，逐 owner 分类如下：

| path:line / symbol | tool | semantic owner | disposition |
|---|---|---|---|
| `161 / _BoundedTextRead.scan_complete` | read/read-section | raw 字符 output scan fact | retain |
| `791,793 / _build_search_files_definition` | search | `result_limit` partial schema | retain |
| `864,865 / _build_read_file_definition` | read | 字符 output/line-scan schema | retain |
| `936 / _build_read_file_section_definition` | read-section | 字符 output schema | retain |
| `1649,1650,1694,1695,1706,1707 / _search_files_business` | search | `result_limit` result producer | retain |
| `1790 / _read_file_business` | read | raw scan result producer | retain |
| `1858 / _read_file_section_business` | read-section | output truncation result producer | retain |
| `2311,2336 / _read_source_with_encoding` | read/read-section | 字符 scan producer | retain |

list producer、list schema、生产 consumer 均无 `scan_complete/truncated_reason` 命中。provider tests 中 list 仅保留字段不存在的 negative assertions；其它命中只断言 search/read 合法事实。`tests/README.md` 不再描述 directory partial。

### 4.3 Output、Issue 177 与 security

- `ToolTruncateSpec|truncate=_text_content_truncate` 仍命中 read/read-section 定义与 owner tests。
- `TruncationManager|FetchMoreToolCallable|fetch_more` 在 `doc_tools.py/doc_provider.py` 零命中；`54e35231..HEAD` 对 `dayu/host dayu/runtime dayu/contracts dayu/config/tool_discovery.json` 零 diff。
- `allowed_paths`、`_project_doc_paths`、`_resolve_search_files_candidate`、cancellation checks 与 `ProcessBackedToolExecutionCapability` 仍有 owner 命中，并由 aggregate security/cancellation tests证明行为。

### 4.4 File allowlist

相对 `54e35231` 的 semantic code/test/README diff 只包括：

- `bounded_source.py -> source_snapshot.py` 的 owner rename/rewrite；
- `dayu/tools/doc_tools.py`；
- `tests/documents/test_processors.py`、`tests/documents/test_import_boundary.py`、`tests/tools/test_doc_tools_provider.py`；
- `tests/README.md`。

其余 diff 只有 R01 implementation/review/controller artifacts 与 phaseflow control state。无其它 production/test/README、临时 fixture、coverage、spool、materialized file、secret、workspace config 或 `__pycache__` 进入 status/diff；验证开始时工作树干净，验证后只新增本 aggregate artifact 并修改当前 control gate。

## 5. README 与安全边界

- `tests/README.md` 已在 S2 仅迁移 Documents/Tools owner 段落到 complete snapshot/full traversal/real threshold smoke。
- `dayu/config/README.md`、根 README、`dayu/README.md` 与各层 README 不描述被删除的 Doc input cap，且分层、安装、CLI/用户工作流未改变，无需更新。
- 保留 Doc `allowed_paths`、路径 projection、search candidate containment、directory-symlink no-recursion、direct-read symlink rejection、cooperative/parent cancellation、process fencing 与 ToolRuntime output governance。
- 没有实现统一 tool authorization framework；没有删除现有 defense-in-depth。

## 6. Review focus 与 gate decision

Controller aggregate validation **PASS**，没有新增 finding 或 blocker。AgentMiMo / AgentDS 的 complete aggregate deepreview 必须覆盖：

1. SourceSnapshot 状态机与 Doc list/search consumer 的组合是否在真实大输入、错误、取消与 cleanup 下同源；
2. source/directory cap 是否在 producer、result、schema、prompt、tests、README、memory/trace 可见面完整清零；
3. output truncation/fetch_more 与 input completeness 是否仍由不同 owner 管理，没有误接 Issue 177；
4. list/search/read 三条 symlink/containment行为、安全、process fencing 是否保持且未被统一权限设计替代；
5. S1/S2 所有 accepted/rejected finding、真实 smoke、coverage、README、R03 handoff 和 allowed-file boundary 是否组合闭合；
6. 是否存在 cross-slice semantic ownership drift、下游补偿、兼容 seam、deferred Issue creep 或 unrelated change。

下一 gate 是双路完整 R01 aggregate deepreview。Reviewer verdict 不授权 R01 completion/accepted aggregate commit；任何 accepted finding 必须由 AgentCodex 修复并经双路完整 re-review。
