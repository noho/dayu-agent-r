# WU-SEMANTIC-OWNERSHIP-01 / R01-S2 Controller Validation

## 1. Gate 与范围

- umbrella WU：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- internal remediation sub-WU：`R01 Doc complete input`；不是新 WU。
- slice：`R01-S2 Directory completeness`。
- accepted plan commit：`54e35231`。
- slice base：`547c926e`，其父链已包含 R01-S1 accepted commit `1a94d798`。
- implementation artifact：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-implementation-s2-codex.md`。

本 artifact 是 controller 对 S2 实现的独立验证复核，不替代 AgentMiMo / AgentDS code review，不授权 R01 aggregate closeout、Issue 177 或后续 remediation sub-WU。

## 2. 动机与语义 owner 复核

R01-S2 的动机成立。直接代码证据显示，旧 `_DOC_DIRECTORY_MAX_ENTRIES`、`max_directory_entries` 和 `directory_entry_limit` 把观察预算误承诺成 Doc list/search 业务完整性事实；这与 controller Topic 1 的“完整输入、只保留 output truncation/fetch_more”裁决直接冲突。

正确 owner 是 `dayu.tools.doc_tools` 的目录遍历、list/search result producer 与 tool schema：

- 模块级 `_iter_directory_entries` 统一拥有稳定、可取消的目录观察顺序；每层按 `(name.casefold(), name)` 排序，再做 depth-first 遍历。
- 目录 symlink 作为 entry 产出但不递归其目标；file symlink 继续作为 list entry。search 仍在 `_resolve_search_files_candidate` 内执行 resolve/containment，direct read 仍由 `_project_doc_paths` 拒绝越界。
- list 扫描到 EOF，`total` 与 `scanned_entries` 是精确完整事实，output `limit` 只约束有界 heap 和返回记录数；list 删除 `scan_complete` / `truncated_reason`。
- search 未达到结果 limit 时扫描到 EOF；只有结果 limit 可以产生 `scan_complete=false` 和 `truncated_reason=result_limit`。
- 删除 `_DOC_DIRECTORY_MAX_ENTRIES`、全部 `max_directory_entries` 参数、counter break、`directory_entry_limit` schema 与 LLM-facing 恢复引导；没有新增替代预算、fallback、compatibility shim 或下游补偿。

## 3. 直接 diff 与测试复核

总控完整读取 `dayu/tools/doc_tools.py`、`tests/tools/test_doc_tools_provider.py`、`tests/README.md` 与 implementation artifact 的最终差异。首次实现中两个 Python 文件曾有整文件 formatter churn；同 gate follow-up 已逐 hunk 恢复所有非 S2 格式变化，当前 tracked semantic diff 仅剩 accepted S2 owner、contract tests 和 README owner 段落。

新增/迁移测试覆盖：

- list 完整观察、精确 `total/scanned_entries`、有界稳定 output 和 partial-only 字段缺失；
- 相同目录内容按相反创建顺序得到相同 list/search 顺序；
- 目录 symlink 可见但不递归，内部 file symlink 保持 list entry；
- search EOF 与 `result_limit` 两种合法状态；
- list/search 精确 LLM-facing 描述；
- 真实 10,001 个普通文件、一个 35,651,621-byte 大文件和一个越界 symlink，经 `ToolsDiscoveryProviderSpec -> discover_tools -> ToolDefinition.callable` 验证 list/read/search/containment；
- 既有 cancellation、process fencing、allowed paths、read output truncation 和 ToolRuntime `fetch_more` owner tests 保留。

真实 smoke 的完整目录共有 10,003 个 entry。list 对唯一大文件返回 `total=1 / returned=1 / scanned_entries=10003`；read 仍由 `ToolTruncateSpec` 把本次 content 输出限制为 2,000 字符；search 在大文件尾部找到 marker、扫描到 EOF且不读取越界 symlink；direct read 越界 symlink 返回 `permission_denied`。

## 4. Controller 独立验证

在项目 Python 3.11 venv 中重跑：

```text
pytest tests/tools/test_doc_tools_provider.py -q
66 passed

pytest <四个 ToolTruncateSpec / fetch_more owner nodes> -q
4 passed, 3 third-party edgar deprecation warnings

pytest <real smoke + symlink/containment + cancellation nodes> -q
6 passed

coverage run -m pytest tests/documents/test_processors.py \
  tests/documents/test_import_boundary.py \
  tests/tools/test_doc_tools_provider.py -q
84 passed

dayu/tools/doc_tools.py: 620 / 770 statements, 80.51948051948052%

python -m pyright
0 errors, 0 warnings, 0 informations

python -m ruff check dayu/tools/doc_tools.py tests/tools/test_doc_tools_provider.py
All checks passed

git diff --check 547c926e --
pass
```

传播与边界扫描：

- `DocResourceBudget|SourceBudgetExceeded|max_source_bytes|max_directory_entries|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files` 在 `dayu tests README.md` 零命中。
- `bounded_source|BoundedSourceSnapshot|dayu-doc-bounded` 在 `dayu tests` 零命中。
- `547c926e..worktree` 对 `dayu/host dayu/runtime dayu/contracts dayu/config/tool_discovery.json` 零 diff。
- `ToolTruncateSpec`、`allowed_paths`、`_project_doc_paths`、`_resolve_search_files_candidate`、cancellation checks 与 process-backed capability 仍有预期 owner/test 命中。
- Issue 177 的 Doc/TruncationManager wiring 未进入本 slice；没有统一 tool authorization framework。

## 5. README 与 residual risk

总控确认 AgentCodex 已先遵守 `tests/README.md` 的更新约束，仅迁移 Documents import/processor 与 Tools Doc provider 的测试职责描述。其它 README 的读者 contract 未因本 slice 改变。

当前可见 residual risk 是完整目录观察的运行成本可能随目录规模增长；这是 controller 已裁决的产品语义，不得重新变成 producer cap 或 partial 业务事实。既有 cancellation、output limit、allowed paths、containment 和 process fencing 是当前风险控制。Doc 与 TruncationManager 的完整接通仍由 Issue 177 负责。

## 6. Gate decision 与 review focus

Controller validation **PASS**；未发现可直接接受的新 finding。下一 gate 是 AgentMiMo / AgentDS 并发完整 R01-S2 code review，重点挑战：

1. shared iterator 的稳定顺序、取消观察、目录异常和 symlink 行为是否与现有 owner contract 一致；
2. list 有界 heap 是否在完整观察后仍提供精确 total 与稳定前 N 项；
3. search 是否只在 `result_limit` 合法 partial，且 containment 不因 iterator 共享而漂移；
4. removed directory/source cap 是否仍通过 schema、prompt、测试或其它 production projection 泄漏；
5. 真实 smoke 是否确实经 public discovery/callable，且 output truncation/fetch_more、security 与 Issue 177 边界未被误动。

任何 accepted finding 都必须由 AgentCodex 修复并经双路完整 re-review；无 reviewer/controller acceptance 前不得提交 S2 或进入 R01 aggregate closure。
