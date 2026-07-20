# WU-SEMANTIC-OWNERSHIP-01 R01 Doc Complete Input Plan Review — MiMo

## Reviewed Target

- **Plan**: `docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`
- **Scope**: R01 sub-WU 的独立 code-generation-ready plan review，覆盖 root cause、umbrella baseline 映射、production/test/doc allowlist、SourceSnapshot contract、ToolRuntime truncation/fetch_more 与 Issue 177 边界、>32 MiB/>10k smoke、coverage/pyright/scans、README/R03 handoff、安全保留。
- **Plan-time HEAD**: `edc6ea62`，分支 `phaseflow/host-issues-control`
- **Accepted umbrella base**: `227317a0`
- **Review timestamp**: 20260714-174946

## Assumptions Tested

1. `DocResourceBudget` 同时携带 source byte 和 directory entry 两类 cap，S1 删除后暂时直接传目录 cap 是合理的 slice 边界。
2. list 的 `scan_complete`/`truncated_reason` 只为 10,000 entry partial 存在，无真实生产消费者。
3. deterministic iterator 不跟随目录 symlink 同时保持 file symlink resolve/containment 行为。
4. >32 MiB/>10k smoke 是必要的真实验证，不是过度规格。
5. 所有 accepted contract 足够具体，可直接交给 implementation agent。

## Findings

### 01-未修复-低-S1 暂传目录 cap 的函数签名 churn 风险

- **位置**: §8.1、§8.2、§9.2
- **问题类型**: 切片过粗 / 最佳实践偏离
- **当前写法**: S1 删除 `DocResourceBudget`，`_route_doc_business` 暂时直接传 `_DOC_DIRECTORY_MAX_ENTRIES` 给 `_list_files_business`/`_search_files_business`；S2 再删除该常量和参数。
- **反例/失败场景**: `_list_files_business` 和 `_search_files_business` 的签名在 S1 删除 `resource_budget` 并改为直接传 `max_directory_entries`，S2 再删除 `max_directory_entries`。同一模块的同一组函数被两个 slice 连续修改签名，implementation agent 需要两次理解、两次修改、两次测试。
- **为什么有问题**: 这不是语义风险（S1 不改变目录 cap 行为），但增加了 implementation 成本和出错概率。如果 S1 的签名变更不干净（例如遗留 `resource_budget` 参数或引入临时 wrapper），S2 需要额外清理。
- **直接证据**:
  - `doc_tools.py:1501-1510` — `_list_files_business` 接受 `max_directory_entries: int` 参数
  - `doc_tools.py:1646-1667` — `_search_files_business` 接受 `max_source_bytes: int` 和 `max_directory_entries: int`
  - `doc_tools.py:1218` — `_route_doc_business` 接受 `resource_budget: DocResourceBudget` 并解构传给上述函数
  - §8.2 第 5 点 — `_route_doc_business` 在 S1 暂时直接传 `_DOC_DIRECTORY_MAX_ENTRIES`
- **影响**: implementation agent 需要两次修改同一函数签名，增加出错概率；但不影响语义正确性。
- **建议改法和验证点**: 在 plan 中明确标注 S1→S2 的签名变更预期：S1 删除 `resource_budget` 参数、新增 `max_directory_entries` 参数；S2 删除 `max_directory_entries` 参数。Implementation agent 应在 S1 完成后验证 S2 的 diff 只删除常量和参数，不引入新抽象。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未通过-list scan_complete/truncated_reason 无生产消费者遗漏

- **位置**: §3.2、§4.1、§9.2
- **问题类型**: 契约缺失验证
- **当前写法**: plan 声称 list 的 `scan_complete`/`truncated_reason` "只为 10,000 partial 存在"，删除后 "避免保留永远为 true/null 的死 contract"。
- **反例/失败场景**: 如果存在外部 API 消费者（例如 CLI、Web UI、第三方集成）解析这些字段，删除会破坏兼容性。
- **为什么有问题**: plan 的 §16.3 承认 "implementation 前必须再跑同一 source scan 确认"，但未在 §12 的 scan 命令中明确列出对 list `scan_complete`/`truncated_reason` 的专项检查。
- **直接证据**:
  - `grep -rn 'scan_complete\|truncated_reason' dayu/ --include='*.py' | grep -v 'doc_tools.py'` — 零命中（生产代码无消费者）
  - `tests/tools/test_doc_tools_provider.py:450,842,844,894,895,921,948,994,1022,1076,1077,1105,1106,1133,1134` — 仅测试断言
  - `tests/README.md:175` — 文档引用
  - `dayu/config/` — 零命中
- **影响**: 当前证据支持删除安全性。但 plan 应在 §12 的 scan 命令中明确包含对 list 专有字段的检查，而非仅依赖 §16.3 的 "必须再跑"。
- **建议改法和验证点**: 在 §12.2 的 scan 命令中增加一条针对 list 专有字段的检查：
  ```bash
  rg -n 'scan_complete|truncated_reason' dayu/tools/doc_tools.py tests/tools/test_doc_tools_provider.py
  ```
  预期只命中 search 路径的 `scan_complete`/`truncated_reason`（result_limit 场景），不命中 list 路径。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 03-未修复-中-deterministic iterator 对 list_files symlink containment 语义未明确

- **位置**: §3.2、§9.2
- **问题类型**: 契约缺失
- **当前写法**: plan 描述 deterministic iterator "不递归跟随目录 symlink"、"每个 entry 前观察 cancellation"、"不吞掉现有 I/O error"。§3.2 说 search "仍经 resolved containment/file 检查"。但未明确 list_files 是否对 symlinked file 做 containment 检查。
- **反例/失败场景**: 当前 `_list_files_business` 使用 `rglob("*")`/`iterdir()` + `is_file()` 遍历，**不检查** symlinked file 是否在 allowed root 内（`doc_tools.py:1540-1548`）。如果 allowed root 内有一个 symlink 指向 root 外的文件，当前 list 会返回该文件。Plan 的 deterministic iterator 如果不明确这一点，implementation agent 可能添加或遗漏 containment 检查，导致行为变更或安全缺口。
- **为什么有问题**:
  - `search_files` 通过 `_resolve_search_files_candidate` 检查 resolved path containment（`doc_tools.py:1760-1784`）
  - `list_files` 当前**不做**此检查（`doc_tools.py:1540-1548`）
  - Plan §3.2 说 list "对授权目录按确定顺序遍历全部相关 entry"，但 "相关" 的定义不明确
  - Plan §9.2 说 search "保留 candidate resolved containment"，但未提 list
  - §10 的 regression matrix 只列 "allowed_paths/containment" 测试，未区分 list 和 search
- **直接证据**:
  - `doc_tools.py:1540-1548` — list 遍历不做 containment 检查
  - `doc_tools.py:1697-1703` — search 通过 `_resolve_search_files_candidate` 做 containment 检查
  - `doc_tools.py:1760-1784` — `_resolve_search_files_candidate` 检查 resolved path 是否在 allowed root 内
  - §3.2 — "search 仍在读取前调用 `_resolve_search_files_candidate` 重新 resolve/containment"（未提 list）
- **影响**: 如果 implementation agent 对 list 也添加 containment 检查，行为会变更（symlinked files outside root 不再返回），可能破坏现有消费者。如果不添加，list 和 search 的安全语义不一致。Plan 应明确选择并记录理由。
- **建议改法和验证点**:
  1. 在 §3.2 中明确 list_files 对 symlinked file 的 containment 语义：(a) 保持当前行为（不检查 containment，因为 list 只展示目录结构，不读取文件内容），或 (b) 与 search 对齐（检查 resolved path containment）。
  2. 如果选择 (a)，在 §10 的 regression matrix 中明确标注 "list 不检查 symlinked file containment，这是设计选择而非遗漏"。
  3. 如果选择 (b)，在 §4.1 的 "必须删除" 中不包含此行为，并在 §9.2 的 production 改动中明确添加。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### 04-未通过-deterministic iterator 缺少明确函数签名和模块位置

- **位置**: §3.2、§9.2
- **问题类型**: 不可直接实施
- **当前写法**: plan 描述 deterministic iterator 的行为（排序规则、递归策略、symlink 处理、cancellation 观察、I/O error 处理），但未指定函数名、签名、模块位置或返回类型。
- **反例/失败场景**: implementation agent 需要自行决定：(a) 函数名是 `_iter_directory_entries` 还是 `_stable_directory_iterator` 还是其它；(b) 返回 `Iterator[Path]` 还是 `Iterator[tuple[Path, os.DirEntry]]` 还是其它；(c) 放在 `doc_tools.py` 顶部还是单独模块；(d) sort key helper 是内联还是独立函数。这些决定会影响后续代码结构和测试方式。
- **为什么有问题**: plan 声称是 "code-generation-ready"，但 deterministic iterator 是 R01-S2 的核心新增代码，其签名和位置是 implementation agent 必须做出的设计决定。如果 agent 的选择与 plan 的隐式假设不一致，可能导致后续修改。
- **直接证据**:
  - §3.2 — "deterministic traversal 使用模块级私有 helper，而不是复制 list/search 两套规则"
  - §9.2 第 2 点 — "新增模块级私有 deterministic iterator + sort-key helper，供 list/search 共用"
  - 未指定函数名、参数类型、返回类型或模块位置
- **影响**: implementation agent 需要做设计决定，增加出错概率；但行为规格足够明确，不会导致语义错误。
- **建议改法和验证点**: 在 §9.2 中添加最小函数签名草案：
  ```python
  def _iter_directory_entries(
      root: Path,
      *,
      recursive: bool,
      cancellation_check: Callable[[], None] | None,
  ) -> Iterator[Path]:
      """按确定顺序遍历目录 entry，不跟随目录 symlink。"""
  ```
  以及 sort-key helper：
  ```python
  def _entry_sort_key(path: Path) -> tuple[str, str]:
      """返回 (name.casefold(), name) 用于稳定排序。"""
  ```
  明确放在 `doc_tools.py` 模块顶部作为私有函数。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 05-未通过-smoke test 10,001 文件创建的时间和磁盘成本

- **位置**: §11
- **问题类型**: 过度设计
- **当前写法**: smoke test 在 `tmp_path/allowed` 创建 10,001 个小 `.txt` 文件和一个 >33 MiB 的 `zzzz-large-tail.txt`。
- **反例/失败场景**: 在 CI 环境或磁盘较慢的开发机上，创建 10,001 个文件可能需要 10-30 秒（每个文件需要 open/write/close syscall）。加上 33 MiB 文件的写入和后续的 discovery→callable→list→read→search 调用，整个 smoke 可能需要 60-120 秒。这会显著拖慢 CI pipeline。
- **为什么有问题**: plan 声称 "若真实文件系统无法在合理测试环境创建这些输入，R01 blocked，不能把阈值缩小或 monkeypatch 旧常量后宣称真实 smoke"。这个立场是正确的（必须验证真实行为），但未讨论时间成本的可接受范围。
- **直接证据**:
  - §11 — "在 `tmp_path/allowed` 创建 10,001 个按稳定名称排序的小 `.txt` 文件；按 1 MiB ASCII chunk 循环写一个大于 33 MiB 的 `zzzz-large-tail.txt`"
  - §11 — "若真实文件系统无法在合理测试环境创建这些输入，R01 blocked"
- **影响**: CI 时间增加，但不影响正确性。如果 CI 有 timeout 限制，可能需要调整。
- **建议改法和验证点**: 在 §11 中添加时间成本预期和 CI 适配建议：
  1. 预期 smoke 运行时间 60-120 秒（取决于磁盘速度）。
  2. 如果 CI 有 per-test timeout，应在 pytest 配置中为该 node 设置合理 timeout（例如 180 秒）。
  3. 文件创建可以并行化（使用 `concurrent.futures.ThreadPoolExecutor`），但 plan 不要求此优化。
  4. 标记为 `@pytest.mark.slow` 以便 CI 可选择性跳过（但 R01 completion 必须运行）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 06-未通过-SourceSnapshot contract 部分条款重复已有实现

- **位置**: §3.1
- **问题类型**: 过度规格
- **当前写法**: §3.1 的 SourceSnapshot contract 包含 10 个条款，其中 "metadata"（content_length 行为）、"状态"（new→active→closed）、"读取"（独立 cursor）、"物化"（单路径复用）、"close"（幂等）等条款描述的行为与当前 `BoundedSourceSnapshot` 完全一致。
- **反例/失败场景**: 无。这些条款是准确的，但 implementation agent 可能误以为它们描述的是新行为而非保留行为。
- **为什么有问题**: plan 的 §4.2 "必须保留" 已经列出了这些行为。§3.1 重复描述不会导致错误，但增加了 plan 长度和阅读负担。更重要的是，如果 implementation agent 只看 §3.1 而不看 §4.2，可能认为所有条款都是新增要求。
- **直接证据**:
  - `bounded_source.py:244-246` — `content_length` 已实现 "进入前返回声明值，active 后返回精确值"
  - `bounded_source.py:276-321` — `__enter__` 已实现 "只调用一次，复制到 SpooledTemporaryFile"
  - `bounded_source.py:346-357` — `open()` 已实现 "独立只读 cursor"
  - `bounded_source.py:359-399` — `materialize()` 已实现 "单路径复用"
  - `bounded_source.py:401-425` — `close()` 已实现 "幂等"
  - §3.1 — 上述行为被重新描述为 contract 条款
- **影响**: 无语义风险。增加 plan 阅读负担，但不影响 code-generation-ready 性。
- **建议改法和验证点**: 在 §3.1 中明确区分 "保留行为" 和 "新增/变更行为"。例如：
  - 条款前标注 `[保留]` 或 `[新增]`/`[变更]`
  - 或在条款后引用当前实现位置（如 "当前实现：`bounded_source.py:244-246`"）
  这样 implementation agent 可以快速识别哪些需要新写、哪些需要保留。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 07-未通过-S1 scan 命令未覆盖 list search 路径的残留

- **位置**: §8.5
- **问题类型**: 测试缺口
- **当前写法**: S1 的 scan 命令是：
  ```bash
  rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|source_budget_exceeded|skipped_oversized_files|source_limit' dayu tests README.md
  rg -n 'bounded_source|BoundedSourceSnapshot|dayu-doc-bounded' dayu tests
  ```
- **反例/失败场景**: S1 删除 source byte 相关代码，但 search 路径的 `skipped_oversized_files` 和 `source_limit` 可能在 S1 未完全清理（例如 search 的 description 或 result 字段仍引用这些值）。如果 S1 的 scan 不覆盖这些，残留可能被带到 S2。
- **为什么有问题**: §8.2 第 9 点说 "search 删除 oversized catch、counter、`skipped_oversized_files`、`source_limit`；保留 `result_limit`/directory cap 到 S2"。这意味着 S1 应该删除 search 的 `skipped_oversized_files` 和 `source_limit`。S1 的 scan 命令确实包含 `skipped_oversized_files|source_limit`，所以应该能捕获。但 scan 未包含 `directory_entry_limit`（这是 S2 的目标），这是正确的。
- **直接证据**:
  - §8.5 — scan 命令包含 `skipped_oversized_files|source_limit`
  - §8.2 第 9 点 — S1 删除 search 的 `skipped_oversized_files` 和 `source_limit`
  - §12.2 — S2 的 scan 命令包含 `directory_entry_limit`
- **影响**: 实际上 S1 的 scan 命令是正确的。此 finding 经过验证后不成立。
- **建议改法和验证点**: 无需修改。S1 scan 覆盖了 source-byte 相关残留，S2 scan 覆盖了 directory-entry 相关残留。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（经验证不成立）

### 08-未通过-search_files 在 S1 保留 directory_entry_limit 的中间状态

- **位置**: §8.2 第 9 点
- **问题类型**: 状态机漏洞
- **当前写法**: S1 删除 search 的 `source_limit`/`skipped_oversized_files`，但保留 `directory_entry_limit`。这意味着 S1 的 search 结果可能同时包含 `truncated_reason=result_limit`（合法）和 `truncated_reason=directory_entry_limit`（将被 S2 删除）。
- **反例/失败场景**: 如果 S1 的测试断言 search 结果不含 `source_limit` 但允许 `directory_entry_limit`，这个中间状态是安全的。但如果 S1 的 scan 命令（§8.5）扫描 `source_limit` 残留时误命中 `directory_entry_limit`（因为二者都包含 "limit"），可能导致误报。
- **为什么有问题**: 实际上 S1 的 scan 命令使用精确匹配 `source_limit`，不会误命中 `directory_entry_limit`。此 finding 经过验证后不成立。
- **直接证据**:
  - §8.5 — `rg -n '...|source_limit'` 使用精确匹配
  - `grep 'source_limit'` 不会匹配 `directory_entry_limit`
- **影响**: 无。S1 的 scan 命令是正确的。
- **建议改法和验证点**: 无需修改。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（经验证不成立）

## Open Questions

### OQ-1: list_files 对 symlinked file 的 containment 策略

Plan 未明确 list_files 是否对 symlinked file 做 resolved path containment 检查。当前实现不做此检查（`doc_tools.py:1540-1548`），search 做此检查（`doc_tools.py:1697-1703`）。Plan 应明确选择并记录理由。

**Blocking?**: 是。Implementation agent 需要知道 list 是否添加 containment 检查，否则可能做出与 plan 隐式假设不一致的决定。

### OQ-2: deterministic iterator 的 sort key 是否区分大小写

Plan 说 "按每层 entry 的 `(name.casefold(), name)` 稳定排序"。这意味着 `A.txt` 和 `a.txt` 的 casefold 值相同，排序由原始 name 决定。但 plan 未说明当 casefold 相同时的 tie-breaking 规则。当前实现使用 `(file_path.name.lower(), relative_path.lower())`（`doc_tools.py:1562`），其中 `relative_path` 包含目录结构，可以区分同名文件。Plan 的 `(name.casefold(), name)` 只使用文件名，不包含路径，可能在递归场景下产生不稳定排序。

**Blocking?**: 否。Implementation agent 可以自行决定 tie-breaking 规则，但 plan 应明确意图。

### OQ-3: SourceSnapshot 的 `_SPOOL_MEMORY_BYTES` 是否需要可配置

Plan 说 "`_SPOOL_MEMORY_BYTES` 只决定内存转磁盘阈值，是内部性能细节，不是可见输入 cap"。当前值为 1 MiB（`bounded_source.py:22`）。如果某些部署环境内存受限，可能需要调整此值。

**Blocking?**: 否。Plan 明确将其定位为内部细节，不要求可配置。Implementation agent 按当前值实现即可。

## Residual Risks

| Risk | 当前处理 | Owner/Destination |
|---|---|---|
| 极大 source/目录可能消耗磁盘、时间或 inode | 完整 spool、process boundary、cooperative/parent cancellation 与 output limit | Issue #177 / 后续输入治理设计 |
| 五工具 output/remainder 没有全部通过 TruncationManager 无损续读 | 保留 current spec/framework owner，不扩张 R01 | GitHub Issue #177 |
| symlink/TOCTOU 是既有局部防御边界 | 保留 resolved containment、candidate recheck 与 process boundary | 后续独立 tool authorization/filesystem hardening WU |
| deterministic iterator 不跟随目录 symlink 可能改变现有行为 | 当前 rglob 跟随 symlink，新 iterator 不跟随 | 需在 §10 regression matrix 中明确标注行为变更 |

## Final Plan Review Conclusion

**Pass with conditions.**

Plan 整体质量高：root cause 分析准确、umbrella baseline 映射完整、production allowlist 闭集明确、SourceSnapshot contract 详细、Issue 177 边界清晰、验证矩阵全面。五个重点 adversarial 问题的结论：

1. **S1 暂传目录 cap**: 合理的 2-slice 设计，不是无必要过渡设计。函数签名 churn 是真实成本但可管理。
2. **list scan_complete/truncated_reason**: 无生产消费者遗漏，删除安全。Plan 应在 §12 scan 中明确覆盖。
3. **stable iterator**: 行为规格基本准确，但 list_files 的 symlink containment 语义需要明确（OQ-1 是 blocking question）。
4. **过度固定 contract/smoke**: SourceSnapshot contract 部分条款重复已有实现（低严重度），smoke 时间成本应预期。
5. **code-generation-ready**: 绝大部分 contract 是 code-generation-ready，deterministic iterator 缺少函数签名（可推断但应明确）。

**Blocking items**:
- OQ-1: list_files symlink containment 策略必须在 plan 中明确。

**Non-blocking improvements**:
- §3.1 区分保留行为和新增行为
- §9.2 添加 deterministic iterator 最小函数签名
- §11 添加 smoke 时间成本预期
- §12.2 增加 list 专有字段 scan
