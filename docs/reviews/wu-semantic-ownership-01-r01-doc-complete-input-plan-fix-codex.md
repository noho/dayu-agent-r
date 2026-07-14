# WU-SEMANTIC-OWNERSHIP-01 / R01 Doc Complete Input Plan Fix — Codex

## 1. 身份、范围与结论

- **umbrella WU**：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- **内部 remediation sub-WU**：`R01 Doc complete input`；不是新 WU。
- **修复时间**：`2026-07-14 18:03:21 +0800`（本机系统时钟）。
- **目标 plan**：`docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`。
- **裁决真源**：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-controller-adjudication.md`。
- **本 gate 边界**：只修 plan 文本并新增本 artifact；不是 implementation，不授权修改产品代码、测试、README、control/design，也不 commit、push 或创建 PR。
- **第一性原理结论**：四项 accepted finding 都成立，但根因是 plan 的 owner/过渡/验证措辞欠封闭，不是产品实现缺陷的新发现。正确修复是收紧 plan contract；扩大为统一权限设计、临时预算校验或 iterator API 设计会偏离 controller 裁决。
- **结果**：`R01-PF-01` 至 `R01-PF-04` 已全部在同一 plan-fix gate 关闭；等待双路完整 re-review 与 controller 后续裁决。

## 2. 已完整读取的证据

1. `AGENTS.md`。
2. `/Users/leo/.codex/skills/planreview/SKILL.md`。
3. `docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md` 修前全文。
4. `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-mimo.md` 全文。
5. `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-ds.md` 全文。
6. `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-controller-adjudication.md` 全文。
7. 当前 `dayu/tools/doc_tools.py` 的 `_project_doc_paths`、`_route_doc_business`、`_list_files_business`、`_search_files_business`、`_resolve_search_files_candidate` 与 `_bounded_local_source` 直接代码事实，用于避免把 reviewer 的错误 `rglob` 前提写回 plan。

## 3. Accepted findings 逐项关闭证据

### R01-PF-01 — 明确并保持当前 file/directory symlink owner 边界

**修前文本证据（原 §3.2、§10）**：

> deterministic traversal 使用模块级私有 helper，而不是复制 list/search 两套规则。helper 按每层 entry 的 `(name.casefold(), name)` 稳定排序、递归时保持稳定 depth-first 顺序、每个 entry 前观察 cancellation，并且不跟随目录 symlink 递归；search 仍在读取前调用 `_resolve_search_files_candidate` 重新 resolve/containment。

> `| symlink guard | search symlink escape test | threshold smoke 的 outside symlink case | root 外正文零泄漏/零命中 |`

问题在于修前文本没有说明“不递归 directory symlink”是 Python 3.11 当前行为，也没有冻结 list file-symlink 的 entry 语义和 direct-read 的独立输入投影 owner，implementer 可能擅自新增 list containment 或把三条边界统一。

**修后文本证据（现 §3.2，plan 第 93、100 行）**：

> `list_files` 的 file-symlink owner 保持当前 directory-entry 语义：遍历 entry 的 `is_file()` 成立时，继续按 symlink entry 的相对路径/名称和 `stat()` metadata 形成记录；list 不读取文件正文，不调用 `_resolve_search_files_candidate`，也不新增 per-entry resolved containment 或新的 symlink/authorization policy。

> Python 3.11 当前 `Path.rglob("*")` 会产出 file/directory symlink entry，但不会递归进入 directory-symlink target；新 helper 必须保持这一现状，不得把“不递归”描述或实现成 R01 新安全修复。……search 仍在实际内容读取前调用 `_resolve_search_files_candidate` 重新 resolve/containment；direct read 仍在 `_project_doc_paths` 对输入路径 canonical resolve/containment 后才读取。三者是不同 owner boundary，不得包装成统一权限 contract。

**修后验证 contract（现 §9.4、§10、§11）**：

- directory symlink entry 不被递归；
- allowed-root 内 file symlink 保持 list entry 行为；
- outside file symlink 由 search candidate containment 跳过、由 direct read 输入投影拒绝；
- smoke 明确只证明 search/direct-read 的内容读取边界，不给 list 新增 per-entry containment。

**关闭判断**：当前 Python 3.11 directory/file symlink、list/search/direct-read 的不同 owner 行为已自足，且明确保持现状；没有实施被 controller rejected 的 list containment 或统一权限设计。

### R01-PF-02 — 封闭 S1 到 S2 的临时签名变化

**修前文本证据（原 §8.1、§8.2）**：

> 目录 entry cap 在 S1 只保持原行为：`_DOC_DIRECTORY_MAX_ENTRIES` 已是现有模块常量，`DocResourceBudget` 删除后由 `_route_doc_business` 直接传给 list/search，S2 再删除。这个短暂状态不新增 owner、配置或 public contract，也不允许重命名/封装成新 budget 类型。

> `_DocProcessTarget` / `_DocProcessTargetFactory` / builder/definition/helper 全链删除 `resource_budget`；

> `_route_doc_business` 在 S1 暂时直接传既有 `_DOC_DIRECTORY_MAX_ENTRIES` 给 list/search，不给其它工具传 source max；

修前没有完整列出 `_execute_doc_business_value` / `_route_doc_business` 的参数终态，也没有明确 S2 精确删除哪两个临时参数，仍给过渡校验/抽象留下空间。

**修后文本证据（现 §8.1，plan 第 264 行）**：

> 删除 `DocResourceBudget` 及 process target/factory/builder/definition、`_execute_doc_business_value`、`_route_doc_business` 全链的 `resource_budget` 参数；`_route_doc_business` 不接收替代 budget 参数，只在 list/search 分支把既有模块常量 `_DOC_DIRECTORY_MAX_ENTRIES: int` 直接传给两个业务函数原有的 `max_directory_entries: int` 参数。S2 随后同时删除该常量和这两个参数。

> 中间态不得新增正整数 assertion/校验 helper、wrapper、dataclass 或其它 budget 类型、配置、optional 参数、alias、兼容逻辑或 public contract。

**修后 S2 终点证据（现 §9.2，plan 第 356 行）**：

> 删除 `_DOC_DIRECTORY_MAX_ENTRIES`、`_list_files_business` / `_search_files_business` 的 `max_directory_entries: int` 参数及对应 docstring/传递与 counter break；不保留 S1 过渡参数或新增替代抽象。

**关闭判断**：S1 与 S2 的签名终点、唯一传值路径和删除顺序已封闭；没有新增 wrapper、校验 helper、budget 类型、配置或兼容 seam，也没有采纳被 rejected 的临时正整数 assert。

### R01-PF-03 — 增加 list partial-only 字段传播分类 scan

**修前文本证据（原 §12.2、§16.3）**：

> 全部预期无输出。数值 scan 故意限定 Doc surface；全局 semantic identifier scan 仍不可限定。

> list 删除只为 directory partial 存在的 `scan_complete/truncated_reason` 是否遗漏真实消费者；当前 repository search 只发现 tests/schema description consumer，implementation 前必须再跑同一 source scan确认。

修前只有 cap-specific 零命中 scan，没有给出生产全范围的同名字段传播 scan，也没有要求逐命中区分 list 的待删语义与 search/read 的合法 owner。

**修后文本证据（新增 §12.2.1，plan 第 498—509 行）**：

```bash
rg -n --glob '*.py' 'scan_complete|truncated_reason' dayu

rg -n 'scan_complete|truncated_reason|directory_entry_limit' \
  tests/tools/test_doc_tools_provider.py tests/README.md
```

> 第一条允许命中且必须在 S2 implementation/completion artifact 逐项记录 `path:line / symbol / tool / semantic owner / disposition`。合法分类只有 search 的 `result_limit` schema/result producer 与 read/read-section 的字符输出 schema/result producer；若出现 list producer、list schema description、读取 list 字段的任何生产 consumer，或无法判定 owner 的命中，立即 stop。

> 最终必须证明 list producer、生产 consumer、schema/test assertion 与 README 均无 `directory_entry_limit` 或 list entry-partial 残留，同时不误删 search/read 的合法同名字段。

**关闭判断**：scan 覆盖完整生产包 `dayu`，不是只扫 producer/test 文件；命中分类、合法 owner、stop 条件、测试 negative assertion 和 README 终态均已明确。

### R01-PF-04 — 修正 SourceSnapshot 调用链措辞

**修前文本证据（原 §5.2）**：

> `get/read/search/section: _source_snapshot -> SourceSnapshot -> processor/raw reader`

**修后文本证据（现 §5.2，plan 第 191—194 行）**：

```text
get/read/search/section:
  with _source_snapshot(path, cancellation_token) as snapshot
    (_source_snapshot helper: LocalFileSource input -> unentered SourceSnapshot context-manager instance)
  -> active snapshot -> processor/raw reader
```

**关闭判断**：调用链现在分别标明 helper function、`LocalFileSource` 输入、未进入的 `SourceSnapshot` context-manager instance 与 active snapshot consumer，不再把 helper/type 写成同一层符号。

## 4. Controller rejected / no-fix 项未实施

| rejected / no-fix 项 | 本次 disposition |
|---|---|
| 给 list 新增 resolved containment，或把“不递归 directory symlink”写成新安全修复 | 未实施；plan 反向明确禁止，并冻结 Python 3.11 当前行为 |
| 给固定 `_DOC_DIRECTORY_MAX_ENTRIES: int` 新增正整数 assert/校验 | 未实施；plan 明确禁止 assertion/校验 helper |
| 固定 iterator 私有函数名、签名、返回类型或 `os.scandir` / `Path.iterdir` 选择 | 未实施；只保留既有行为 contract 与模块级私有共享 owner |
| 给真实 smoke 增加 `slow` skip、pytest timeout、并行建文件或预估时长 | 未实施；§11 的真实阈值与默认执行 contract 未弱化 |
| 给 SourceSnapshot 每条 contract 重复标注“保留/新增” | 未实施；§3.1 保持原文 |
| 修改 MiMo Finding 07/08 对应 scan、sort-key tie-break 或其它 self-disproved 项 | 未实施 |
| 把 spool memory threshold 配置化 | 未实施 |
| 修改 LLM scan、保留 prompt 或精确 coverage include | 未实施；controller 已裁决 no-fix |
| 产品代码、测试、README、control/design、Issue 或其它 artifact | 未修改 |

## 5. 文件边界与验证

### 5.1 文件边界

本 gate 只产生以下两个目标文件内容：

1. 修改 `docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`。
2. 新增 `docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-fix-codex.md`。

开始时已存在且本 gate 未触碰的工作区状态：

- `M docs/host/issues-implementation-control.md`；
- 未跟踪的目标 plan、两路 review 与 controller adjudication。

没有修改产品代码、测试、README、control/design 或其它文件；没有 stage、commit、push 或 PR 操作。

### 5.2 验证结果

- `pytest` / `pyright`：未运行；本 gate 只修改 plan/review 文档，且用户明确禁止进入 implementation 或修改代码/测试。
- `git diff --check`：exit `0`，无输出。
- 对两个未跟踪目标文件分别执行 `git diff --no-index --check /dev/null <file>`：均无 whitespace error 输出；exit `1` 仅表示 no-index 两端内容不同。补充 `rg -n '[[:blank:]]+$' <plan> <fix-artifact>` 无命中。
- 最终 `git status --short`：

```text
 M docs/host/issues-implementation-control.md
?? docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-fix-codex.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-controller-adjudication.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-ds.md
?? docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-mimo.md
```

与 gate 开始状态相比只新增 fix artifact 条目；control 修改和三份既有 review 状态保持不变，目标 plan 仍按原状态为未跟踪文件。

## 6. Remaining risk

本次没有 implementation 结果，因此不声称生产行为或测试已通过。剩余风险只在后续 gate：双路完整 re-review 必须确认四项 accepted finding 的文本闭合，且确认上述 rejected/no-fix 项没有被 plan 意外引入；controller 接受修后 plan 前不得 implementation。
