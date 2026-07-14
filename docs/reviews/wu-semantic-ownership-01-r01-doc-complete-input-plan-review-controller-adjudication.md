# WU-SEMANTIC-OWNERSHIP-01 / R01 Doc Complete Input Plan Review 总控裁决

## 1. 裁决对象与边界

- umbrella WU：`WU-SEMANTIC-OWNERSHIP-01`。
- 当前单元：内部 remediation sub-WU `R01 Doc complete input`；它不是新 WU，也不是重新打开的历史 sub-WU。
- plan：`docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`。
- 第一路 review：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-mimo.md`。
- 第二路 review：`docs/reviews/wu-semantic-ownership-01-r01-doc-complete-input-plan-review-ds.md`。
- 权威产品裁决：`docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 1、8、9。
- 设计真源：`docs/tool/design.md`、`docs/host/design.md` 及 accepted umbrella plan。

两路 reviewer verdict 都只是证据输入，不独立授权 plan acceptance。本 artifact 只裁决 plan gate；不授权 implementation。

## 2. 总控直接复核

### 2.1 S1/S2 边界

当前 `DocResourceBudget` 同时携带 source byte cap 与 directory entry cap。S1 删除前者而暂时把既有模块常量作为显式 `int` 传给 list/search，S2 再删除后者。两路 reviewer 均确认两个 slice 分别关闭不同 root cause，中间态不改变目录 cap 产品行为，也不新增配置、owner 或 public contract。

该切分可保留，但 plan 必须把两次签名变化写成封闭的机械过渡，明确禁止为了中间态新增 wrapper、dataclass、assertion helper、兼容 alias 或第二个 budget owner。`_DOC_DIRECTORY_MAX_ENTRIES` 是模块内固定整数常量；为它新增运行时正整数校验不是恢复既有外部输入校验，而是无必要的过渡代码。

### 2.2 list partial-only 字段消费者

两路 review 的全仓 source scan 均得到同一结论：生产代码没有 list `scan_complete` / `truncated_reason` 消费者；外部命中是测试与 `tests/README.md`。但现 plan 的 completion scan 只删除 cap-specific identifier，没有把“list 专属字段已消失、search/read 同名字段因不同 owner 合法保留”写成可复核分类。

因此接受一个 plan scan 补强，但不能采用只扫描 producer/test 文件后宣称全仓无消费者的弱证明。fix 必须给出生产范围 source scan 与逐命中分类规则。

### 2.3 symlink 事实复核

两路 review 都声称当前 Python 3.11 `Path.rglob("*")` 默认递归跟随目录 symlink。该关键前提不成立。总控使用项目解释器直接复核：

```text
Python 3.11.15
rglob result: ['linked-dir', 'linked-file.txt']
linked-file-is-file: True
linked-dir-is-dir: True
```

测试结构是在被遍历目录内创建一个指向外部目录的 symlink 和一个指向外部文件的 symlink；`rglob("*")` 产出两个 symlink entry，但没有产出外部目录内的文件。因此“不递归跟随目录 symlink”是当前行为的保留，不是 R01 新增安全修复。

当前代码的精确边界是：

- `list_files` 对 file symlink 使用 `is_file()` / `stat()`，会把 symlink entry 当作文件记录；它不读取正文，也没有 per-entry resolved containment。
- `search_files` 在读取前调用 `_resolve_search_files_candidate`，resolve 后重新做 allowed-root containment 与 file 检查，外部 target 不会被读取。
- 直接 read 的路径先经 `_project_doc_paths` canonical resolve / containment，外部 target 被拒绝。

Topic 9 已裁决“existing defensive security/safety implementations remain as they are”，并明确本 WU 不实施统一权限或重新设计 symlink policy。R01 只删除 input caps，不能借 iterator 改造新增 list per-entry containment，也不能把当前 list 行为误写成已有防御。真正的 plan 缺口是没有明确上述三条不同 owner 行为，implementer 可能自行改变 file-symlink 语义。

### 2.4 iterator 与 smoke

plan 已冻结模块级私有 helper、共享 owner、排序、depth-first、cancellation、目录 symlink 与 I/O 行为，足以 code generation。私有函数名、`os.scandir` / `Path.iterdir` 选择和具体返回类型是 implementation detail；reviewer 建议的固定函数签名不是产品或架构 contract。

真实 >32 MiB / >10,000 entries smoke 是用户明确要求的阈值反证。reviewer 给出的 60–120 秒估计没有运行证据；在验证前添加 `slow` skip、并行文件创建或 pytest timeout 会弱化默认验证或引入不必要复杂度。plan 已有“真实环境不合理则 blocked”的 stop condition，无需预先改写。

## 3. Accepted findings

### R01-PF-01 — 明确并保持当前 file/directory symlink owner 边界

来源：MiMo Finding 03 / OQ-1、DS Finding 3 中“contract 未完整指定”的有效部分。

要求：

1. plan 明确当前 Python 3.11 `rglob` 不递归跟随目录 symlink，新 iterator 保持该行为，不把它描述为新安全修复。
2. plan 明确 list 继续按目录 entry 语义处理 file symlink，不新增 per-entry resolved containment 或新 symlink policy。
3. plan 明确 search 与 direct read 继续在实际内容读取边界执行现有 resolve / containment。
4. regression matrix 至少验证目录 symlink 不被递归、allowed-root 内 file symlink 的 list entry 行为、外部 file symlink 的 search/read 拒绝；不得把 list 元数据行为包装成统一 authorization contract。

### R01-PF-02 — 封闭 S1 到 S2 的临时签名变化

来源：MiMo Finding 01、DS Finding 1 的有效文档部分。

要求：plan 写清 S1 删除 `resource_budget`、只把既有 `_DOC_DIRECTORY_MAX_ENTRIES: int` 直接传给 list/search；S2 删除该参数与常量。中间态不新增校验 helper、wrapper、budget 类型、配置或 public contract，也不作为可交付终态。

### R01-PF-03 — 增加 list partial-only 字段传播分类 scan

来源：MiMo Finding 02；DS Finding 2 的通过证据。

要求：plan 增加可执行的生产范围 scan，并要求逐命中区分 list 专属字段与 read/search 的合法同名字段；最终必须证明 list producer、生产消费者、schema/assertion 与 README 中没有残留的 directory-partial 语义。

### R01-PF-04 — 修正 SourceSnapshot 调用链措辞

来源：DS Finding 6。

要求：plan 将含混的 `_source_snapshot -> SourceSnapshot` 改成函数、输入和 context-manager class 可区分的调用链，避免把 helper 与类型写成同一层符号。

## 4. Rejected / no-fix findings

| finding | 裁决 | 直接理由 |
|---|---|---|
| MiMo Finding 03 / DS Finding 3 的“当前 rglob 跟随目录 symlink”与“给 list 新增 resolved containment”部分 | rejected | Python 3.11.15 直接实测否定前提；Topic 9 要求现有安全实现保持现状，R01 不重设计权限/symlink policy。 |
| DS Finding 1 的临时正整数 assert | rejected | 值是模块内固定 typed literal，不是未校验外部输入；新增 assert 是会在 S2 删除的过渡代码。 |
| MiMo Finding 04 / DS Finding 5 | rejected | 行为、owner、位置和共享要求已经自足；固定私有 helper 名称/API 会把 implementation detail 升格为 plan contract。 |
| MiMo Finding 05 / DS Finding 4 的 smoke 性能建议 | rejected | 无实际时长证据；`slow` 可跳过、并行写和 timeout 不属于正确性 contract。真实阈值 smoke 不得弱化。 |
| MiMo Finding 06 | rejected | §3.1 定义最终完整 contract，§4.2 已区分保留项；重复标注不会改变 implementation。 |
| MiMo Finding 07、08 | rejected as self-disproved | reviewer 自己确认现有 scan 已覆盖对应 source residual，精确匹配不会误伤 `directory_entry_limit`。 |
| MiMo OQ-2 | rejected | `(name.casefold(), name)` 是每层排序；同层 entry 名唯一，父目录也按同一规则排序，depth-first 顺序确定。list 最终 bounded-heap order 仍有独立现有 sort key。 |
| MiMo OQ-3 | no-fix note | spool memory threshold 已明确为内部性能细节；R01 不新增配置 owner。 |
| DS Finding 7、8、9 | passed/no-fix | reviewer 已确认 LLM scan、prompt retain 与精确 coverage include 正确。 |

## 5. Gate decision

R01 plan **暂不接受**。`R01-PF-01` 至 `R01-PF-04` 必须由 AgentCodex 在同一 plan-fix gate 全部关闭；不得实施任何产品代码、测试或 README，也不得实现 rejected/no-fix 项。

fix 完成后必须由 AgentMiMo、AgentDS 并发做完整 re-review，至少验证：

1. symlink 文本与 Python 3.11 / 当前代码事实一致，未新增 list containment 或统一授权设计；
2. 两 slice 临时签名没有新增过渡抽象/校验；
3. list partial-only propagation scan 可执行且不误删 read/search 合法语义；
4. SourceSnapshot 调用链措辞已消歧；
5. 所有 rejected/no-fix 建议均未被误实现。

当前无产品、owner、依赖或 allowlist blocker；next gate 是 R01 plan fix。
