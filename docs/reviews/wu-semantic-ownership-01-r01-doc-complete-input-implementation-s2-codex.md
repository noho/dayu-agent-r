# WU-SEMANTIC-OWNERSHIP-01 / R01-S2 Implementation — 完整目录遍历、LLM contract 收敛与真实阈值 smoke

## 1. Gate 身份、范围与结论

- **umbrella WU**：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- **内部 remediation sub-WU**：`R01 Doc complete input`；不是新 WU、Issue #177 或后续 remediation。
- **slice**：accepted-plan Slice `R01-S2`。
- **accepted plan commit**：`54e352319c7d5fd1306f1da6a6e5f4c2cb983669`（`gateflow: accept R01 doc complete input plan`）。
- **S1 accepted commit**：`1a94d798db27eee02d7acb48876027efdf36cb4b`（`gateflow: accept R01-S1 complete source snapshot`）。
- **slice base / 当前控制 HEAD**：`547c926e057d2bc78c9bb4e4d3940f87c5e94b52`（`docs: enter R01-S2 directory completeness implementation`）。
- **gate**：implementation；本 artifact 不执行 code review、fix、re-review、accepted slice commit、aggregate deepreview、R02、R03 或 Issue #177。
- **状态**：`implementation-pass / ready-for-code-review`。
- **结论**：目录 entry cap 的常量、签名、传递、docstring、counter break、list partial producer/result/schema/LLM 引导均已删除。list/search 共用一个稳定、可取消、depth-first 的目录迭代器；list 完整观察全部 entry 并以既有有界堆保存最小 output records，search 只可因合法 `result_limit` 停止。现有路径授权、symlink、取消、process-backed execution 与 read output owner 均保持原边界。
- **artifact path**：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-implementation-s2-codex.md`。

## 2. 第一性原理判断与 owner 证据

动机成立且严重性评估准确。slice base 的直接代码证据是：

1. `dayu.tools.doc_tools._route_doc_business` 把模块常量固定传给 list/search。
2. `_list_files_business` / `_search_files_business` 在 counter 命中后提前 `break`，导致未观察的 entry 永久丢失。
3. list 的 `total`、`scan_complete`、`truncated_reason` 与 list/search schema 把这一 producer cap 对外承诺为业务事实并指导模型缩小目录。

这些事实的唯一 owner 是 `dayu.tools.doc_tools` 的目录遍历、业务结果与 schema 边界；Host、Engine、provider、README 或测试夹具都不能恢复 producer 未观察的 entry。因此修复落在 owner 与 owner tests，没有新增下游 fallback、兼容 seam、替代 cap、目录 index、pagination、authorization facade 或 Issue #177 接线。

## 3. 实施内容

### 3.1 确定性目录遍历 owner

- 删除 `_DOC_DIRECTORY_MAX_ENTRIES` 与 list/search 全链 `max_directory_entries` 参数、传递和 docstring。
- 新增且只新增两个模块级私有 helper：
  - `_directory_entry_sort_key(entry)` 返回 `(entry.name.casefold(), entry.name)`；
  - `_iter_directory_entries(directory, recursive, cancellation_token)` 在每层枚举和产出时观察取消，按上述键稳定排序，并以 depth-first 顺序递归普通目录。
- iterator 产出 directory symlink entry，但以 `is_symlink()` 阻止递归其 target；file symlink 继续作为 entry 产出。
- iterator 不捕获 `OSError`，目录枚举失败沿既有错误路径透出；没有 fallback 或 loose parsing。

### 3.2 list owner

- `_list_files_business` 消费共享 iterator 并观察全部 entry；`scanned_entries` 是完整观察数，`total` 是完整匹配文件数。
- 保留 `_ListedFileCandidate` 有界反向堆，只保存最小 `actual_limit` 条记录；候选键补足 casefold、原名、relative-path casefold 与原 relative path，使大小写与同名路径 tie 仍确定。
- file symlink 继续按 symlink entry 自身的 relative path/name 和跟随 `stat()` 的 metadata 返回；未调用 search containment helper，也未增加 list per-entry containment。
- list 最终 result keys 固定为 `directory / files / total / returned / scanned_entries`；删除 list 专用 `scan_complete / truncated_reason`。
- list description 改为自足说明：`files` 是稳定顺序首批记录，`total`/`scanned_entries` 来自完整遍历，`total > returned` 只表示 output `limit` 限制本次返回数量。

### 3.3 search owner

- `_search_files_business` 消费同一 iterator；在正文读取前仍调用 `_resolve_search_files_candidate` 做 resolved containment 与 file 检查。
- 未达到 `actual_limit` 时遍历到 EOF，返回 `scan_complete=true / truncated_reason=null`；达到 limit 时合法停止并返回 `scan_complete=false / truncated_reason=result_limit`。
- search description 只解释 `result_limit` 与可执行下一步，不再包含 directory/source cap 或规避输入 cap 的指引。
- `total_matches` 继续表示当前返回命中数；没有实现 complete result continuation 或 framework remainder 接线。

### 3.4 保持不变的 owner 边界

- direct read 继续由 `_project_doc_paths` 对 canonical resolved path 做 allowed-root containment，outside file symlink 仍在输入投影边界拒绝。
- search 的 outside file symlink 仍在候选读取边界跳过；list 不统一到这两个读取授权边界。
- directory symlink 不递归只是 Python 3.11 既有遍历语义保持，不宣称为新的安全修复。
- `DocToolLimits`、参数 `limit/maximum`、read/read-section 字符输出字段、两个 `ToolTruncateSpec`、process-backed execution、父进程取消/fencing 与 provider config 均未改变。
- `TruncationManager`、remainder store、cursor/scope token 与 framework `fetch_more` 未进入 `doc_tools.py` / `doc_provider.py`。

## 4. Owner/consumer tests 与真实 smoke

### 4.1 新增/迁移的 owner tests

- list 完整观察、精确 `total/scanned_entries`、有界 output 与 list partial-only fields absence。
- 两棵内容相同但创建顺序相反的目录，list 完整 records 与 search matches 完全相同，并断言稳定次序。
- directory symlink entry 可见但 target 不递归；allowed-root 内 file symlink 仍按自身 list path/name/size 返回。
- search 未达到 limit 时扫描到 EOF；累计命中达到 limit 时仍保留 `result_limit`。
- schema exact assertions 锁定 list 完整遍历语义、search 合法 result-limit 语义与 read 字符输出事实。
- retained tests继续覆盖 allowed/outside/nonexistent/type、search symlink escape、direct read containment、list/search/read cancellation、process cancel no-late-accept 与 read char partial。

### 4.2 默认真实阈值 smoke

固定 node：

```text
test_doc_complete_input_real_smoke_above_legacy_thresholds
```

实际 fixture 与调用事实：

| 项目 | 实际值 / 断言 |
|---|---|
| 小文件 | 10,001 个真实普通 `.txt` 文件；逐文件落盘，不使用 sparse、伪 declared length 或阈值 monkeypatch |
| 大文件 | `zzzz-large-tail.txt`；34 次 1 MiB ASCII chunk + 换行 + 36-byte 尾部 marker；实际 `35,651,621 bytes`（`34.00003528594971 MiB`） |
| symlink | allowed root 内 1 个 file symlink 指向 root 外、内容含相同 marker 的普通文件 |
| 调用链 | 真实 `ToolsDiscoveryProviderSpec -> dayu.tools.doc_provider.discover_tools -> ToolDefinition.callable` |
| list | pattern 只匹配大文件；`total=1`、`returned=1`、`scanned_entries=10,003`，无 list partial-only fields |
| read | 成功；既有 output limit 返回 2,000 chars、`content_truncated=true`，`ToolTruncateSpec.target_field=content` 保留 |
| search | 尾部 marker 命中且唯一 file 是大文件；`scanned_entries=10,003`、`total_matches=1`、扫描到 EOF；outside symlink 零命中 |
| direct read | 传入 outside symlink path，由 `_project_doc_paths` 返回 `permission_denied` |

controller follow-up 后最终单独运行：`1 passed in 2.03s`；shell wall time `2.802s`（user `1.38s`，system `1.36s`）。

## 5. 文件边界与 exact diff

相对 slice base `547c926e`，semantic diff 严格限于：

1. `dayu/tools/doc_tools.py`；
2. `tests/tools/test_doc_tools_provider.py`；
3. `tests/README.md`；
4. 新增本 implementation artifact。

前三个 tracked 文件的最终 `git diff --numstat 547c926e --` 为：

```text
79  31  dayu/tools/doc_tools.py
3   3   tests/README.md
313 37  tests/tools/test_doc_tools_provider.py
```

没有 control、design、其它 production/test/README、Host、Engine、runtime、contracts、config、Fins、UI 或 Service diff。`workspace/tmp/.coverage-r01-s2` 与 `workspace/tmp/coverage-r01-s2.json` 是忽略的验证产物，不进入 git diff。

### 5.1 Controller validation follow-up：移除 formatter churn

controller 复核指出，首次 implementation validation 对两个修改 Python 文件执行整文件 `ruff format`，把 accepted S2 owner block 之外的既有代码改成纯格式差异，违反 closed slice 内仍只改 accepted finding 相关代码的约束。该 finding 成立。

本 follow-up 以 `547c926e` 为逐行基线，对普通 diff 与 ignore-whitespace diff 逐 hunk 对照，并仅用 `apply_patch` 手工恢复：

- `doc_tools.py` 的 definition builder 调用、`_sections_via_processor` 调用、`_resolve_search_files_candidate` 签名、Markdown slice、read selected/total-lines 表达式、search excerpt slice 与 response projection 等非 S2 owner block；
- provider test 的 provider-error match、既有 cancellation test 空行、limits assertions、ToolRuntime builder/calls/execution/assertions 等非 S2 test block。

恢复后，普通 diff 只剩 directory cap 删除、两个 traversal helpers、list/search owner/schema 变化、旧 contract test 迁移、新 S2 tests、README 与本 artifact。已通过的完整遍历、排序、symlink、containment、取消、真实 smoke 和 output-owner 语义没有回退。follow-up 不再运行或要求整文件 formatter clean；仓库当前 gate 只运行 `ruff check` 修改 Python 文件。

## 6. 验证结果

### 6.1 Focused / owner / coverage

```text
pytest tests/tools/test_doc_tools_provider.py -q
66 passed in 3.93s
```

```text
pytest \
  tests/tools/test_combined_tools_acceptance.py::test_combined_truncate_specs_and_fetch_more_owner \
  tests/host/test_toolruntime_effective_bundle.py::test_enabled_fetch_more_injects_schema_and_callable_when_truncation_enabled \
  tests/host/test_toolruntime_truncation_fetch_more.py::test_truncated_result_exposes_only_cursor_and_scope_token \
  tests/host/test_toolruntime_truncation_fetch_more.py::test_fetch_more_dispatches_as_normal_tool_and_is_single_use -q
4 passed in 0.93s
```

上述四节点只有三条第三方 `edgar` deprecation warnings，无测试失败。

coverage 采样：

```text
coverage run --data-file=workspace/tmp/.coverage-r01-s2 -m pytest \
  tests/documents/test_processors.py \
  tests/documents/test_import_boundary.py \
  tests/tools/test_doc_tools_provider.py -q
84 passed in 5.10s
```

| changed production file | covered / statements | exact coverage | gate |
|---|---:|---:|---|
| `dayu/tools/doc_tools.py` | 620 / 770 | 80.51948051948052% | `>=80%` pass |

coverage JSON：`workspace/tmp/coverage-r01-s2.json`；`coverage report --include='dayu/tools/doc_tools.py' --fail-under=80` exit `0`。

### 6.2 Type / lint / diff hygiene

- `python -m pyright`：`0 errors, 0 warnings, 0 informations`。
- `python -m ruff check dayu/tools/doc_tools.py tests/tools/test_doc_tools_provider.py`：pass。
- 本 follow-up 明确不运行 `ruff format` / `ruff format --check`；当前仓库未把整文件 formatter clean 设为本 gate 要求，且再次运行会重新引入 unrelated churn。
- `git diff --check 547c926e --`：exit `0`，无输出。

首次 provider run 曾有 1 个测试 fixture failure：测试在 macOS 大小写不敏感文件系统同时创建 `beta.txt` / `Beta.txt`，两者不是两条 entry，违反“两棵树内容相同”的测试前提。fixture 改用无文件系统别名的不同名称后，最终全文件与所有后续验证均通过；生产逻辑未因该失败增加平台 fallback。

## 7. 删除语义、LLM、security 与 Issue #177 scans

- `DocResourceBudget|SourceBudgetExceeded|max_source_bytes|max_directory_entries|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files` 对 `dayu tests README.md`：零命中。
- `bounded_source|BoundedSourceSnapshot|dayu-doc-bounded` 对 `dayu tests`：零命中。
- rejected LLM guidance/token scan 对 `doc_tools.py`、prompts、provider test：零命中。
- legacy numeric scan 只命中未修改的 `dayu/documents/processors/html_extraction.py:323,333` 两个 `-10_000` HTML 评分哨兵；它们不控制目录 entry、source bytes、扫描停止或 Doc tool result，故保留。
- `TruncationManager|FetchMoreToolCallable|fetch_more` 对 `doc_tools.py` / `doc_provider.py`：零命中。
- accepted-plan base 到当前对 `dayu/host dayu/runtime dayu/contracts dayu/config/tool_discovery.json`：零 diff。
- `ToolTruncateSpec|truncate=_text_content_truncate` 仍命中 read/read-section 声明与 tests，四个 ToolRuntime owner tests通过。
- `allowed_paths`、`_project_doc_paths`、`_resolve_search_files_candidate`、`_raise_if_doc_cancelled` 与 `ProcessBackedToolExecutionCapability` 仍有 owner 命中；provider 全文件 security/cancellation tests通过。

## 8. `scan_complete / truncated_reason` 生产逐命中分类

最终 `rg -n --glob '*.py' 'scan_complete|truncated_reason' dayu` 的合法命中全部位于 `dayu/tools/doc_tools.py`：

| path:line / symbol | tool | semantic owner | disposition |
|---|---|---|---|
| `doc_tools.py:161 / _BoundedTextRead.scan_complete` | read/read-section raw scan | 字符 output scan typed fact | retain |
| `doc_tools.py:791,793 / _build_search_files_definition` | search | `result_limit` LLM-facing schema | retain |
| `doc_tools.py:864,865 / _build_read_file_definition` | read | 字符 output/line-scan schema | retain |
| `doc_tools.py:936 / _build_read_file_section_definition` | read-section | 字符 output schema | retain |
| `doc_tools.py:1649,1650,1694,1695 / _search_files_business` | search | `result_limit` producer state | retain |
| `doc_tools.py:1706,1707 / _search_files_business` | search | `result_limit` result projection | retain |
| `doc_tools.py:1790 / _read_file_business` | read | 字符 output result projection | retain |
| `doc_tools.py:1858 / _read_file_section_business` | read-section | 字符 output result projection | retain |
| `doc_tools.py:2311,2336 / _read_source_with_encoding` | read | 字符 output scan producer | retain |

无 list producer、list schema、生产 consumer 或无法分类命中。provider tests 中 list 相关命中只是否定断言字段不存在；`tests/README.md` 不描述 list entry partial。

## 9. README trigger decision

| README | decision | 证据 |
|---|---|---|
| `tests/README.md` | 已更新 | 命中 tests trigger；完整读取其“README 更新边界”后，只迁移 Documents 的完整 source snapshot owner 与 Tools 的完整目录/真实 smoke owner contract，不写实现过程或未来体系 |
| `dayu/config/README.md` | 无需更新 | provider 仍只拥有 `allowed_paths` 与五个 output/argument limits，无 input cap/config 变化 |
| 根 `README.md` | 无需更新 | 安装、初始化、CLI/Web/WeChat 入口、参数、默认输出、日志、workspace 位置与用户工作流均未改变 |
| `dayu/README.md` | 无需更新 | UI/Service/Host/Engine 分层与装配关系未改变 |
| `dayu/engine/README.md` | 无需更新 | 无 Engine production/contract diff |
| `dayu/host/README.md` | 无需更新 | 无 Host production/contract diff；只运行既有 ToolRuntime owner tests |
| `dayu/fins/README.md` | 无需更新 | 无 Fins production/contract diff |

## 10. R03 LLM-facing handoff inventory

R03 必须消费下列最终 inventory，不得回改 R01 owner、重建 input cap 或把合法 output guidance 当成输入丢失语义删除。

| file / exact source | LLM-facing? | owner | disposition | final text / assertion / evidence |
|---|---|---|---|---|
| `dayu/tools/doc_tools.py / list_files ToolFunctionSchema.description` | yes | list result/schema owner | rewrite | `files` 是稳定顺序首批记录；`total` 是完整匹配数；`scanned_entries` 是完整检查数；`total > returned` 只表示 output `limit` |
| `dayu/tools/doc_tools.py / get_file_sections description` | yes | section navigation owner | retain | 先定位章节；非 null `ref` 交给 `read_file_section`，null 时用 `read_file`，不得猜 ref |
| `dayu/tools/doc_tools.py / search_files description` | yes | search result/schema owner | rewrite | 只承诺 `result_limit`；false/null 组合及下一步自解释；保留 match file/ref 到 read tool 的导航 |
| `dayu/tools/doc_tools.py / read_file description` | yes | read 字符 output owner | retain | `content/returned_chars/content_truncated/scan_complete/total_lines/line_range` 自解释，并指导按行缩小 output 范围 |
| `dayu/tools/doc_tools.py / read_file_section description` | yes | section 字符 output owner | retain | ref 来源、支持格式、字符 output partial 与 fallback 到 `read_file` 的动作保持 |
| `dayu/tools/doc_tools.py / 五工具 parameter property descriptions` | yes | 参数 schema owner | retain | directory/file path、pattern、recursive、query、include-types、line range、ref 与 `limit/maximum` 均保留；limit 仅是 output/argument contract，无 rejected input-cap token |
| `dayu/tools/doc_tools.py / _DocBusinessFailure + _invoke_doc_business projections` | yes（进入 tool failure result） | Doc error projection owner | retain S1 terminal state | 保留 `invalid_argument`、`permission_denied`、`file_not_found`、`execution_error`、cancel 的业务可行动 message/hint；无 source-budget error、拆分/较小来源引导或 Host 治理字段 |
| `dayu/tools/doc_tools.py / list result keys` | yes | list result owner | delete + retain | 最终仅 `directory/files/total/returned/scanned_entries`；删除 entry/source-only fields |
| `dayu/tools/doc_tools.py / search result keys` | yes | search result owner | retain + narrow | `query/directory/matches/total_matches/scanned_entries/scan_complete/truncated_reason`；reason 只允许 `result_limit` 或 null |
| `dayu/tools/doc_tools.py / get/read/read-section result keys` | yes | 各工具 result owner | retain | get-sections 导航字段不变；read 保留字符/行扫描字段；read-section 保留字符 partial、tables/children 与 word count |
| `dayu/config/prompts/base/tools.md:28-36` | yes | base Doc workflow guidance owner | retain / no diff | 路径 A/B 与“大文件先看章节”仅是导航/output-efficiency guidance，不声称大文件失败、跳过或目录不完整 |
| `tests/tools/test_doc_tools_provider.py / schema exact assertions + real tool-call smoke` | test LLM fixture | owner-contract tests | rewrite | exact list/search descriptions、list field absence、search/read retained fields；真实 spec/discovery/callable arguments覆盖 list/read/search、tail marker 与 containment |
| `tests/tools/test_combined_tools_acceptance.py / combined truncate/fetch-more owner test` | test schema consumer | ToolRuntime output owner test | retain / no diff | 证明 Doc/Fins/Web 暴露 `ToolTruncateSpec`，framework `fetch_more` 由 ToolRuntime 注入；不代表 Issue #177 complete wiring |
| `dayu/tools/doc_provider.py / provider config errors` | no（operator/composition） | provider config owner | retain / no diff | discovery fail-fast，不进入 model tool schema/result |
| `dayu/config/tool_discovery.json:48-62` | no（ConfigLoader/provider input） | raw provider config owner | retain / no diff | `allowed_paths` + 五个 output/argument limits 保持，未新增 input cap |
| `dayu/config/README.md / tests/README.md / README.md` | no（开发/用户文档） | 各 README 写作 owner | tests rewrite, others retain | tests 只记录现有 owner tests；开发文档不作为 runtime LLM source |

扫描未发现 allowlist 外的新 Doc LLM-facing source。

## 11. Residual risks 与未覆盖项

| residual / uncovered area | classification | owner / destination |
|---|---|---|
| 极大 source/目录可能增加磁盘、时间与 inode 消耗 | `assigned to later work unit` | 后续 input-governance 设计；R01 按 accepted contract 保留完整 spool、process boundary 与 cancellation，不恢复未经裁决 hard-fail |
| 五工具 output/remainder 尚未全部通过 `TruncationManager` 无损续读 | `tracked by existing issue` | GitHub Issue #177；本 slice 仅保留既有 `ToolTruncateSpec` / framework owner |
| search 达到合法 result limit 后不扫描剩余 entry，`total_matches` 仍只是返回命中数 | `tracked by existing issue` | GitHub Issue #177 若未来形成 complete target + continuation contract |
| symlink/TOCTOU 仍是既有三条局部边界，不是统一 authorization contract | `assigned to later work unit` | 独立 filesystem/tool authorization hardening WU，仅在有直接证据时立项 |

没有未分类 residual risk、blocking open question、allowlist 扩张或 accepted contract 偏离。

## 12. Completion signal 与下一入口

R01-S2 implementation 已满足：directory cap 全链删除、共享 deterministic cancellable iterator、list 完整事实、search 合法 EOF/result-limit 状态、symlink owner 保持、真实阈值 smoke、provider/ToolRuntime/security/cancellation tests、单文件 coverage、full pyright、scoped ruff、diff/semantic/LLM/Issue #177 scans、README decision与 R03 inventory 均完成。

**下一入口只有 R01-S2 code review。** AgentCodex 在此停止，不进入 code review、fix、re-review、commit、aggregate deepreview、R02、R03、Issue #177、push 或 PR。
