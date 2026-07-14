# WU-SEMANTIC-OWNERSHIP-01 / R01 Doc Complete Input Plan Fix 后第二路完整 Re-Review — DS

## 0. Re-Review 身份与边界

- **re-review 类型**: adversarial plan re-review（plan fix 后的第二路独立完整 re-review，非新 WU、非 implementation review）
- **umbrella WU**: 既有 `WU-SEMANTIC-OWNERSHIP-01`
- **内部 remediation sub-WU**: `R01 Doc complete input`，slug `r01-doc-complete-input`
- **re-review target**: 修后 plan `docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md` + plan-fix artifact `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-fix-codex.md`
- **裁决真源**: `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-controller-adjudication.md`
- **初轮 review**: MiMo review `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-mimo.md` + DS review `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-ds.md`
- **re-review 人**: AgentDS（第二路 reviewer）
- **re-review 时间**: 2026-07-14 18:10 UTC+8
- **plan base**: accepted umbrella `227317a0`；plan-time HEAD `edc6ea62`
- **本次 gate 边界**: 只新增本 re-review artifact；不修改 plan/fix/control/design/代码/测试/README；不 commit/push/PR

## 1. 已完整读取的证据清单

| 证据源 | 路径 | 读取状态 |
|--------|------|----------|
| AGENTS.md | 项目根 | 全文已读 |
| 修后 R01 plan | `docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md` | 全文已读 |
| MiMo 初轮 review | `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-mimo.md` | 全文已读 |
| DS 初轮 review | `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-ds.md` | 全文已读 |
| Controller adjudication | `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-controller-adjudication.md` | 全文已读 |
| Plan fix (Codex) | `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-fix-codex.md` | 全文已读 |
| Umbrella control doc | `docs/host/issues-implementation-control.md` | R01 相关 entry 已读 |
| 当前 `doc_tools.py` | `dayu/tools/doc_tools.py` (3271 行) | 关键段已读: import、常量、DocResourceBudget、_execute_doc_business_value、_route_doc_business、_list_files_business、_search_files_business、_resolve_search_files_candidate、_project_doc_paths、_bounded_local_source、_BoundedTextRead、LLM-facing description 文本 |
| 当前 `bounded_source.py` | `dayu/documents/processors/bounded_source.py` | BoundedSourceSnapshot.__enter__ 与 SourceBudgetExceeded 已读 |
| Python 3.11 行为验证 | 直接执行 | `rglob` symlink 行为与 controller 结论一致 |

## 2. Assumptions Tested

| # | assumption | verdict | 证据 |
|---|-----------|---------|------|
| A1 | plan-fix 只修改 plan 文本与新增 fix artifact，未触碰产品代码/测试/README/control/design | **通过** | git status 显示 control 修改与三份既存 review 状态不变；无产品代码 diff；fix artifact §5.1 明确文件边界 |
| A2 | Python 3.11 `Path.rglob("*")` 不递归进入 directory symlink target | **通过** | 直接执行 Python 3.11.15 复现 controller 测试：创建 allowed root 内 directory symlink 指向外部目录，`rglob("*")` 产出 symlink entry 但不产出外部目录内文件 |
| A3 | 当前 `list_files` 对 file symlink 不做 containment 检查 | **通过** | `doc_tools.py:1540` 使用 `rglob("*")` + `is_file()`；无任何 `_resolve_search_files_candidate` 或 `_project_doc_paths` 调用 |
| A4 | 当前 `search_files` 对 file candidate 做 containment 检查 | **通过** | `doc_tools.py:1699-1703` 调用 `_resolve_search_files_candidate`，该函数 resolve 后检查 containment |
| A5 | 当前 direct read 的 `_project_doc_paths` 对文件路径做 canonical resolve + containment | **通过** | `doc_tools.py:1426` 使用 `candidate.expanduser().resolve(strict=False)` + `_is_relative_to` containment |
| A6 | 生产代码中无 list `scan_complete`/`truncated_reason` 的非 test 消费者 | **通过** | 全仓 `rg --glob '*.py' 'scan_complete|truncated_reason' dayu/` 命中全在 `doc_tools.py` 自身；无 Host/Engine/Service/UI 消费者 |
| A7 | umbrella mandatory baseline 未被弱化 | **通过** | 见 §4.5 逐项核查 |

## 3. R01-PF-01 至 R01-PF-04 逐项闭合证明

### 3.1 R01-PF-01 — 明确并保持当前 file/directory symlink owner 边界

**controller 要求**:
1. plan 明确当前 Python 3.11 `rglob` 不递归跟随目录 symlink，新 iterator 保持该行为，不把它描述为新安全修复。
2. plan 明确 list 继续按目录 entry 语义处理 file symlink，不新增 per-entry resolved containment 或新 symlink policy。
3. plan 明确 search 与 direct read 继续在实际内容读取边界执行现有 resolve / containment。
4. regression matrix 至少验证目录 symlink 不被递归、allowed-root 内 file symlink 的 list entry 行为、外部 file symlink 的 search/read 拒绝；不得把 list 元数据行为包装成统一 authorization contract。

**修后 plan 直接证据**:

- **§3.2 (plan 第 93 行)**:
  > `list_files` 的 file-symlink owner 保持当前 directory-entry 语义：遍历 entry 的 `is_file()` 成立时，继续按 symlink entry 的相对路径/名称和 `stat()` metadata 形成记录；list 不读取文件正文，不调用 `_resolve_search_files_candidate`，也不新增 per-entry resolved containment 或新的 symlink/authorization policy。

  对应代码事实：`doc_tools.py:1540-1571` — `_list_files_business` 使用 `rglob("*")`，`is_file()` 判断，`file_path.stat()` 读 metadata，无 containment 调用。完全一致。

- **§3.2 (plan 第 100 行)**:
  > Python 3.11 当前 `Path.rglob("*")` 会产出 file/directory symlink entry，但不会递归进入 directory-symlink target；新 helper 必须保持这一现状，不得把"不递归"描述或实施成 R01 新安全修复。helper 按每层 entry 的 `(name.casefold(), name)` 稳定排序、递归时保持稳定 depth-first 顺序、每个 entry 前观察 cancellation。search 仍在实际内容读取前调用 `_resolve_search_files_candidate` 重新 resolve/containment；direct read 仍在 `_project_doc_paths` 对输入路径 canonical resolve/containment 后才读取。三者是不同 owner boundary，不得包装成统一权限 contract。

  对应代码事实：
  - Python 3.11.15 直接执行 `rglob` 测试：产出 `linked-dir` 和 `linked-file.txt` symlink entry，但不产出外部目录内的 `outside-file.txt`。与 controller 结论一致。
  - `doc_tools.py:1699-1703` — search 调用 `_resolve_search_files_candidate`，resolve 后 containment。
  - `doc_tools.py:1426` — `_project_doc_paths` 使用 `.resolve(strict=False)` + `_is_relative_to` containment。

- **§9.4 (plan 第 389 行)**:
  > directory symlink entry 不被递归；allowed-root 内指向 allowed-root 内文件的 file symlink 仍作为 list entry 返回，记录使用 symlink entry 的相对路径/名称，不把该 list 元数据行为宣称为 authorization。指向 allowed-root 外文件的 file symlink 仍由 search 的 candidate resolve/containment 跳过，并由 direct read 的 `_project_doc_paths` 拒绝；不得通过给 list 新增 per-entry containment 来"统一"这三条行为。

- **§10 regression matrix (plan 第 429 行)**:
  > | directory/file symlink traversal | directory-symlink no-recursion + allowed-root 内 file-symlink list-entry tests | list traversal regression | 保持 Python 3.11 现状：不递归 directory symlink；list 按 entry 返回 file symlink，不新增 per-entry containment 或统一授权语义 |
  > | search/direct-read symlink containment | search symlink escape + direct-read denied tests | threshold smoke 的 outside file-symlink case | search 在候选读取边界跳过外部 target，direct read 在输入投影边界拒绝，root 外正文零泄漏/零命中 |

- **§11 smoke (plan 第 452-453 行)**:
  > 在 allowed root 内放置指向 root 外 marker 文件的 file symlink；search 不得读到 outside marker，direct read 的 `_project_doc_paths` resolved containment 仍拒绝。这个 smoke 只证明 search/direct-read 的内容读取边界，不给 list 增加 per-entry containment，也不把三者包装成统一 authorization contract。

**闭合判断**: **FULLY CLOSED** ✓

四项 controller 要求全部有直接 plan 文本对应，且与当前 Python 3.11 行为、doc_tools.py 代码事实完全一致。没有实施被 controller rejected 的 list containment 或统一权限设计。初轮 MiMo/DS reviewer 关于"rglob 递归跟随目录 symlink"的错误前提已纠正，plan 不再声称"新安全修复"。

---

### 3.2 R01-PF-02 — 封闭 S1 到 S2 的临时签名变化

**controller 要求**:
plan 写清 S1 删除 `resource_budget`、只把既有 `_DOC_DIRECTORY_MAX_ENTRIES: int` 直接传给 list/search；S2 删除该参数与常量。中间态不新增校验 helper、wrapper、budget 类型、配置或 public contract，也不作为可交付终态。

**修后 plan 直接证据**:

- **§8.1 (plan 第 264 行)**:
  > 删除 `DocResourceBudget` 及 process target/factory/builder/definition、`_execute_doc_business_value`、`_route_doc_business` 全链的 `resource_budget` 参数；`_route_doc_business` 不接收替代 budget 参数，只在 list/search 分支把既有模块常量 `_DOC_DIRECTORY_MAX_ENTRIES: int` 直接传给两个业务函数原有的 `max_directory_entries: int` 参数。S2 随后同时删除该常量和这两个参数。S1 是可独立 review 的中间 slice，不是 R01 可交付终态；中间态不得新增正整数 assertion/校验 helper、wrapper、dataclass 或其它 budget 类型、配置、optional 参数、alias、兼容逻辑或 public contract。

- **§9.2 第 1 点 (plan 第 356 行)**:
  > 按 §8.1 封闭临时签名：删除 `_DOC_DIRECTORY_MAX_ENTRIES`、`_list_files_business` / `_search_files_business` 的 `max_directory_entries: int` 参数及对应 docstring/传递与 counter break；不保留 S1 过渡参数或新增替代抽象。

**逐项检验**:

| 禁止项 | 修后 plan 是否存在 | 证据 |
|--------|-------------------|------|
| 新 wrapper | 不存在 | §8.1 明确 "不接收替代 budget 参数"，直接传 `int` |
| 新校验 helper | 不存在 | §8.1 明确 "不得新增正整数 assertion/校验 helper" |
| 新 budget 类型/dataclass | 不存在 | §8.1 明确 "不得新增……dataclass 或其它 budget 类型" |
| 新配置 | 不存在 | §8.1 明确 "不得新增……配置" |
| 新 optional 参数 | 不存在 | §8.1 明确 "不得新增……optional 参数" |
| 兼容 alias/re-export | 不存在 | §8.1 明确 "不得新增……alias、兼容逻辑或 public contract" |
| S2 保留过渡参数 | 不存在 | §9.2 明确 "不保留 S1 过渡参数或新增替代抽象" |

controller 明确 rejected 的"临时正整数 assert"（DS Finding 1 建议）未实施：plan §8.1 明确禁止 "正整数 assertion/校验 helper"。

**闭合判断**: **FULLY CLOSED** ✓

S1→S2 的两次签名变化已封闭为机械过渡：S1 全链删 `resource_budget`，list/search 直接收 `int` 常量；S2 同时删常量和参数。中间态无任何过渡抽象、校验、wrapper 或兼容 seam。controller rejected 的临时正整数 assert 未实施。

---

### 3.3 R01-PF-03 — 增加 list partial-only 字段传播分类 scan

**controller 要求**:
plan 增加可执行的生产范围 scan，并要求逐命中区分 list 专属字段与 read/search 的合法同名字段；最终必须证明 list producer、生产消费者、schema/assertion 与 README 中没有残留的 directory-partial 语义。

**修后 plan 直接证据**:

- **新增 §12.2.1 (plan 第 498-509 行)**:

  第一条 scan 命令（生产全范围）：
  ```bash
  rg -n --glob '*.py' 'scan_complete|truncated_reason' dayu
  ```
  > 第一条允许命中且必须在 S2 implementation/completion artifact 逐项记录 `path:line / symbol / tool / semantic owner / disposition`。合法分类只有 search 的 `result_limit` schema/result producer 与 read/read-section 的字符输出 schema/result producer；若出现 list producer、list schema description、读取 list 字段的任何生产 consumer，或无法判定 owner 的命中，立即 stop。

  第二条 scan 命令（测试/README）：
  ```bash
  rg -n 'scan_complete|truncated_reason|directory_entry_limit' \
    tests/tools/test_doc_tools_provider.py tests/README.md
  ```
  > 第二条中 list 相关测试只允许"字段不存在"的 negative assertion，不得保留 partial 值/reason assertion；`tests/README.md` 的 list contract 不得再描述这两个字段或 directory partial。

  > 结合 §12.2 第一条 semantic identifier 零命中，最终必须证明 list producer、生产 consumer、schema/test assertion 与 README 均无 `directory_entry_limit` 或 list entry-partial 残留，同时不误删 search/read 的合法同名字段。

**scan 可执行性验证**（re-review 已实际执行生产全范围 scan）：

执行 `rg -n --glob '*.py' 'scan_complete|truncated_reason' dayu/` 结果分类：

| 行号 | symbol | tool | owner | disposition |
|------|--------|------|-------|-------------|
| 201 | `_BoundedTextRead.scan_complete` | read/read-section | dataclass field — 字符输出 owner | **保留** |
| 702-704 | `list_files.description` | list | schema description — 含 `directory_entry_limit` | **S2 改写** |
| 851-852 | `search_files.description` | search | schema description — 含 `result_limit`/`source_limit` | S1 删除 source text，S2 清理 entry text |
| 926-927 | `read_file.description` | read | schema description — 字符输出 | **保留** |
| 1001 | `read_file_section.description` | read-section | schema description — 字符输出 | **保留** |
| 1538,1544,1581,1584,1585 | `_list_files_business` | list | result producer — `scan_complete`/`truncated_reason=directory_entry_limit` | **S2 删除** |
| 1687-1688,1693-1694 | `_search_files_business` | search | result producer — `directory_entry_limit` 分支 | **S2 删除** |
| 1737-1739,1742-1743,1755-1756 | `_search_files_business` | search | result producer — `source_limit`/`result_limit` 分支 | S1 删 source，S2 保留 result |
| 1841 | `_read_file_business` | read | result producer — 字符输出 | **保留** |
| 1911 | `_read_file_business` | read | result producer — 字符输出 | **保留** |
| 2367 | `_read_file_section_business` | read-section | result producer — 字符输出 | **保留** |
| 2392 | `_read_file_section_business` | read-section | result producer — 字符输出 | **保留** |

**关键发现**: 全部命中可明确分类。list producer 的 `scan_complete`/`truncated_reason`（1538-1585）将被删除；search/read/read-section 的合法同名字段保留。无 list 生产消费者（没有任何非 `doc_tools.py` 的模块读取 list 返回值的 `scan_complete`/`truncated_reason`）。无无法判定 owner 的命中。

**闭合判断**: **FULLY CLOSED** ✓

Production-wide classified scan 已可执行且已实际执行。分类规则明确：合法保留 = search `result_limit` + read/read-section 字符输出；待删除 = list entry partial + search `source_limit`/`directory_entry_limit`。不会误删 search/read 的合法同名字段。stop 条件覆盖了 list producer、生产 consumer 和无法判定 owner 的命中。

---

### 3.4 R01-PF-04 — 修正 SourceSnapshot 调用链措辞

**controller 要求**:
plan 将含混的 `_source_snapshot -> SourceSnapshot` 改成函数、输入和 context-manager class 可区分的调用链，避免把 helper 与类型写成同一层符号。

**修后 plan 直接证据**:

**修前文本**（初轮 DS Finding 6 引用）:
```text
get/read/search/section: _source_snapshot -> SourceSnapshot -> processor/raw reader
```

**修后文本**（plan §5.2 第 191-194 行）:
```text
get/read/search/section:
  with _source_snapshot(path, cancellation_token) as snapshot
    (_source_snapshot helper: LocalFileSource input -> unentered SourceSnapshot context-manager instance)
  -> active snapshot -> processor/raw reader
```

**消歧验证**:

| 符号 | 修前 | 修后 | 当前代码对应 |
|------|------|------|-------------|
| `_source_snapshot` | 与 `SourceSnapshot` 并列，语义模糊 | 明确为 helper function，构造 `LocalFileSource` + 未进入的 `SourceSnapshot` context-manager | 当前 `_bounded_local_source`（待 rename） |
| `LocalFileSource` | 未提及 | 明确为 Source 输入 | `dayu.documents.processors.local_file_source.LocalFileSource` |
| `SourceSnapshot` | 写成与 helper 同一层的抽象步骤 | 明确为 context-manager class，进入后变为 active snapshot | §3.1 定义的 `SourceSnapshot` 类 |
| active snapshot | 未区分 | 明确为进入上下文后的实例 | `SourceSnapshot.__enter__` 返回值 |

调用链现在区分了 helper 函数、`LocalFileSource` 输入、未进入的 `SourceSnapshot` context-manager instance 与 active snapshot consumer 四层语义。不再把 helper 和 type 写成同一层符号。

**闭合判断**: **FULLY CLOSED** ✓

---

## 4. Controller 全部 rejected/no-fix 项未误实现核查

### 4.1 Rejected/no-fix 项逐条核查

| rejected/no-fix 项 | controller 裁决理由 | 修后 plan 状态 | 是否误实现 |
|--------------------|--------------------|----------------|-----------|
| 给 list 新增 resolved containment / 统一授权 | Topic 9 要求现有安全实现保持现状；R01 不重设计权限 | plan §3.2、§9.4、§11 明确禁止 list per-entry containment，三条 owner 保持独立 | **未实施** ✓ |
| 把"不递归 directory symlink"写成新安全修复 | Python 3.11.15 实测不跟随；是现状保留 | plan §3.2 明确"保持现状，不得描述或实施成 R01 新安全修复" | **未实施** ✓ |
| 给固定 `_DOC_DIRECTORY_MAX_ENTRIES` 新增正整数 assert | 值是模块内固定 typed literal，非外部输入 | plan §8.1 明确"不得新增正整数 assertion/校验 helper" | **未实施** ✓ |
| 固定 iterator 私有函数名/签名/API | 行为 contract 已自足；implementation detail | plan §3.2、§9.2 只描述行为，未固定函数名/签名 | **未实施** ✓ |
| 给真实 smoke 增加 `slow` skip/pytest timeout/并行建文件 | 无实际时长证据；弱化默认验证 | plan §11 保持原 spec，无 `slow`/`timeout`/并行 | **未实施** ✓ |
| 给 SourceSnapshot 每条 contract 标注"保留/新增" | §3.1 定义最终 contract，§4.2 已区分 | plan §3.1 保持原文 | **未实施** ✓ |
| MiMo Finding 07/08 fix | reviewer 自证不成立 | 未修改 | **未实施** ✓ |
| MiMo OQ-2 sort-key tie-break | `(name.casefold(), name)` 同层确定 | 未修改 | **未实施** ✓ |
| MiMo OQ-3 spool memory 可配置 | 内部性能细节 | 未修改 | **未实施** ✓ |
| DS Finding 7/8/9 LLM scan/prompt/coverage | reviewer 已确认正确 | 未修改 | **未实施** ✓ |
| 产品代码/测试/README | controller 明确禁止 | plan-fix artifact §1 明确"不是 implementation"；git status 无产品代码 diff | **未实施** ✓ |

### 4.2 产品代码未修改证据

```text
git status 显示:
 M docs/host/issues-implementation-control.md
?? docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-ds.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-mimo.md
```

无 `dayu/`、`tests/`、`README.md` 下任何文件变更。plan-fix artifact §5.1 确认本 gate 只产生 plan 修改与 fix artifact。

### 4.3 Umbrella mandatory baseline 未弱化核查

| umbrella baseline | 修后 plan 位置 | 状态 | 证据 |
|-------------------|---------------|------|------|
| `allowed_paths` 必填/fail-fast | §4.2、§6.1、§10 | **保留** | plan 明确 `allowed_paths` 不迁移不修改 |
| containment/symlink policy 不重设计 | §3.2、§4.2、§9.4 | **保留** | 三条 owner 独立保持，不统一 |
| Issue #177 边界 | §0、§4.3、§12.4、§16.1 | **保留** | plan §0 明确 Issue 177 是唯一 destination；§12.4 scan 证明未接 `TruncationManager` |
| Security: process cancellation/fencing | §4.2、§10、§12.5 | **保留** | §12.5 security scan 预期命中并保留 |
| >32 MiB / >10k smoke | §11 | **保留** | 原 spec 未弱化，无 `slow` skip |
| Coverage per-file ≥80% | §8.5、§14.2 | **保留** | 逐文件 `--fail-under=80` 命令不变 |
| README decision | §13.1 | **保留** | S2 更新 tests/README；其它无 diff |
| R03 handoff inventory | §13.2 | **保留** | 逐文件 inventory 完整，R03 消费约束明确 |
| LLM-facing 约束 | §12.3、§13.2 | **保留** | tools.md 的"大文件先看章节"正确鉴定为 output guidance |
| Baseline failure registry | §14.1 | **保留** | inherited failures 指纹不变，不新增 registry |

**闭合判断**: 全部 controller rejected/no-fix 项均未在修后 plan 中误实施。umbrella mandatory baseline、allowlist、Issue 177、security、smoke、coverage、README 与 R03 handoff 无一弱化。

---

## 5. 五项重点 adversarial 再验证

### 5.1 directory/file symlink 与 list/search/direct-read 三条 owner 事实准确

**验证结论**: **准确** ✓

- 目录 symlink: Python 3.11 `rglob("*")` 不递归进入 directory symlink target（直接执行验证）；plan 正确标注为现状保留而非新安全修复。
- list file symlink: 当前代码 `is_file()` + `stat()` 无 containment；plan 正确保留此行为且明确禁止新增 per-entry containment。
- search file symlink: 当前代码 `_resolve_search_files_candidate` resolve + containment；plan 正确保留。
- direct read symlink: 当前代码 `_project_doc_paths` canonical resolve + containment；plan 正确保留。
- 未新增 list per-entry containment 或统一授权：plan §3.2、§9.4、§11 三处明确禁止。✓

### 5.2 S1→S2 临时签名无 wrapper、校验 helper、budget/兼容 seam

**验证结论**: **确认** ✓

- 无 wrapper：`_route_doc_business` 直接传 `int` 常量给 list/search。
- 无校验 helper：§8.1 明确禁止 `assertion/校验 helper`。
- 无 budget 类型：`DocResourceBudget` 全链删除后不引入替代。
- 无兼容 seam：S1→S2 是机械的两次删除，中间态不保留过渡参数。

### 5.3 production-wide list partial-only 分类 scan 可执行且不会误删 search/read 合法字段

**验证结论**: **确认** ✓

- scan 命令可执行：已实际执行 `rg -n --glob '*.py' 'scan_complete|truncated_reason' dayu/`，全部命中可分类。
- 分类规则明确：合法保留 = search result_limit + read/read-section 字符输出；待删除 = list entry partial + search source_limit/directory_entry_limit。
- 不会误删：分类 scan 要求逐命中记录 owner 和 disposition；stop 条件阻止误删。
- README 约束：§12.2.1 明确 `tests/README.md` 的 list contract 不得再描述这两个字段。

### 5.4 SourceSnapshot helper/type 调用链消歧

**验证结论**: **确认** ✓

- 修后调用链区分了 `_source_snapshot` helper function、`LocalFileSource` 输入、未进入的 `SourceSnapshot` context-manager instance、active snapshot consumer 四层语义。
- 不再将 helper 与 type 写成同一层符号。

### 5.5 controller 全部 rejected/no-fix 项未误实现

**验证结论**: **确认** ✓

- §4.1 逐项核查 11 条 rejected/no-fix 项，全部未实施。
- 产品代码/测试/README 无变更。
- umbrella mandatory baseline 全部保留未弱化。

---

## 6. Open Questions

**无 blocking question。**

以下为非阻塞观察：

### OQ-1 (informational): list scan_complete/truncated_reason 分类 scan 需要 implementation/completion artifact 实际执行

§12.2.1 要求 S2 implementation/completion artifact 逐项记录分类结果。当前 re-review 已实际执行生产全范围 scan 并分类（见 §3.3 表格），但这是 re-review 的验证动作，不是 implementation artifact 的输出。implementation agent 必须在 S2 completion artifact 中独立执行并记录同一 scan 结果，不可仅引用本 re-review。

**非阻塞原因**: plan §12.2.1 已明确要求 completion artifact 记录分类结果；本 re-review 证明了 scan 的可执行性和分类规则的完备性。

### OQ-2 (informational): `_BoundedTextRead` dataclass 的 `scan_complete` 字段名与 list/search 结果字段同名

`_BoundedTextRead.scan_complete`（line 201）是 read/read-section 内部 dataclass 的字段，语义为"字符扫描是否完整"。它与 list 和 search result dict 的 `scan_complete` key 同名但不同 owner。当前 plan §12.2.1 的 scan 命令（`rg -n --glob '*.py' 'scan_complete|truncated_reason' dayu`）会命中该 dataclass field 定义。implementation agent 需在分类时正确识别其 owner 为 read/read-section 字符输出，不是 list entry partial。

**非阻塞原因**: plan §12.2.1 的分类规则 "合法分类只有 search 的 result_limit schema/result producer 与 read/read-section 的字符输出 schema/result producer" 已覆盖此 case；`_BoundedTextRead` 属于 read/read-section 字符输出 owner。

---

## 7. Residual Risks

| residual | 当前处理 | 建议 |
|----------|---------|------|
| 极大本地 source/目录可能消耗资源 | 完整 spool、process boundary、cancellation、output limit | 正确由 Issue #177 承接；R01 不弱化此风险 |
| 五工具 output/remainder 未完整接 TruncationManager | 保留 current spec/framework owner；不扩张 R01 | 正确由 Issue #177 承接；R01 §12.4 scan 证明未接入 |
| search result limit 后未扫描剩余 | schema 自解释；不伪造 total | 正确由 Issue #177 承接 |
| symlink/TOCTOU 局部防御 | 三条独立 owner 行为保持；R01 不统一 | plan 已在三处明确禁止统一授权；后续独立立项 |
| list 不再返回 `scan_complete` 字段后，输出只靠 `total`/`returned`/`scanned_entries` 表达完整性 | `total` 为完整匹配数，`returned` 为首屏数 | 信息充分；`total > returned` 即表示有界 output |

---

## 8. Final Re-Review Conclusion

**Verdict: PASS**

R01 plan 经 plan-fix 后，四项 accepted finding (`R01-PF-01` 至 `R01-PF-04`) 已全部闭合：

- **R01-PF-01**: directory/file symlink 与 list/search/direct-read 三条 owner 边界已明确，与 Python 3.11 实际行为、当前 doc_tools.py 代码完全一致；未新增 list per-entry containment 或统一授权。
- **R01-PF-02**: S1→S2 临时签名已封闭为机械过渡；无 wrapper、校验 helper、budget 类型或兼容 seam；controller rejected 的临时正整数 assert 未实施。
- **R01-PF-03**: production-wide list partial-only 分类 scan 已增加且可执行；分类规则完备；不会误删 search/read 合法同名字段。
- **R01-PF-04**: SourceSnapshot helper/type 调用链已消歧为四层可区分语义。

全部 11 条 controller rejected/no-fix 项均未在修后 plan 中误实施。umbrella mandatory baseline（allowed_paths、Issue 177、security、smoke、coverage、README、R03 handoff）无一弱化。产品代码/测试/README 无任何变更。

**R01 plan 可以进入 controller accepted-plan local commit gate，随后进入 implementation。**

---

## Appendix A: Re-Review Execution Evidence

### A.1 Python 3.11 rglob symlink 行为验证

```text
Python 3.11.15
rglob entries: ['linked-dir', 'linked-file.txt', 'real-file.txt']
linked-dir is_dir(): True
linked-file is_file(): True
recursed into linked-dir? False
```

测试结构：allowed root 内创建 directory symlink（指向外部目录）和 file symlink（指向外部文件）。`rglob("*")` 产出两个 symlink entry，但不递归进入 directory symlink target 内的文件。

### A.2 Production-wide scan_complete/truncated_reason scan

执行 `rg -n --glob '*.py' 'scan_complete|truncated_reason' dayu/` 的完整命中见 §3.3 表格。全部命中在 `doc_tools.py`，无 Host/Engine/Service/UI 消费者。

### A.3 Production-wide rejected semantic identifier scan

执行 `rg -n 'DocResourceBudget|SourceBudgetExceeded|max_source_bytes|max_directory_entries|source_budget_exceeded|directory_entry_limit|source_limit|skipped_oversized_files' dayu tests README.md`：当前（修前代码）有预期命中（因代码尚未修改）；plan §12.2 要求 R01 completion 后全局零命中。

### A.4 产品代码未修改证据

```text
git status --short:
 M docs/host/issues-implementation-control.md
?? docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-ds.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-mimo.md
```

`dayu/`、`tests/`、`README.md` 路径零 diff。
