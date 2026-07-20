# WU-SEMANTIC-OWNERSHIP-01 / R01 Doc Complete Input Aggregate Deepreview

## Scope

- Mode: aggregate deepreview（R01 sub-WU S1+S2 组合行为）
- Umbrella: 既有 `WU-SEMANTIC-OWNERSHIP-01`
- Internal remediation sub-WU: `R01 Doc complete input`
- Accepted umbrella plan: `227317a0`
- Accepted R01 plan: `54e35231`
- Accepted slices: R01-S1 `1a94d798`；R01-S2 `aa875ea5`
- Aggregate validation base: `54e35231`；validation HEAD: `26a65b0e`
- Branch: `phaseflow/host-issues-control`
- Output file: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-aggregate-deepreview-mimo.md`
- Included scope: `54e35231..26a65b0e` 全部 production/test/README 变更
- Excluded scope: control doc、review/implementation artifacts、其它 sub-WU
- Parallel review coverage: 无（scope 限于 2 个 production 文件 + 3 个 test 文件 + 1 个 README）

## Review Method

1. 依次完整读取 AGENTS.md、controller discussion、umbrella remediation plan、R01 independent plan、aggregate validation artifact、design truth docs。
2. 用 git log/diff 定位 S1/S2 commit 的完整 production/test/README 变更。
3. 独立读取 `source_snapshot.py`（458 行）、`doc_tools.py`（3215 行，关键函数全读）、三份 test files、tests README。
4. 独立运行全部验证：84 tests passed、pyright 0 errors、git diff --check pass、全部 semantic identifier scan 零命中、real smoke（10,001 files + 35.6 MiB + symlink escape）passed。
5. 逐项挑战 plan 中列出的六个审查维度。

## Findings

未发现实质性问题。

以下是对六个审查维度的完整覆盖说明：

### 1. SourceSnapshot 状态机与 Doc consumers 在真实大输入/错误/取消/cleanup 下是否同源

**结论：同源，无 drift。**

`SourceSnapshot` 状态机为 `new -> active -> closed`：

- `__enter__` 设置 `_entered = True`，按 64 KiB chunk 复制到真实 EOF，设置 `_snapshot_size`。
- `close()` 在 `self._lock` 内设置 `_spool = None`、`_snapshot_size = None` 并关闭 spool；materialized path 在锁外清理。
- `open()` 通过 `snapshot_size` property 检查 active 状态，返回 `_SnapshotBinaryReader`。
- `_read_at()` 在 `self._lock` 内检查 active 并读取，确保与 `close()` 串行化。
- `__exit__` 调用 `close()`；`__enter__` 的 `except BaseException` 也调用 `close()`。

错误/取消/cleanup 路径：
- `Source.open()` 的 `OSError` 原样透出，未发布的 spool 被关闭（`test_source_snapshot_open_oserror_is_preserved_and_closes_spool`）。
- `Source.read()` 的 `OSError` 原样透出（`_FailingSource` / `_FailingBinaryStream` 测试）。
- 协作取消在 `__enter__` 的 3 个检查点和 `materialize()` 的 3 个检查点生效，取消后 spool 和 partial materialized path 均被清理（`test_source_snapshot_materialize_observes_cancellation_and_cleans_resources`）。
- Python 异常和正常退出都清理 materialized path（`test_source_snapshot_cleans_materialized_file_after_python_exception`、`test_source_snapshot_cleans_materialized_file_on_normal_exit`）。
- `close()` 幂等（`test_source_snapshot_copies_unknown_length_to_eof_with_independent_cursors` 末尾断言两次 close 无异常）。

Doc consumers（`_list_files_business`、`_search_files_business`、`_read_file_business` 等）通过 `_source_snapshot()` helper 构造 `SourceSnapshot`，该 helper 只创建 `LocalFileSource` + `SourceSnapshot`，不传 byte budget。`_search_files_business` 使用 `with _source_snapshot(...) as snapshot:` 确保每个候选文件的 snapshot 在读取后清理。

### 2. source/directory cap 是否在 producer/result/schema/prompt/tests/README/LLM-readable surface 全链清零

**结论：全链清零。**

自动 scan 结果：
- `DocResourceBudget|SourceBudgetExceeded|max_source_bytes|max_directory_entries|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files` 在 `dayu tests README.md` 零命中。
- `bounded_source|BoundedSourceSnapshot|dayu-doc-bounded` 在 `dayu tests` 零命中。
- Doc scoped legacy numeric scan（`32 MiB`、`10_000`）仅命中 `dayu/documents/processors/html_extraction.py:323,333` 的两个 `-10_000` HTML 评分哨兵，与 R01 无关。

LLM-facing 文本：
- `list_files` description 只说明 `total` 是完整匹配数、`returned` 是首屏数量、`limit` 限制返回数量。无 `directory_entry_limit`、`scan_complete`（list 侧）、`truncated_reason`（list 侧）。
- `search_files` description 只说明 `result_limit` 为唯一 partial 原因。无 `source_limit`、`skipped_oversized_files`、`directory_entry_limit`。
- `read_file` / `read_file_section` description 保留 `content_truncated`、`scan_complete` 作为字符 output 事实。

`scan_complete`/`truncated_reason` 生产分类（逐行人工归属）：
- list producer/schema：零命中。
- search producer：`_search_files_business` 内 `result_limit` 设置（retain）。
- read/read-section producer：`_BoundedTextRead.scan_complete`、`_read_file_business`、`_read_file_section_business`、`_read_source_with_encoding` 的字符 output 事实（retain）。
- 无 list 相关残留。

### 3. list/search/read 的 complete-input 与 output truncation/fetch_more 是否仍由正确 owner 分离且未误接 Issue 177

**结论：正确分离，Issue 177 未实现。**

- `ToolTruncateSpec` 仍声明在 `read_file`（`_text_content_truncate(limits.read_file_max_chars)`）和 `read_file_section`（`_text_content_truncate(limits.read_file_section_max_chars)`）。
- `TruncationManager|FetchMoreToolCallable|fetch_more` 在 `doc_tools.py`/`doc_provider.py` 零命中。
- `54e35231..HEAD` 对 `dayu/host dayu/runtime dayu/contracts dayu/config/tool_discovery.json` 零 diff。
- `DocToolLimits` 的五个 output/argument limit 保留不变。
- list 的 `result_limit` 由 `DocToolLimits.list_files_max` 控制；search 的 `result_limit` 由 `DocToolLimits.search_files_max_results` 控制。
- 真实 smoke 验证 read 成功且只发生合法字符 output truncation（`test_doc_complete_input_real_smoke_above_legacy_thresholds`）。

### 4. symlink/containment/allowed paths/cancellation/process fencing 是否保持且未被统一权限设计替代

**结论：保持，未被替代。**

三条不同 owner 的 symlink 行为：

1. **directory symlink**：`_iter_directory_entries` 检查 `not entry.is_symlink() and entry.is_dir()` 后才递归。Directory symlink entry 被 yield 但不递归进入 target。与 Python 3.11 `Path.rglob("*")` 行为一致。
2. **list file symlink**：`_list_files_business` 只检查 `file_path.is_file()`，不调用 `_resolve_search_files_candidate`，不做 per-entry resolved containment。File symlink 作为 directory entry 列出，使用 symlink entry 的相对路径/名称和 `stat()` metadata。
3. **search/direct-read file symlink**：`_search_files_business` 调用 `_resolve_search_files_candidate` 在内容读取前做 resolved containment；direct read 在 `_project_doc_paths` 做输入路径 canonical resolve/containment。外部 target 不读取/拒绝。

安全边界验证：
- `allowed_paths`、`_project_doc_paths`、`_resolve_search_files_candidate`、`_raise_if_doc_cancelled`、`ProcessBackedToolExecutionCapability` 全部保留且有 owner 命中。
- `test_disallowed_path_returns_failed_outcome` 通过。
- `test_search_files_does_not_read_symlink_escape` 通过。
- 真实 smoke 中 outside symlink 正文零泄漏，direct read 返回 `permission_denied`。
- 没有实现统一 tool authorization framework。

### 5. S1/S2 所有 findings 最终状态、coverage、真实 >33 MiB + >10,000-entry smoke、README/R03 handoff、allowlist 是否组合闭合

**结论：组合闭合。**

验证矩阵：

| 验证项 | 结果 |
|---|---|
| `pytest tests/documents tests/tools/test_doc_tools_provider.py` | 84 passed |
| 5 个 combined ToolTruncateSpec/fetch_more owner nodes | 5 passed |
| 真实 threshold smoke + disallowed path + search symlink escape | 3 passed |
| `source_snapshot.py` coverage | 93.5%（144/154 statements） |
| `doc_tools.py` coverage | 80.5%（620/770 statements） |
| pyright | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | pass |
| semantic identifier scan | 零命中 |
| LLM-facing scan | 零命中 |
| Issue 177 non-implementation scan | 零命中 |
| security/cancellation scan | 保留命中，行为由测试证明 |
| allowed-file diff | 只含 R01 授权文件 |

真实 smoke 实际数值：
- 10,001 个普通小文件 + 1 个 35,651,621-byte 大文件（尾部 36-byte marker）+ 1 个 allowed root 内指向 outside root 的 file symlink。
- list 完整观察 10,003 entries；read 成功；search 在大文件尾部命中并扫描到 EOF；outside symlink 正文零泄漏，direct read 返回 `permission_denied`。

README decision：
- `tests/README.md`：S2 更新 Documents/Tools 段落。
- `dayu/config/README.md`：无需更新（只描述 `allowed_paths` 和五个 output limits）。
- 根 `README.md`：无需更新（不描述 Doc cap/error/workflow）。
- `dayu/README.md`：无需更新（分层与装配不变）。

R03 handoff：R01 completion artifact 包含逐文件 LLM-facing inventory（§13.2），列出每个 tool schema description、parameter description、error message、result field、prompt fixture 的 final disposition。R03 必须消费该 inventory。

### 6. 是否有 cross-slice ownership drift、下游补偿、compatibility seam、deferred Issue creep 或 unrelated change

**结论：无。**

`54e35231..26a65b0e` 的 4 个 commit 全部与 R01 直接相关：
- `1a94d798`：S1 source snapshot rename/rewrite + doc_tools.py + tests。
- `aa875ea5`：S2 directory traversal + doc_tools.py + tests + README。
- `547c926e`、`26a65b0e`：control doc gate 状态更新。

无 unrelated production/test/README 变更。无 compatibility wrapper、re-export、alias、fallback、loose parsing 或默认值 shim。无 deferred Issue creep（Issue 177/178/175/142/151 均未被触及）。无下游补偿（no consumer re-computes completeness）。

## Open Questions

无。

## Residual Risk

| residual | 当前处理 | owner/destination |
|---|---|---|
| 极大本地 source/目录可能消耗磁盘、时间或 inode | 完整 spool、process boundary、cooperative/parent cancellation 与 output limit；不恢复未经裁决 hard-fail | Issue #177 / 后续输入治理设计 |
| 五工具 output/remainder 没有全部通过 `TruncationManager` 无损续读 | 保留 current spec/framework owner，不扩张 R01 | GitHub Issue #177 |
| search 达到合法 result limit 后不会扫描剩余 entry | schema 自解释为 output result limit；不伪造完整 total | Issue #177 若未来以 complete result + fetch_more 重构 |
| symlink/TOCTOU 是既有局部防御边界 | 保持三条不同 owner 行为；R01 不统一权限或重设计 symlink policy | 后续独立 tool authorization/filesystem hardening WU |

上述 residual 均不降低 R01 accepted contract。它们是 umbrella 已分类的后续 destination，不是 R01 的未闭合项。

## Verification Summary

| 维度 | 状态 | 证据 |
|---|---|---|
| SourceSnapshot 状态机同源 | PASS | 代码走读 + 14 个 owner tests + real smoke |
| source/directory cap 全链清零 | PASS | 6 条 semantic identifier scan 零命中 + LLM-facing scan 零命中 |
| output truncation 与 Issue 177 分离 | PASS | ToolTruncateSpec 保留 + TruncationManager 零引用 + host/runtime 零 diff |
| symlink/containment/security 保持 | PASS | 3 条 owner 行为 + security scan + 2 个 security tests + real smoke |
| S1/S2 findings/coverage/smoke 闭合 | PASS | 84 tests + coverage >=80% + pyright 0 + real smoke 10k+33MiB |
| cross-slice drift/compatibility seam | PASS | 4 commits 全部 R01 相关 + 无 wrapper/fallback/shim |

**Aggregate deepreview PASS。未发现实质性问题。**
