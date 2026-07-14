# WU-SEMANTIC-OWNERSHIP-01 / R01 Doc Complete Input Plan Fix 后第一路完整 Re-Review — MiMo

## 审查身份

- **审查类型**：plan fix 后第一路完整 adversarial re-review
- **审查 target**：修后 plan `docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`
- **审查 base**：plan fix artifact `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-fix-codex.md`
- **审查范围**：修后 plan 全文 + controller adjudication 四项 accepted finding + 全部 rejected/no-fix 项 + 当前 `doc_tools.py` / `bounded_source.py` / Python 3.11 行为直接证据
- **审查时间**：2026-07-14 18:09:31 +0800（本机系统时钟）

## 0. Assumptions Tested

| # | assumption | verdict | 证据 |
|---|-----------|---------|------|
| A1 | R01-PF-01 symlink 边界文本与 Python 3.11 真实行为一致 | **通过** | 见 §1.1 |
| A2 | R01-PF-02 S1→S2 临时签名无 wrapper/校验/budget seam | **通过** | 见 §1.2 |
| A3 | R01-PF-03 list partial-only 分类 scan 可执行且不误删 | **通过** | 见 §1.3 |
| A4 | R01-PF-04 SourceSnapshot 调用链消歧 | **通过** | 见 §1.4 |
| A5 | controller rejected/no-fix 项未被误实现 | **通过** | 见 §1.5 |
| A6 | umbrella mandatory baseline/allowlist 未弱化 | **通过** | 见 §1.6 |

## 1. 逐项验证

### 1.1 R01-PF-01 — symlink owner 边界闭合验证

**controller 要求**：明确 Python 3.11 `rglob` 不递归跟随目录 symlink、list file-symlink 保持 directory-entry 语义、search/direct-read 分别在不同边界 resolve/containment、三者不包装成统一权限 contract。

**修后 plan 文本证据（现 §3.2，plan 第 100 行）**：

> Python 3.11 当前 `Path.rglob("*")` 会产出 file/directory symlink entry，但不会递归进入 directory-symlink target；新 helper 必须保持这一现状，不得把"不递归"描述或实现成 R01 新安全修复。helper 按每层 entry 的 `(name.casefold(), name)` 稳定排序、递归时保持稳定 depth-first 顺序、每个 entry 前观察 cancellation。search 仍在实际内容读取前调用 `_resolve_search_files_candidate` 重新 resolve/containment；direct read 仍在 `_project_doc_paths` 对输入路径 canonical resolve/containment 后才读取。三者是不同 owner boundary，不得包装成统一权限 contract。

**修后 plan 文本证据（现 §3.2，plan 第 93 行）**：

> `list_files` 的 file-symlink owner 保持当前 directory-entry 语义：遍历 entry 的 `is_file()` 成立时，继续按 symlink entry 的相对路径/名称和 `stat()` metadata 形成记录；list 不读取文件正文，不调用 `_resolve_search_files_candidate`，也不新增 per-entry resolved containment 或新的 symlink/authorization policy。

**Python 3.11.15 直接实测**：

```text
rglob("*") entries: external, external/nested, external/nested/deep.txt, external/outside.txt, linked-dir, normal.txt
Children under linked-dir/: []  (零个——不递归)
os.scandir: linked-dir is_dir(follow_symlinks=False)=False, is_symlink=True
```

**当前代码直接证据**：

- `doc_tools.py:1540` — `_list_files_business` 使用 `dir_path.rglob("*")`，对 file symlink 调用 `is_file()` 返回 True，`stat()` 读取 target metadata（第 1552 行），不调用 `_resolve_search_files_candidate`，无 per-entry containment。
- `doc_tools.py:1699-1703` — `_search_files_business` 在读取前调用 `_resolve_search_files_candidate`（第 1760-1784 行），resolve 后重新做 allowed-root containment 与 file 检查。
- `doc_tools.py:1426-1431` — `_project_doc_paths` 对输入路径做 `Path(value).expanduser().resolve(strict=False)` + containment check，外部 target 被拒绝。

**修后验证 contract（现 §9.4、§10、§11）**：

- directory symlink entry 不被递归；
- allowed-root 内 file symlink 保持 list entry 行为；
- outside file symlink 由 search candidate containment 跳过、由 direct read 输入投影拒绝；
- smoke 明确只证明 search/direct-read 的内容读取边界，不给 list 新增 per-entry containment。

**闭合判断**：**R01-PF-01 已闭合。** Python 3.11 真实行为、当前代码事实与修后 plan 文本三者一致。三条不同 owner 边界已明确冻结，未新增 list containment 或统一权限设计。

---

### 1.2 R01-PF-02 — S1→S2 临时签名闭合验证

**controller 要求**：S1 删除 `resource_budget`、只把既有 `_DOC_DIRECTORY_MAX_ENTRIES: int` 直接传给 list/search；S2 删除该参数与常量。中间态不新增校验 helper、wrapper、budget 类型、配置或 public contract。

**修后 plan 文本证据（现 §8.1，plan 第 264 行）**：

> 删除 `DocResourceBudget` 及 process target/factory/builder/definition、`_execute_doc_business_value`、`_route_doc_business` 全链的 `resource_budget` 参数；`_route_doc_business` 不接收替代 budget 参数，只在 list/search 分支把既有模块常量 `_DOC_DIRECTORY_MAX_ENTRIES: int` 直接传给两个业务函数原有的 `max_directory_entries: int` 参数。S2 随后同时删除该常量和这两个参数。中间态不得新增正整数 assertion/校验 helper、wrapper、dataclass 或其它 budget 类型、配置、optional 参数、alias、兼容逻辑或 public contract。

**修后 S2 终点证据（现 §9.2，plan 第 356 行）**：

> 删除 `_DOC_DIRECTORY_MAX_ENTRIES`、`_list_files_business` / `_search_files_business` 的 `max_directory_entries: int` 参数及对应 docstring/传递与 counter break；不保留 S1 过渡参数或新增替代抽象。

**当前代码直接证据**：

- `doc_tools.py:1218-1224` — `_route_doc_business` 接收 `resource_budget: DocResourceBudget` 参数。
- `doc_tools.py:1254` — `_list_files_business` 接收 `max_directory_entries=resource_budget.max_directory_entries`。
- `doc_tools.py:1273` — `_search_files_business` 接收 `max_directory_entries=resource_budget.max_directory_entries`。
- `doc_tools.py:1508` — `_list_files_business` 参数 `max_directory_entries: int`。
- `doc_tools.py:1654` — `_search_files_business` 参数 `max_directory_entries: int`。
- `doc_tools.py:87-88` — `_DOC_DIRECTORY_MAX_ENTRIES: Final[int] = 10_000`。

**签名过渡路径验证**：

| 阶段 | `_route_doc_business` | `_list_files_business` / `_search_files_business` |
|------|----------------------|--------------------------------------------------|
| 当前 | `resource_budget: DocResourceBudget` | `max_source_bytes: int, max_directory_entries: int` |
| S1 后 | 删除 `resource_budget`，直接传 `_DOC_DIRECTORY_MAX_ENTRIES` 给 `max_directory_entries` | 删除 `max_source_bytes`，保留 `max_directory_entries: int` |
| S2 后 | 同 S1 | 删除 `max_directory_entries: int` |

**闭合判断**：**R01-PF-02 已闭合。** S1→S2 的签名变化路径、唯一传值路径和删除顺序已封闭。没有新增 wrapper、校验 helper、budget 类型、配置或兼容 seam。controller rejected 的临时正整数 assert 未被采纳。

---

### 1.3 R01-PF-03 — list partial-only 字段分类 scan 闭合验证

**controller 要求**：增加可执行的生产范围 scan，并要求逐命中区分 list 专属字段与 read/search 的合法同名字段；最终必须证明 list producer、生产消费者、schema/assertion 与 README 中没有残留的 directory-partial 语义。

**修后 plan 文本证据（新增 §12.2.1，plan 第 498-509 行）**：

```bash
rg -n --glob '*.py' 'scan_complete|truncated_reason' dayu

rg -n 'scan_complete|truncated_reason|directory_entry_limit' \
  tests/tools/test_doc_tools_provider.py tests/README.md
```

> 第一条允许命中且必须在 S2 implementation/completion artifact 逐项记录 `path:line / symbol / tool / semantic owner / disposition`。合法分类只有 search 的 `result_limit` schema/result producer 与 read/read-section 的字符输出 schema/result producer；若出现 list producer、list schema description、读取 list 字段的任何生产 consumer，或无法判定 owner 的命中，立即 stop。第二条中 list 相关测试只允许"字段不存在"的 negative assertion，不得保留 partial 值/reason assertion；`tests/README.md` 的 list contract 不得再描述这两个字段或 directory partial。结合 §12.2 第一条 semantic identifier 零命中，最终必须证明 list producer、生产 consumer、schema/test assertion 与 README 均无 `directory_entry_limit` 或 list entry-partial 残留，同时不误删 search/read 的合法同名字段。

**当前代码 `scan_complete` / `truncated_reason` 逐行分类验证**：

| 行号 | symbol | tool | semantic owner | disposition |
|------|--------|------|---------------|-------------|
| 201 | `_BoundedTextRead.scan_complete` | read/read-section | 字符输出截断 | **保留**（plan §4.2） |
| 702-704 | `list_files` description | list | directory entry partial | **删除**（plan §4.1） |
| 851-852 | `search_files` description | search | result_limit + directory_entry_limit + source_limit | **部分删除**：删除 `directory_entry_limit`/`source_limit`，保留 `result_limit` |
| 926-927 | `get_file_sections` description | get-sections | 字符输出截断 | **保留** |
| 1001 | `read_file` description | read | 字符输出截断 | **保留** |
| 1538-1585 | `_list_files_business` result | list | directory entry partial | **删除**（plan §4.1） |
| 1687-1756 | `_search_files_business` result | search | result_limit + directory_entry_limit + source_limit | **部分删除**：删除 `directory_entry_limit`/`source_limit`，保留 `result_limit` |
| 1841 | `_get_file_sections_business` result | get-sections | 字符输出截断 | **保留** |
| 1911 | `_read_file_section_business` result | read-section | 字符输出截断 | **保留** |

**分类结论**：

- list producer（第 702-704、1538-1585 行）的 `scan_complete`/`truncated_reason` + `directory_entry_limit` 语义将被删除。
- search producer（第 851-852、1687-1756 行）的 `result_limit` 语义保留，`directory_entry_limit`/`source_limit` 语义删除。
- read/read-section producer（第 201、926-927、1001、1841、1911 行）的字符输出截断语义保留。
- 生产代码中没有读取 list 返回值 `scan_complete`/`truncated_reason` 的 consumer（只有 `doc_tools.py` 自身 producer 和 test consumer）。

**闭合判断**：**R01-PF-03 已闭合。** 生产范围 scan 覆盖完整 `dayu` 包，逐命中分类规则明确，合法 owner 定义精确，stop 条件完备。不会误删 search/read 的合法同名字段。

---

### 1.4 R01-PF-04 — SourceSnapshot 调用链消歧验证

**controller 要求**：把含混的 `_source_snapshot -> SourceSnapshot` 改成函数、输入和 context-manager class 可区分的调用链。

**修前文本（原 §5.2）**：

> `get/read/search/section: _source_snapshot -> SourceSnapshot -> processor/raw reader`

**修后文本（现 §5.2，plan 第 191-194 行）**：

```text
get/read/search/section:
  with _source_snapshot(path, cancellation_token) as snapshot
    (_source_snapshot helper: LocalFileSource input -> unentered SourceSnapshot context-manager instance)
  -> active snapshot -> processor/raw reader
```

**当前代码直接证据**：

- `doc_tools.py:1919-1943` — `_bounded_local_source` 是当前对应函数，接收 `path: Path`、`max_source_bytes: int`、`cancellation_token: CancellationToken`，构造 `LocalFileSource(path=path, uri=str(path))` 并返回 `BoundedSourceSnapshot(source, max_source_bytes, _DocSourceCancellationCheck(cancellation_token))`。
- plan 将 `_bounded_local_source` 重命名为 `_source_snapshot`，删除 `max_source_bytes` 参数，保留 `LocalFileSource` 输入构造和 `SourceSnapshot` context-manager 返回。

**闭合判断**：**R01-PF-04 已闭合。** 调用链现在分别标明 helper function（`_source_snapshot`）、`LocalFileSource` 输入、未进入的 `SourceSnapshot` context-manager instance 与 active snapshot consumer，不再把 helper/type 写成同一层符号。

---

### 1.5 Controller rejected / no-fix 项未误实现验证

| rejected / no-fix 项 | 修后 plan disposition | 验证 |
|---|---|---|
| 给 list 新增 resolved containment | plan §3.2 明确禁止："list 不读取文件正文，不调用 `_resolve_search_files_candidate`，也不新增 per-entry resolved containment 或新的 symlink/authorization policy" | **未实施** |
| 把"不递归 directory symlink"写成新安全修复 | plan §3.2 明确："不得把'不递归'描述或实现成 R01 新安全修复" | **未实施** |
| 给固定 `_DOC_DIRECTORY_MAX_ENTRIES: int` 新增正整数 assert | plan §8.1 明确禁止："中间态不得新增正整数 assertion/校验 helper" | **未实施** |
| 固定 iterator 私有函数名/签名/API | plan 只保留行为 contract（§3.2、§9.2），未指定函数名、参数类型或返回类型 | **未实施** |
| 给 smoke 增加 `slow` skip/timeout/并行/预估时长 | plan §11 保持原文，未新增性能建议或 skip 标记 | **未实施** |
| 给 SourceSnapshot 每条 contract 标注"保留/新增" | plan §3.1 保持原文 | **未实施** |
| spool memory threshold 配置化 | plan §3.1 明确 "`_SPOOL_MEMORY_BYTES` 只决定内存转磁盘阈值，是内部性能细节，不是可见输入 cap" | **未实施** |

**闭合判断**：全部 rejected/no-fix 项均未被 plan 意外引入。

---

### 1.6 Umbrella mandatory baseline / allowlist 未弱化验证

| baseline 项 | 修后 plan 状态 | 验证 |
|---|---|---|
| Issue #177 non-implementation | plan §0 第 20 行、§3.4 第 118 行、§4.3 第 146 行明确排除 | **未弱化** |
| R01 production allowlist | plan §6.1 保持完整闭集 6 文件 | **未弱化** |
| security/cancellation tests | plan §10 regression matrix + §12.5 scan | **未弱化** |
| smoke 真实阈值 | plan §11 保持 >32 MiB / >10k 真实文件系统验证 | **未弱化** |
| coverage ≥80% per changed file | plan §8.5、§9.5、§14.2 保持逐文件 `--fail-under=80` | **未弱化** |
| README decision | plan §13.1 保持 5 个 README 逐项 decision | **未弱化** |
| R03 handoff inventory | plan §13.2 保持逐文件 inventory | **未弱化** |

**闭合判断**：umbrella mandatory baseline 完整保留，allowlist 未扩大或缩小。

---

## 2. Residual Risks

| residual | 当前处理 | 与修前 plan 的变化 |
|---|---|---|
| 极大 source/目录消耗资源 | spool/cancel/output limit | 无变化 |
| 五工具未完整接 TruncationManager | 保留 current spec，Issue #177 | 无变化 |
| search result limit 后未扫描剩余 | schema 自解释 | 无变化 |
| symlink/TOCTOU 局部防御 | 三条不同 owner 边界明确冻结 | **改进**：plan 现在明确 list file-symlink 语义和 directory-symlink 不递归是现状保持 |
| S1→S2 中间态 directory cap 仍存在 | 行为不变，不新增 owner | **改进**：plan 现在明确禁止中间态新增 wrapper/assertion |

## 3. Open Questions

**无 blocking question。** 四项 accepted finding 的文本闭合已通过直接证据验证，controller rejected/no-fix 项未被误实现，umbrella mandatory baseline 未弱化。

## 4. Final Re-Review Conclusion

**Verdict: PASS**

修后 plan 的四项 accepted finding 全部通过直接证据验证闭合：

1. **R01-PF-01 (symlink)**：Python 3.11.15 直接实测确认 `rglob("*")` 不递归进入 directory symlink；`list_files` 保持 directory-entry 语义、`search_files` 使用 `_resolve_search_files_candidate`、`direct read` 使用 `_project_doc_paths`，三条不同 owner 边界明确冻结，未新增 list containment 或统一权限设计。
2. **R01-PF-02 (S1→S2 签名)**：S1 删除 `resource_budget` 参数后直接传 `_DOC_DIRECTORY_MAX_ENTRIES` 给 `max_directory_entries`；S2 删除常量和参数。无 wrapper、校验 helper、budget 类型、配置或兼容 seam。
3. **R01-PF-03 (list partial-only scan)**：§12.2.1 生产范围 scan 覆盖完整 `dayu` 包，逐命中分类规则明确区分 list 专属字段与 search/read 合法同名字段，stop 条件完备。
4. **R01-PF-04 (调用链消歧)**：§5.2 现在分别标明 `_source_snapshot` helper function、`LocalFileSource` 输入、`SourceSnapshot` context-manager type，不再把 helper/type 写成同一层符号。

全部 controller rejected/no-fix 项均未被 plan 意外引入。umbrella mandatory baseline（Issue #177 non-implementation、allowlist、security、smoke、coverage、README、R03 handoff）未弱化。

**修后 plan 可以进入 controller 最终裁决 gate。**
