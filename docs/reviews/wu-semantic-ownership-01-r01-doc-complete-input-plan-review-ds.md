# WU-SEMANTIC-OWNERSHIP-01 / R01 Doc Complete Input — 第二路独立 Plan Review (DS)

## 审查身份

- **审查类型**：adversarial plan review（第二路独立，非 implementation review）
- **审查 target**：`docs/host/wu-semantic-ownership-01-r01-doc-complete-input-plan.md`
- **审查 base**：plan 声明 base = `227317a0cf`（accepted umbrella），plan-time HEAD = `edc6ea62`
- **审查范围**：plan 全文 + 所有必读真源（AGENTS.md、controller discussion Topic 1/8/9、五份 design truth、umbrella plan §0/§6-§8/§21-§24） + 当前生产代码/测试/README 直接证据
- **审查人**：AgentDS（第二路 reviewer）
- **审查时间**：2026-07-14 17:50 UTC+8

## 0. Assumptions Tested

| # | assumption | verdict | 证据 |
|---|-----------|---------|------|
| A1 | plan base 与 HEAD 之间 R01 相关路径无 diff | **通过** | plan §0 列出的 blob SHA 经核实：`bounded_source.py` (`4a09dbb`)、`doc_tools.py` (`09aa9b2`)、`doc_provider.py` (`b6521d0`) 等均在两个 SHA 保持一致 |
| A2 | 语义 owner 唯一清晰 | **通过** | source snapshot owner = `dayu.documents.processors`；tool result/error owner = `dayu.tools.doc_tools`；config owner = `dayu.tools.doc_provider`。Controller discussion Topic 1 明确裁决删除 input cap |
| A3 | 无越界 production 文件需求 | **通过** | §6.1 production 闭集 6 个文件与实际调用链一致；Host/Engine/runtime/contracts/config/Fins/UI/Service 均不在必须修改范围内 |
| A4 | list `scan_complete/truncated_reason` 无遗漏消费者 | **通过（有注记）** | 见 Finding 2 |
| A5 | deterministic iterator 保留既有安全行为 | **部分通过** | 见 Finding 3 |
| A6 | 真实 smoke 成本可接受 | **通过** | 见 Finding 4 |
| A7 | plan contract code-generation-ready | **部分通过** | 见 Finding 5 |
| A8 | umbrella baseline 逐项映射完整 | **通过** | §7 表格覆盖 umbrella §7.4/§7.5/§8/§21/§22 全部 R01 baseline 项，逐项给出 `保留/细化/等价替换`，无静默遗漏 |

## 1. Findings

### F1-未修复-低-S1 临时传 directory cap 是合理的切片边界，非过度设计

- **位置**: plan §8.1 原子目标、§8.2 production 改动第 5 条、§16.3 remaining question 1
- **问题类型**: 切片过粗 / 过度设计（被证伪）
- **当前写法**: S1 删除 `DocResourceBudget` 类和 `max_source_bytes` 全链，但 `_route_doc_business` 在 S1 暂时直接传既有模块常量 `_DOC_DIRECTORY_MAX_ENTRIES` 给 list/search；S2 再连同常量一起删除。plan 声称"这个短暂状态不新增 owner、配置或 public contract，也不允许重命名/封装成新 budget 类型"
- **反例/失败场景**: 若 S1 和 S2 之间发生阻断（如 controller 需要 pause、发现新问题），中间态仍有 directory entry cap 行为，但与旧 `DocResourceBudget` 类无关。这可能让后续 developer 误以为 directory cap 已被删除
- **为什么有问题**: 问题在于中间态虽然行为不变，但实现方式从"通过 dataclass 传参"变成"直接引用模块常量"。`DocResourceBudget.__post_init__` 的防御性校验（防止 bool/int 混淆、非正数）在 S1 直接传常量时会丢失。这不是语义退化（常量值的正确性不变），但丢失了一个防御层
- **直接证据**:
  - `doc_tools.py:133-150`：`DocResourceBudget.__post_init__` 对 `max_directory_entries` 做 `isinstance(value, bool) or not isinstance(value, int) or value <= 0` 校验
  - plan §8.2: "`_route_doc_business` 在 S1 暂时直接传既有 `_DOC_DIRECTORY_MAX_ENTRIES` 给 list/search"
  - 当前调用链 `_route_doc_business` 接收 `resource_budget: DocResourceBudget` 参数，S1 将其替换为 `int` 直接参数
- **影响**: 轻微。S1→S2 是同一 sub-WU 的两个 slice，plan 明确禁止 S1 和 S2 之间暂停后以 S1 状态交付。常量值在 S1 中不变
- **建议改法和验证点**: 无需改变切片边界。建议在 S1 implementation artifact 中显式记录：S1 的 `_route_doc_business` 签名从 `resource_budget: DocResourceBudget` 改为 `max_directory_entries: int`（带正整数 assert 替代原 `__post_init__` 校验），并在 S2 删除该参数。plan §8.1 已说"不新增 owner、配置或 public contract"，可补充"不丢失既有校验"
- **修复风险**: 低
- **严重程度**: 低（已充分论证，仅补充文档建议）

**裁决**: 这不是过度设计。两个 slice 分别解决不同的 root cause（source byte budget vs directory entry cap），各自有独立的测试矩阵和 coverage 目标。合并为一个 slice 会形成更大的原子变更，降低可审查性。

---

### F2-已通过-低-list `scan_complete/truncated_reason` 删除无真实消费者遗漏

- **位置**: plan §3.2、§4.1、§9.2、§16.3 remaining question 2
- **问题类型**: 契约缺失 / open question 收敛
- **当前写法**: plan 声称删除 list 专用于 directory partial 的 `scan_complete/truncated_reason` 字段。plan §16.3 要求"implementation 前必须再跑同一 source scan 确认"
- **反例/失败场景**: 若有非 test 消费者依赖 list 的 `scan_complete/truncated_reason` 字段做路由决策，删除会导致运行时 KeyError 或逻辑分支失效
- **直接证据（plan review 阶段的 source scan）**:
  - `dayu/tools/doc_tools.py` 是唯一 producer（`_list_files_business` 第 1578-1586 行构造这两个字段）
  - **零个**非 test、非 doc_tools.py 自身的生产代码文件读取 list 返回值的 `scan_complete` 或 `truncated_reason`
  - `tests/tools/test_doc_tools_provider.py` 第 842-844 行、894-895 行是唯一的外部 consumer（验证 partial/complete 语义）
  - `tests/README.md` 第 175 行在文档描述中提到这些字段，属 S2 更新范围
  - `docs/` 下只有 R3-E 历史 plan 引用（非消费者）
  - Host/ToolRuntime 不解析 list 返回值内的这些字段——ToolRuntime 只通过 `ToolTruncateSpec` 做 output 截断，不检查业务 payload 内部字段
- **结论**: 无遗漏的真实消费者。plan §16.3 的谨慎要求（implementation 前再跑 scan）合理但 plan review 阶段已经可以确认
- **保留正确性验证**:
  - `read_file` / `read_file_section` 的 `scan_complete` 字段（字符截断语义，plan §4.2 明确保留）**不受影响**——它们来自 `_BoundedTextRead` dataclass（第 196-204 行），与 list 的 dict key `scan_complete` 是不同的语义 owner
  - search 的 `scan_complete/truncated_reason` 保留（因 `result_limit` 仍存在），plan §9.2 明确保留
- **严重程度**: 已通过（低风险确认项）

---

### F3-未修复-中-稳定 iterator 的 file symlink 语义未完整指定

- **位置**: plan §3.2 deterministic traversal 描述、§9.2 production 改动第 2 条
- **问题类型**: 契约缺失 / 安全边界
- **当前写法**: plan §3.2 说 "不跟随目录 symlink 递归"，§9.2 说 "不递归跟随目录 symlink"；plan §9.2 说 search "保留 candidate resolved containment"（通过 `_resolve_search_files_candidate`）。但对 **list_files 中的 file symlink** 处理方式未指定
- **反例/失败场景**:
  1. **目录 symlink 行为变更未记录为安全修复**：当前 `dir_path.rglob("*")`（第 1540 行）**默认跟随目录 symlink**（Python 3.11+ Path.rglob 行为）。若 allowed root 内存在指向 root 外的目录 symlink，rglob 会遍历 outside 文件。当前 list_files **没有** per-entry containment 检查（与 search_files 不同）。新 iterator 不跟随目录 symlink 实际上是**安全改进**，但 plan 未将其记录为安全修复
  2. **file symlink 信息泄露**：当前 list_files 对 symlink-to-outside-file 调用 `file_path.is_file()` 返回 True（跟随 symlink），`file_path.stat()` 返回 target 的 size/mtime。plan 未说明新 iterator 对 file symlink 的处理——是 resolve 后 containment check（与 search 一致），还是 stat 原路径（泄露 target metadata），还是不跟随？
  3. **`read_file` 的 symlink 行为**：`_bounded_local_source` → `LocalFileSource(path=path)` → `path.open("rb")` 会跟随 file symlink。这被 `_project_doc_paths` 的 `candidate.resolve(strict=False)` + containment check 保护。但若新 iterator 产生的 list 中 file path 是未 resolve 的 symlink path，模型可能用该 path 调 `read_file`，此时 `_project_doc_paths` 的 resolve+containment 会正确拒绝（如果 symlink 指向 outside）。路径拒绝的错误消息可能让模型困惑
- **为什么有问题**: contract 不完整。implementer 需要在没有明确指导下自行决定 file symlink 语义，可能在 list_files 中引入与 search_files 不一致的 containment 行为
- **直接证据**:
  - `doc_tools.py:1540`: `entries = dir_path.rglob("*")` — rglob 默认跟随目录 symlink
  - `doc_tools.py:1547`: `if not file_path.is_file():` — symlink-to-file 返回 True
  - `doc_tools.py:1760-1784`: `_resolve_search_files_candidate` — search 有 containment 重检，list 没有
  - 全仓库搜索 `is_symlink|follow_symlinks` 在 `dayu/tools/doc_tools.py` 与 `dayu/documents/processors/` 中**零命中**——当前没有显式 symlink 分类逻辑
- **影响**: 实施 Agent 可能对 file symlink 采用不一致策略（list 直接 stat vs resolve 后 containment）；list 可能泄露 outside 文件 metadata（size/mtime）即使 read 被正确拒绝
- **建议改法和验证点**:
  1. plan §3.2 显式补充 file symlink 策略：建议 list_files 对新 iterator 产出的每个 file candidate 也做 resolve + containment check（复用或提取 `_resolve_search_files_candidate` 的核心逻辑），使 list 和 search 的 containment 行为一致
  2. 将"从 rglob 改为不跟随目录 symlink"记录为显式安全修复（当前 plan 未标记此项为安全改进）
  3. smoke test（§11）的 symlink 用例已覆盖 search escape，建议增加到 list_files 的 symlink 验证
- **修复风险**: 低（在 plan 层面补充语义，不改变代码）
- **严重程度**: 中（contract 不完整，可能导致 implementation 时的不一致；但不阻塞 plan acceptance，可在 controller adjudication 后补充到 plan fix）

---

### F4-已通过-低-真实 smoke 设计合理、成本可接受

- **位置**: plan §11
- **问题类型**: 过度设计 / 测试缺口（被证伪）
- **当前写法**: 在 `tmp_path` 创建 10,001 个小 .txt 文件 + 一个 >33 MiB 文件，通过真实 discovery→callable 验证 list tail/search tail/read 成功；使用 1 MiB ASCII chunk 循环写避免大内存构造
- **反例评估**:
  - **磁盘成本**: 10,001 个极小文件（每个几十字节）+ 33 MiB 大文件 ≈ 34 MiB 磁盘。`tmp_path` 自动清理
  - **inode 成本**: 10,001 次文件创建。在 APFS (macOS) 上通常是亚秒级操作；在 CI 容器文件系统上可能慢 2-5 秒
  - **时间成本**: 文件创建 + 遍历 + 搜索 + 读取 + cleanup ≈ 5-15 秒。对于 smoke test 可接受
  - **plan 自带的 blocking guard**: "若真实文件系统无法在合理测试环境创建这些输入，R01 blocked"——这个条件合理。如果测试环境连 10,001 个小文件都无法创建，那 Doc 工具在实际使用中也会遇到问题
- **优化建议（非必须）**: 可考虑将 smoke 标记为 `pytest.mark.slow` 并在 CI 中选择性运行，但 plan 要求默认 pytest 可执行且不打 skip/xfail，这对于验证正确性是合理的严格性
- **结论**: 非过度设计。smoke 的真实性要求（不用 monkeypatch、不用 declared length 冒充）是正确的测试策略
- **严重程度**: 已通过

---

### F5-未修复-低-deterministic iterator 实现细节留给 implementer，存在不必要的自由度

- **位置**: plan §3.2、§9.2
- **问题类型**: 不可直接实施
- **当前写法**: plan 说 deterministic iterator 应该"按每层 entry 的 `(name.casefold(), name)` 稳定排序、递归时保持稳定 depth-first 顺序、每个 entry 前观察 cancellation，并且不跟随目录 symlink 递归"。但没有指定：
  - 使用 `os.scandir` 还是 `Path.iterdir` 还是 `os.walk`——不同 API 的 symlink 行为不同
  - `os.scandir` 的 `DirEntry.is_symlink()` 和 `DirEntry.is_dir(follow_symlinks=False)` 可以区分 directory symlink
  - `Path.iterdir()` 不跟随 symlink 但也不报告 symlink 属性
- **为什么有问题**: implementer 可能选择 `os.walk`（默认 followlinks=False 但行为与 plan 描述的 depth-first + sort 不完全一致），或自建递归，导致轻微的跨平台行为差异
- **直接证据**:
  - plan §9.2: "新增模块级私有 deterministic iterator + sort-key helper，供 list/search 共用"——正确但缺少实现约束
  - Python 3.11 `os.scandir` 的 `DirEntry.is_dir(follow_symlinks=False)` 是实现"不跟随目录 symlink"的最直接方式
  - Python 3.11 `os.walk` 的 `followlinks=False`（默认）也会跳过目录 symlink，但 `os.walk` 的遍历顺序不可控
- **影响**: 实施 Agent 可能选择不同实现，导致后续 review 返工。但不影响 contract 正确性（contract 只要求稳定排序 + 不跟随目录 symlink）
- **建议改法和验证点**: plan 可补充一句"推荐基于 `os.scandir` + `DirEntry.is_dir(follow_symlinks=False)` 实现以精确控制目录 symlink 和遍历顺序"，但这不是 plan acceptance 的硬条件。测试的 deterministic order test（§9.4 第 382 行）已经提供了足够的验收标准
- **修复风险**: 低
- **严重程度**: 低（测试已覆盖行为契约，实现选择是 local optimization）

---

### F6-未修复-低-plan §5.2 目标调用链中 `_source_snapshot` 函数命名与 §3.1 `SourceSnapshot` 类名不一致

- **位置**: plan §5.2 目标路径文本
- **问题类型**: 不可直接实施（轻微措辞不一致）
- **当前写法**: §5.2 写 "`_source_snapshot -> SourceSnapshot -> processor/raw reader`"。`_source_snapshot` 是 plan §8.2 中提到的内部 helper 函数（当前对应 `_bounded_local_source`），而 `SourceSnapshot` 是 §3.1 的新类名
- **为什么有问题**: implementer 可能困惑 `_source_snapshot` 是函数还是类。plan §3.1 定义的 `SourceSnapshot` 是类，§8.2 说的 `_source_snapshot(path, token)` 是构造 `LocalFileSource` + `SourceSnapshot` 的工厂函数。调用链图应该更精确地区分
- **直接证据**: plan §8.2: "`_source_snapshot` 构造 `LocalFileSource` + `SourceSnapshot`"
- **影响**: 轻微。熟悉代码的 implementer 可以正确理解，但增加了阅读摩擦
- **建议改法和验证点**: 将 §5.2 中 `_source_snapshot -> SourceSnapshot` 改为 `_source_snapshot(path, token) -> LocalFileSource + SourceSnapshot(context manager) -> processor/raw reader`
- **修复风险**: 低
- **严重程度**: 低

---

### F7-未修复-低-plan §12.3 LLM-facing scan 正则可能漏掉部分中文引导语

- **位置**: plan §12.3
- **问题类型**: 契约缺失
- **当前写法**: scan 正则包含 `较小文件|拆分文件|缩小文件范围|缩小目录`，这些是当前 `doc_tools.py` 中的 LLM-facing 文本
- **发现**: plan §4.1 列出必须删除的 LLM-facing 文本包括"要求模型缩小/拆分文件、改用较小来源、缩小目录来规避这些 input cap 的 description/message/hint/assertion"。但 scan 正则可能不覆盖：
  1. `_execute_doc_business_value` 第 1207 行的 hint `"缩小文件范围、拆分文件，或改用较小的来源后重试。"`——这个在 scan 正则覆盖范围内（"拆分文件"、"缩小文件范围"）
  2. `list_files` description 第 704 行的 `"必须缩小目录、关闭递归或收紧 pattern 后重试"`——"缩小目录"在正则内
  3. `search_files` description 第 852 行的 `"应分别收紧关键词/目录或改用较小文件后重试"`——"较小文件"在正则内（"较小文件" 匹配 "改用较小" 吗？不匹配。"较小文件" 是完整词，"改用较小文件" 包含它——是的，包含）
- **结论**: 正则覆盖完整。plan 的 scan 策略是正确的
- **但有一个遗漏**: `dayu/config/prompts/base/tools.md` 第 35 行 "大文件先看 `get_file_sections`，避免整文件 `read_file`"——plan §13 正确判断这是导航效率建议（不声称文件会因 size 失败），不属于 rejected guidance。此判断准确
- **严重程度**: 低（已确认无遗漏）

---

### F8-已通过-低-`tools.md` prompt 文件在 R01 范围内确认无需修改

- **位置**: plan §13.2 R03 handoff inventory、§6.2 LLM inventory
- **问题类型**: 契约缺失（被证伪——已正确处理）
- **直接证据**:
  - `dayu/config/prompts/base/tools.md` 的 `<when_tag doc>` 段包含两条指引：
    1. "路径 A：`list_files` → `get_file_sections` → `read_file_section`"——工作流建议，不声称输入限制
    2. "大文件先看 `get_file_sections`，避免整文件 `read_file`"——输出/导航效率建议，不声称文件会因 size 失败或跳过
  - plan §13.2 正确判定该文件为"保留、无 diff"，并给出理由："这是导航/output-efficiency guidance，不声称大文件会失败/跳过，不得让 R03 误删"
- **验证**: 该文件中没有 `directory_entry_limit`、`source_limit`、`skipped_oversized_files`、`source_budget_exceeded` 或任何暗示输入 cap 的文本
- **结论**: plan 的判定准确。保留该 guidance 是正确的——删除 `read_file` 的 source hard-fail 后，"用 get_file_sections 先看结构再精读"仍然是好的 LLM 使用策略
- **严重程度**: 已通过

---

### F9-未修复-低-S1 coverage `--include` 使用 glob `*source*.py` 可能匹配非预期文件

- **位置**: plan §7 baseline 映射表 S1 coverage 行、umbrella plan §7.5 coverage `--include` 列
- **问题类型**: 契约缺失
- **当前写法**: plan §7 说 coverage include 是 `dayu/documents/processors/source_snapshot.py`（精确文件名），但 umbrella §7.5 写的是 `dayu/documents/processors/*source*.py`（glob）
- **问题**: R01 plan §8.5 S1 命令使用精确 `--include='dayu/documents/processors/source_snapshot.py'`（正确）。但 umbrella baseline 的 glob `*source*.py` 在 `source.py`（协议定义）存在的情况下会多匹配一个不应有 coverage 要求的文件。R01 plan 已通过"基于直接证据细化"修正为精确文件名，这是正确的
- **结论**: plan 已正确处理。umbrella baseline 的 glob 是 starting point，accepted sub-WU plan 的精确文件名是 execution truth
- **严重程度**: 低（已正确处理）

---

## 2. 五项重点 adversarial 判断

### 2.1 S1 删除 DocResourceBudget 后暂时直接传目录 cap

**判断**: **非过度设计，切片边界合理。**

详细分析见 F1。两个 slice 解决不同的 root cause（byte budget vs entry cap），有不同的测试矩阵和 coverage 目标。合并为一个 slice 会形成更大原子变更，降低可审查性。中间态行为不变（S1 不改目录 cap），且 plan 明确禁止在 S1/S2 之间暂停交付。

**但有一个实现细节需注意**: `DocResourceBudget.__post_init__` 的 `isinstance(value, bool)` 防御性校验在直接传 `int` 常量时会丢失。S1 implementation 应在 `_route_doc_business` 的 `max_directory_entries` 参数处保留等价校验（或显式记录不需要——因为常量值硬编码且类型明确）。

### 2.2 list 删除 scan_complete/truncated_reason 是否有真实消费者遗漏

**判断**: **无遗漏。**

全仓库 source scan（production/test/README）确认：list 返回值的 `scan_complete/truncated_reason` 字段只在 `doc_tools.py`（producer）和 `tests/tools/test_doc_tools_provider.py`（test consumer）中引用。没有 Host/ToolRuntime/Engine/Service/UI 或其他 production 模块读取这些字段。详见 F2。

**重要区分**: `read_file`/`read_file_section`/`search_files` 的 `scan_complete` 字段（不同语义 owner——字符截断和 result limit）被 plan 正确保留，不受影响。

### 2.3 stable iterator 对 file/directory symlink、containment、I/O、cancel 的语义

**判断**: **directory symlink 语义正确但不完整；file symlink 语义未指定。**

详细分析见 F3。三个子判断：

| 维度 | plan 语义 | 与当前代码的一致性 | 评估 |
|------|----------|-------------------|------|
| 目录 symlink | 不递归跟随 | **改变**（rglob 默认跟随） | 安全改进，但 plan 未记录为安全修复 |
| file symlink（list） | 未指定 | 当前 `is_file()` 返回 True，`stat()` 读 target metadata | **缺失**——list 可能泄露 outside file metadata |
| file symlink（search） | 保留 `_resolve_search_files_candidate` | resolve + containment check | **正确** |
| containment | list 目录参数在 `_project_doc_paths` 校验；search 额外 per-entry resolve+containment | 当前行为 | **保留正确** |
| I/O error | "不吞掉现有 I/O error，不增加 fallback" | 当前 `OSError` on `stat()` 被 catch 并继续 | **正确** |
| cancel | "每个 entry 前观察 cancellation" | 当前 `_raise_if_doc_cancelled` 每 entry 调用 | **正确** |

### 2.4 计划是否过度固定新的 source/directory contract 或昂贵 smoke

**判断**: **否。**

- **SourceSnapshot contract** (§3.1): 自足、完整、无多余抽象。spool/cursor/materialize/cleanup 状态机清晰。未引入 speculative 功能
- **Directory contract** (§3.2/§9.2): 稳定排序 + 不跟随目录 symlink + 取消检查 + 不吞 I/O error。是最小完整契约
- **Smoke** (§11): 34 MiB 磁盘、10,001 inode、预计 5-15 秒。真实发现→callable 验证是关键正确性证明。非过度
- plan §16.2 明确拒绝了 6 种替代方案（更大数字、隐藏错误、流式跳过、顺手做 #177、保留 alias、引入 index/cache），每一项拒绝都有基于 owner/discipline 的理由

### 2.5 所有 accepted contract 是否 code-generation-ready

**判断**: **基本 ready，有 3 个 minor gap。**

| contract | readiness | gap |
|----------|----------|-----|
| `SourceSnapshot` (§3.1) | **ready** | 无。输入/状态机/spool/read/materialize/cleanup/error 全部自足 |
| `doc_tools` source path (§3.2/§8.2) | **ready** | 无。import 变更、参数删除、异常映射删除、search skip 删除全部精确 |
| `doc_tools` directory path (§3.2/§9.2) | **ready with minor gap** | file symlink 语义未指定（见 F3）；iterator 实现 API 未约束（见 F5） |
| `doc_provider` (§3.3) | **ready** | 无。确认无需修改 |
| Host/Engine output (§3.4) | **ready** | 无。保留行为清单明确 |
| 删除清单 (§4.1) | **ready** | 无。逐项列出文件/符号/常量/行为/result/schema/LLM 文本/测试 |
| 保留清单 (§4.2) | **ready** | 无。`allowed_paths`、cancel、process fencing、`DocToolLimits`、`ToolTruncateSpec`、read search partial fields 全部明确 |
| 非目标 (§4.3) | **ready** | 无。Issue #177、新 budget、新 auth、新 schema compat 全部排除 |
| 测试契约 (§8.4/§9.4/§10/§11) | **ready** | 无。E 每项 owner test、consumer test、smoke 的 pass 信号具体 |
| scan 契约 (§12) | **ready** | 无。allowed-file diff、语义/source/LLM/security/Issue-177 scan 命令准确 |
| README decision (§13.1) | **ready** | 无。5 个 README 分别给出 decision + 证据 |

## 3. Open Questions

无 blocking product/owner/dependency/allowlist question。以下为已收敛的非阻塞项：

1. **file symlink 在 list_files 中的行为**（F3）：需 controller 裁决是否需要在 list_files 中增加 per-entry containment check。当前 plan 未指定，建议在 plan fix 中补充
2. **iterator 实现 API 选择**（F5）：建议 controller 确认 `os.scandir` + `DirEntry.is_dir(follow_symlinks=False)` 为实现方向，但不阻塞 plan acceptance
3. **S1 coverage baseline**：umbrella §7.5 的 `*source*.py` glob 已由 R01 plan 精确化为 `source_snapshot.py`，确认这是有意的"基于直接证据细化"

## 4. Residual Risks and Suggested Tracking

| residual | 当前处理 | 建议 |
|----------|---------|------|
| 极大本地 source/目录消耗资源 | 保留 spool/cancel/output limit；不恢复 hard-fail | 同 plan §16.1，正确由 Issue #177 承接 |
| 五工具未完整接 TruncationManager | 保留 current spec；不扩张 R01 | 同 plan §16.1，正确由 Issue #177 承接 |
| search result limit 后未扫描剩余 | schema 自解释；不伪造 total | 同 plan §16.1 |
| symlink/TOCTOU 局部防御 | 保留既有防御；R01 不重设计 | 同 plan §16.1；建议 F3 补充 list file symlink containment |
| S1→S2 中间态 directory cap 仍存在 | 行为不变，不新增 owner | 低风险；建议 implementation artifact 显式记录中间态 |

## 5. Final Plan Review Conclusion

**Verdict: PASS-WITH-MINOR-GAPS**

R01 plan 是 code-generation-ready 的独立实施计划。root cause 证据充分（§2.2 四张表逐项追踪 producer→consumer 传播链），语义 owner 清晰（§3 四个 owner contract 完整），umbrella baseline 逐项映射完整（§7 表格无静默遗漏），production/test/doc allowlist 闭集准确（§6/§8.3/§9.3），删除/保留/非目标清单完备（§4），真实 smoke 设计合理（§11），stop condition 覆盖全面（§15）。

三个 minor gap（F3 file symlink 语义、F5 iterator 实现约束、F6 调用链措辞）均不阻塞 plan acceptance，可在 controller adjudication 后通过 plan fix 补充。五项重点 adversarial 判断全部通过。

**建议的 plan fix 范围**（仅供 controller 参考，不要求全部在 accepted plan 中修复）：
1. §3.2 补充 list_files 对 file symlink 的处理策略（推荐 resolve + containment check）
2. §5.2 修正 `_source_snapshot -> SourceSnapshot` 为更精确描述
3. 可选：§9.2 补充 iterator 实现 API 的方向性建议

**R01 plan 可以进入下一 gate（AgentMiMo 第二路 plan review 完成后 controller adjudication）。**
