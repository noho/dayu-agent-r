# WU-SEMANTIC-OWNERSHIP-01 Remediation Plan Adversarial Review (AgentDS)

## Gate Identity

- **角色**：AgentDS — 独立 plan review，不是 implementation、controller 或 code review
- **审查对象**：`docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`
- **输出**：仅本 artifact；不修改 plan/design/control/README/测试，不 commit/push/PR
- **权威顺序**：AGENTS.md → issues-implementation-control.md → phaseflow-umbrella-optimization-control.md → controller-discussion.md → host/design.md → engine/design.md → tool/design.md → fins/design.md → ui/design.md
- **证据范围**：`b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD`；HEAD=`01bbf74c`

## 审查方法

对计划逐项挑战 12 个维度（见用户指令），每个 finding 必须有：
- 稳定 ID（DS-PF-xx）
- 严重级别（blocking / high / medium / note）
- 直接文件/行号/代码证据
- 为何违反 controller/design/AGENTS
- 最小具体修复

区分 accepted-candidate（计划可接受但需澄清）、question（需回答）、note（观察但非缺陷）。

---

## 总体 Verdict

**计划可进入 implementation，但有 2 个 blocking 问题必须先修复：**

1. **DS-PF-01**：Windows `.cmd` quoting 方案（`subprocess.list2cmdline`）对 cmd 特殊字符 `&|^%!()` 不安全——这不是理论 corner case，财报文件路径完全可以包含这些字符。
2. **DS-PF-02**：R07 中 `_SOURCE_SNAPSHOT_MAX_ATTEMPTS = 3`、`SourceSnapshotChangedError`、`_CachedProcessor` snapshot lease 等是 speculative design，当前代码零证据。

共 **12 个 finding**：2 blocking、3 high、5 medium、2 note。无 blocking question 需要用户回答（所有 blocking 都是 plan 内部缺陷，不需外部决策）。

---

## Findings

### DS-PF-01 — BLOCKING — `subprocess.list2cmdline` 对 Windows `.cmd` batch 脚本不安全

- **严重级别**：blocking（会使生成的 `.cmd` 脚本在路径含 `&|^%!()` 时不可执行或执行错误命令）
- **涉及 plan 位置**：R11 §18.2 第 873 行："Windows...使用 `subprocess.list2cmdline`等价的cmd quoting。不得手写脆弱replace。"
- **涉及设计/控制**：controller discussion Topic 7.1 要求 "Safe argv quoting"；UI design §2 要求 "路径中的空格、引号及 shell 特殊字符不得改变 argv 边界"；[Issue #175](https://github.com/noho/dayu-agent-r/issues/175) 虽不在本 WU，但安全 quoting 不依赖该 issue。
- **直接证据**：

```python
# 实际测试
import subprocess
test_arg = 'report_2024_Q4 & review (final) | v2.pdf'
cmdline = subprocess.list2cmdline(['python', '-m', 'dayu.cli', 'upload_filing', '--path', test_arg])
# 输出: python -m dayu.cli upload_filing --path "report_2024_Q4 & review (final) | v2.pdf"
```

在 `.cmd` batch 文件中，`&` 是命令链操作符，`|` 是管道，`(` `)` 是分组——上述输出会**执行多条命令**而非传给单个 `--path` 参数。

- **为什么 `list2cmdline` 不足**：`subprocess.list2cmdline` 遵循 MS C runtime 规则（文档见 `help(subprocess.list2cmdline)`），只处理空格与双引号转义。它**不**转义 cmd.exe 的 shell 元字符。这正是 `list2cmdline` 文档说明的用途：为 `CreateProcess` 准备命令行字符串，不是为 `.cmd` batch 脚本生成安全内容。`.cmd` 脚本的 `%*` 转发同样不保护这些字符。

- **独立测试确认**：
  - `file&special.pdf` → `file&special.pdf`（无引号，`&` 变为命令分隔符）
  - `file|pipe.pdf` → `file|pipe.pdf`（`|` 变为管道）
  - `file^caret.pdf` → `file^caret.pdf`（`^` 是 cmd 转义符，但只在特殊字符前生效，独立出现是字面量——行为不确定）
  - `file%percent.pdf` → `file%percent.pdf`（在 batch 中 `%` 触发变量展开）
  - `file!excl.pdf` → `file!excl.pdf`（启用延迟展开时 `!` 触发变量展开）

- **最小修复**：计划必须：
  1. 承认 `subprocess.list2cmdline` 对 `.cmd` batch 脚本不够。
  2. 定义最小安全 `.cmd` 转义规则。至少对 `%` 加倍为 `%%`（batch 变量展开），对 `&|<>^` 用 `^` 转义，对 `!` 在显式 `setlocal enabledelayedexpansion` 不存在时认定为安全（默认禁用），或要求 batch 脚本添加 `setlocal disabledelayedexpansion`。
  3. 在 R11-S2 的跨平台 smoke 中加入对抗性 argv 测试（路径含 `&|^%!()` 的 `.cmd` 在 Windows CI 中实际执行并通过 fake `dayu-cli` recorder 比对）。
  4. 评估是否可以用 `^"..."^"` 包裹含特殊字符的路径（`^"` 转义双引号使其在 cmd 中被视为字面引号）。

- **注意**：该 finding 不要求删除 `subprocess.list2cmdline`（POSIX `shlex.quote`/`shlex.join` 对 `/bin/sh` 是正确的）。只要求补充 Windows `.cmd` 安全转义，不得统称为 "cmd quoting"。

---

### DS-PF-02 — BLOCKING — R07 snapshot retry、新类型、lease 是 speculative design

- **严重级别**：blocking（计划引入了多个当前代码库中不存在的类型、常量与机制，没有 controller/design 裁决依据）
- **涉及 plan 位置**：R07 §14.3 第 681 行：`_SOURCE_SNAPSHOT_MAX_ATTEMPTS = 3`、`SourceSnapshotChangedError`、`SourceDocumentSnapshot`（context-managed）、`_CachedProcessor` snapshot lease
- **涉及设计/控制**：controller discussion Topic 6.3 只授权 "Move revision/snapshot ownership fully into storage"，没有授权具体 retry 次数、snapshot lease 生命周期或新的 typed error；fins/design.md §4 只授权 "有界内部重试" 与 "typed `source_changed_during_read`"
- **直接证据**：

```bash
rg -n '_SOURCE_SNAPSHOT_MAX_ATTEMPTS|SourceSnapshotChangedError|SourceDocumentSnapshot' dayu/
# (零结果 — 当前代码库中完全不存在这些符号)
```

当前代码的 revision 一致性实现（`dayu/fins/tools/read_runtime.py`）使用 revision-before/after 双读+零重试 fail，与计划描述的 3 次重试+file digest 校验+snapshot lease 完全不同。计划引入的机制至少包含：
- 内部命名常量 `_SOURCE_SNAPSHOT_MAX_ATTEMPTS = 3`（数值 3 的来源？为什么不是 2 或 5？）
- 新的 typed error `SourceSnapshotChangedError`（与现有 `source_changed_during_read` 的关系？）
- Context-managed `SourceDocumentSnapshot`（与现有 read path 的集成边界？）
- `_CachedProcessor` snapshot lease 与 eviction close（cache 模块的新 contract？）

- **为何这不是 controller/design 授权的**：controller 只裁决了 "read consumers must not hash selected fields or own a second before/after version protocol" 和 "storage-owned snapshot/version returned with the source, or a bounded retry, may be simpler"（后者是建议，不是裁决）。fins/design.md §4 说 "read boundary 可以做有界内部重试以取得稳定 snapshot；只有无法取得稳定版本时才返回 typed `source_changed_during_read`"——但未指定重试次数、snapshot API 形态或 cache lease 生命周期。

- **最小修复**：
  1. 将 `_SOURCE_SNAPSHOT_MAX_ATTEMPTS = 3` 标记为实现细节（不在计划中固定），实现 agent 可以选 3 作为合理初值，但需在 R07 completion report 中说明选择理由。
  2. 删除 `SourceSnapshotChangedError` 的新类型引入——复用 fins/design.md 已授权的 `source_changed_during_read` typed error。
  3. `SourceDocumentSnapshot` 的 context manager 语义如果只是 `open_source_snapshot()` 返回一个带有 `close()` 的对象的语法糖，可以保留为内部细节；但必须在计划中注明 "形态为实现细节" 而非作为公共 contract。
  4. `_CachedProcessor` snapshot lease：如果当前 cache 已支持 lease/eviction，可以作为实现细节；如果要求新增 cache 模块 contract，必须先由 R07-S3 的允许文件集验证 `cache.py` 是否已在 allowlist 中（它已在 R07 allowlist：`dayu/fins/tools/cache.py`）。

**注意**：这不是反对 storage-owned snapshot/revision 方向（该方向 controller 已裁决且正确）。问题是计划把数值、新类型名和生命周期细节固定为 plan-level 契约，而这些没有 controller/design/代码证据支撑。

---

### DS-PF-03 — HIGH — 安全 retained/modified matrix 缺失跨平台 quoting 与 Windows env 写原子性

- **严重级别**：high（安全清单缺少两个已识别的边界风险）
- **涉及 plan 位置**：§21 安全 retained/modified 行为清单；§23 residual risk
- **涉及设计/控制**：UI design §2（argv quoting）、§3（init atomicity）；controller Topic 7
- **直接证据**：
  1. §21 第 1060 行写了 "CLI upload script atomic write/quoting"，但 §23 第 1156 行只把 "Windows env写与POSIX profile/config无法形成跨资源全局原子事务" 列为 residual risk，没有把 **Windows `.cmd` quoting 的 cmd 元字符安全**（DS-PF-01）列为安全清单独立条目。
  2. §21 列了 16 个行为，但未覆盖：**跨平台脚本在路径含 shell 元字符时 argv 边界不变的 owner-level 验收标准**。这是 UI design §2 的明确要求。

- **最小修复**：
  1. §21 新增条目："CLI upload script platform-specific quoting (POSIX `shlex.quote` / Windows cmd metachar escaping)"，disposition=retained/new contract，验收=adversarial argv smoke
  2. §23 residual risk 补充 Windows `.cmd` quoting 的已知局限（在极端路径名下的边缘行为，如路径同时含 `%` 和 `!` 且启用延迟展开时），并指明其 owner（R11 CLI owner）

---

### DS-PF-04 — HIGH — R03 LLM source scan 覆盖范围不可验证

- **严重级别**：high（计划要求扫描 `dayu/config/prompts/**` 等大量文件，但扫描谓词仅覆盖已知反模式，可能漏报）
- **涉及 plan 位置**：R03 §10.4 S2 第 441-451 行；§7.5 第 219 行 scan 命令
- **涉及设计/控制**：AGENTS.md LLM-facing 文本约束；controller Topic 3 要求 "Source audit is part of the fix scope, not optional follow-up"
- **直接证据**：
  - R03-S2 的 scan 命令（§7.5 第 219 行）：`rg -n 'llm_safe_replay_arguments|arguments_summary_unsafe|api_key.*token.*secret.*password|unsafe.argument' dayu tests`
  - 此 scan 只能发现：
    - 代码中的 `api_key`/`token`/`secret`/`password` 敏感字段名出现（但无法区分它是作为 LLM-facing tool schema 参数还是内部 config key 出现）
    - 已废弃的 `llm_safe_replay_arguments` 调用
  - **不能发现**：
    - 用 `credential`/`cookie`/`auth`/`session`/`bearer` 等非匹配名暴露的 secret（controller Topic 3 明确指出了这个问题）
    - tool schema description 中暴露的内部状态/治理术语
    - prompt fragment 中要求模型理解内部模块名或实现术语

- **计划本身的 guards**：计划 §10.3 第 423 行写了 "当前生产 tool schemas 不应把 API key/password/token secret 暴露为 LLM 参数；若 source scan 找到真实 secret 参数，必须在该 tool schema/producer owner 删除或改成 config ref"——这是正确的方向，但 scan 谓词无法保证完整性。

- **这是否是计划缺陷**：部分。controller 要求的 source audit 是完整的人工+自动化审查，不是只靠 grep。计划可以接受，但需要明确：
  1. R03-S2 的 scan 是最小自动化门禁，不是完整 audit。
  2. R03 implementation 必须附加人工逐文件审查 `dayu/config/prompts/**`、所有 `ToolDefinition` name/description、Host/Engine tool message renderers、以及测试中的真实 LLM smoke prompt fixtures。
  3. 人工审查结果必须进入 R03 completion report。

- **处置**：accepted-candidate — 计划方向正确，但需要补充人工审查承诺。不做此补充，scan-only 验证不满足 controller Topic 3 的 "Source audit is part of the fix scope" 要求。

---

### DS-PF-05 — HIGH — R11 cross-platform smoke 将 Windows 验证推迟到 CI 但不定义 CI 触发条件

- **严重级别**：high（计划承认 Windows smoke 无法在当前开发环境完成，但未定义 CI gate 是什么、谁来运行、失败如何处理）
- **涉及 plan 位置**：R11 §18.3 S2 第 902 行："非Windows开发机可单测 quoting，但不能宣称完成Windows smoke，必须等CI"
- **涉及设计/控制**：UI design §1 要求入口在发布前有 "smoke tests"；issues-implementation-control.md 要求 umbrella gate 不可被外部依赖阻塞
- **直接证据**：计划 §22.1 的 smoke 矩阵要求 "CLI upload: POSIX实执行 + Windows CI cmd" 通过，但 R11 是 sub-WU 级别 gate，其独立完成信号（§7.3）要求 "真实 smoke 通过"。如果 R11 的 smoke gate 依赖未定义的 CI，sub-WU 就无法独立 closure。

- **最小修复**：
  1. R11 completion 条件中明确：POSIX smoke 是 blocking gate；Windows smoke 若 CI 不可用，先用 unit test 验证 quoting 逻辑（adversarial argv → 生成 `.cmd` → 解析验证转义正确性），然后记录 "Windows CI pending" 作为 residual。
  2. Windows 实际执行 smoke 必须在 aggregate gate 前完成，不推迟到 PR 之后。
  3. 补充说明：若 Windows CI runner 根本不存在，谁负责搭建、何时搭建。

---

### DS-PF-06 — MEDIUM — Topic coverage 完整性：R08 未覆盖 controller 要求的 "raw XBRL total 不进 LLM"

- **严重级别**：medium（controller 明确要求，计划覆盖了但证据链弱）
- **涉及 plan 位置**：R08 §15.2 第 740 行；§15.3 S1 第 755 行
- **涉及设计/控制**：fins/design.md §6；controller Topic 6.4 要求 "raw provider `total` 只作 producer协议校验/diagnostic，不进 LLM-facing result"
- **直接证据**：
  - 计划 R08-S1 的 scan（§7.5 第 232 行）要求 `raw_total` 在 public/LLM path 零残留
  - 但计划未说明**当前代码中 `total` 是通过什么路径暴露给 LLM 的**（是 XBRL result schema 字段？read runtime 投影？tool description 文本？）
  - R08-S2 第 765 行的 scan 命令 `statement_locator|statement_method_missing|raw_total|deduped_count` 的零残留是可验证的，但 "raw total 仅 internal，不进 LLM" 的正面断言（即：internal diagnostic trace 中仍然存在 `total`，只是 public typed result 不含）需要更精确的验证——不是零残留，而是**只在 internal 路径残留**

- **最小修复**：R08 completion report 必须区分：
  1. public/LLM-facing output：`raw_total` 零残留（硬要求）
  2. internal diagnostic/producer validation：`total` 保留（允许）
  并提供具体的 grep 命令区分这两类残留。

---

### DS-PF-07 — MEDIUM — R09 validator 状态机的 late-progress-after-result 语义与 R05 的 late-publication fence 存在交互但不交叉验证

- **严重级别**：medium（两个状态机各自正确，但计划未要求交叉测试）
- **涉及 plan 位置**：R05 §12.2（wait observation timeout → late publication token reject）；R09 §16.2（direct stream EVENT_AFTER_RESULT fail closed）
- **涉及设计/控制**：fins/design.md §7；host/design.md wait state machine
- **直接证据**：两者都是 "迟到事实被拒绝" 的模式，但作用于不同层级：
  - R05：observation timeout 后 late callback → token 被拒，不可发布
  - R09：RESULT 后的 late progress → `EVENT_AFTER_RESULT` error
  - 如果 ingestion runtime 的 wait observation 在 R05 timeout 后仍然产出了 late result，而 direct stream 的 validator 此时处于 RESULT_BUFFERED，validation 的 FAIL 和 wait 的 reject 可能独立发生，形成两个不同错误路径。这不一定是 bug，但计划没有要求验证两者在组合场景下的一致性。

- **最小修复**：在 aggregate smoke 矩阵（§22.1）中增加一个场景：R05 observation timeout + R09 duplicate result，验证 terminal error identity 唯一且不冲突。不作为 blocking——当前 state machine 设计没有明显矛盾，只是缺少交叉验证。

---

### DS-PF-08 — MEDIUM — 12 sub-WU / 30 slices 切分合理性：R01 与 R03 的耦合隐式正确但未声明

- **严重级别**：medium（R01 删除 Doc LLM-facing cap 文案后，R03 的 LLM source scan 需要知道 R01 已经删除了哪些文案，否则可能重复审计或漏审计）
- **涉及 plan 位置**：§5 owner map 第 119 行说 "R01、R02、R03 可在独立分支顺序实施"；§6 sequencing 第 144 行说 "R01、R02、R03 可在独立分支顺序实施，但进入 umbrella aggregate 前必须 rebase 到同一已审基线"
- **涉及设计/控制**：AGENTS.md 语义所有权约束："多个消费者需要同一语义时，必须复用同一个 source of truth"
- **直接证据**：
  - R01-S2 的 scan（§7.5 第 213 行）：`rg -n 'directory_entry_limit|source_limit|skipped_oversized_files|10_000' dayu tests README.md`
  - R03-S2 的 scan（§7.5 第 219 行）：`rg -n 'llm_safe_replay_arguments|...' dayu tests`
  - 这两个 scan 不重叠。但如果 R01 先实施删除了 Doc tool description 中的 `source_limit`/`directory_entry_limit` 文案，而 R03 随后审查 prompt/schema 中的 LLM-facing 文本时看到了**已经修改后的**文件，R03 不会知道这些文本曾经存在过——这实际上是对的（R03 审查的是最终状态）。但反过来：如果 R03 先实施，它可能对 "LLM-facing 文本中包含 `source_limit` 等词" 做出删除裁决，而 R01 随后实施时又删除了同一段文本的剩余部分，导致冲突。

- **是否实际风险**：低——因为 R01 和 R03 删除的是不同 owner 的内容（R01 删除 Doc tool schema/description 中的 cap 文案；R03 删除 Host projection 中的 repair 逻辑和 prompt/schema 中的 secret/internal ref）。但 rebase 是在 aggregate 前，不是每个 sub-WU 完成后。

- **处置**：accepted-candidate — 当前 sequencing 规则（第 144 行）已明确要求 aggregate 前 rebase。建议 R01 completion report 中列出其删除的 LLM-facing 文本清单，作为 R03 实施时的已知输入。

---

### DS-PF-09 — MEDIUM — R11-S1 OLD-aligned 分类中 "call材料最多对应已识别report数量" 缺乏 OLD 代码直接引用

- **严重级别**：medium（计划声称 OLD-aligned 但未引用具体 OLD 代码行号）
- **涉及 plan 位置**：R11 §18.2 第 869 行
- **涉及设计/控制**：controller Topic 7.1 要求 "Keep Fins-owned typed scanning/classification and use OLD as the product-behavior reference"
- **直接证据**：OLD 代码已确认：
  ```python
  # /Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py:1540-1542
  material_caps: dict[str, int] = {
      "EARNINGS_PRESENTATION": _UPLOAD_MAX_PRESENTATION,  # 6
      "EARNINGS_CALL": len(recognized_entries),           # = annual+periodic count
  }
  ```
  以及：
  ```python
  # /Users/leo/workspace/dayu-agent/dayu/fins/upload_recognition.py:120-124
  _UPLOAD_MAX_ANNUAL: int = 5
  _UPLOAD_MAX_PERIODIC: int = 6
  _UPLOAD_MAX_PRESENTATION: int = 6
  ```

- **计划描述的准确性**："annual最多5、periodic仅最新年度且最多6、presentation最多6、call材料最多对应已识别report数量" — **与 OLD 代码完全一致**。但 OLD 还有两个细节未在计划中出现：
  1. `FINANCIAL_STATEMENTS` material type 在 OLD 中**无数量上限**（不在 `material_caps` dict 中，全部保留）
  2. 优先级的 "同期去重" 由 `_pick_best_per_period`（`upload_recognition.py`）实现，不是简单的时间排序

- **最小修复**：在 R11 §18.2 中补充：
  1. OLD 具体代码引用：`/Users/leo/workspace/dayu-agent/dayu/fins/cli_support.py:1540-1542` 和 `upload_recognition.py:120-124`
  2. 明确声明 `FINANCIAL_STATEMENTS`（若有）无数量上限
  3. 明确同期去重由 `_pick_best_per_period` OLD 等价逻辑实现

---

### DS-PF-10 — MEDIUM — R12 init catalog 的 model ID 列表可能已在当前 packaged config 中过时

- **严重级别**：medium（计划冻结了具体 model ID 字符串，但控制器要求 "具体ID必须以当前 packaged model contract为准"）
- **涉及 plan 位置**：R12 §19.2 第 934-950 行 catalog 表格
- **涉及设计/控制**：controller Topic 7.3 要求 "Provider 菜单、模型组合和 API key ref 必须从一个 init-owned typed catalog/contract 产生"
- **直接证据**：计划第 934 行写 "具体ID必须以当前 packaged model contract为准，若catalog所需ID缺失则同slice补到 current schema并由ConfigLoader验证，不加旧schema别名"。这是正确的自修正机制。但 catalog 表中的具体字符串（如 `mimo-v2.5-pro-plan`、`deepseek-v4-pro`、`claude-sonnet-4-6` 等）是否与当前 `dayu/config/models.json` 一致，plan 未提供对照证据。

- **处置**：note — 计划已内建 "若 catalog 所需 ID 缺失则同 slice 补到 current schema" 的自修正逻辑，因此实际 implementation 会核对。但建议 R12-S1 的第一步就是 diff `models.json` 与 plan catalog，把差异写入 completion report。

---

### DS-PF-11 — NOTE — 计划对 Issue 151（assets）与 reset 的边界处理正确但措辞需对标 controller

- **严重级别**：note（确认计划处理正确，微调措辞）
- **涉及 plan 位置**：§4 第 95 行；R12 §19.3 第 977 行
- **涉及设计/控制**：controller Topic 7.3 明确说："Align `--reset` with OLD: show `.dayu`, `config`, and **product-present `assets`** targets and require explicit confirmation, then delete those Dayu-owned/reconstructable roots... **The current repository has no `dayu/assets`**; do not import unimplemented write/template product surface only to mimic an OLD directory. Issue #151 owns write and its required assets."
- **直接证据**：
  - 计划 §4 第 95 行将 Issue 151 列为 "deferred：workspace assets"
  - 计划 R12 §19.3 第 977 行说 "永不删除portfolio"
  - 但计划**未明确复述** controller 的关键裁决：如果当前仓库没有 `assets` 目录，reset 不应该报错或创建它；只有当产品未来有了 `assets`（通过 Issue 151），reset 才应按 OLD 行为删除并重建

- **处置**：accepted-candidate — 计划的 "永不删除portfolio" + "Issue 151 deferred" 逻辑覆盖了 controller 意图。但建议在 R12 §19.3 第 977 行后加一句："当前仓库无 `dayu/assets`，reset 不应要求其存在或创建空目录；Issue 151 交付后，reset 白名单扩展至 assets 属于该 issue scope。"

---

### DS-PF-12 — NOTE — 计划正确避免了 6 类常见 plan review 缺陷

- **严重级别**：note（正面确认）
- **涉及范围**：全部 plan 章节

以下检查项均通过，无需单独 finding：

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| Topic 8 未越界 | ✅ | §4：Topic 8 标记为 no code；aggregate guard 只做 regression |
| Topic 9 未越界 | ✅ | §3 明确 "不设计或实现统一 tool authorization framework"；§21 security matrix 每项归 retained/modified |
| Issue 142/151/175/177/178 未越界 | ✅ | §4 追踪表每项标记 deferred + issue owner；§3 非目标明确排除 |
| Web/WeChat/render tracker 未越界 | ✅ | §4 Topic 7.2 标记删除 placeholder，不实现 tracker；§3 明确不搬入本 WU |
| 不新增统一授权框架 | ✅ | §3、§21、controller Topic 9 一致 |
| R03 合并 Topic 3/4 合理 | ✅ | §5 第 119 行解释：共享同一 accepted-evidence LLM projection + 四个 downstream consumers；拆开会产生中间态 |
| R06 合并 batch authority + source publication 合理 | ✅ | §5 第 119 行解释：transaction commit point 和 complete source 唯一可见点必须同时切换 |
| 每个 sub-WU ≤3 slices | ✅ | §5 表格：R10=1 slice，R01/R05/R08/R09=2 slices，其余=3 slices |
| Config→composition→behavior sequencing | ✅ | §6 sequencing 规则 1-5 层次分明 |
| Provider mode 不按 tool name/scene 反推 | ✅ | R04-S1 §7.5 scan："provider mode不得从tool name/scene反推" |
| Scene-derived policy 删除 | ✅ | R04-S3 §7.5 scan：`with_entrypoint_wait_poller_policy`零残留 |
| 无兼容 schema/旧测试/fallback | ✅ | §3 非目标明确排除；AGENTS.md 禁止兼容性代码 |
| Completion report format | ✅ | §24 格式完整，禁止 "tests pass" |
| Aggregate deepreview 覆盖 adversarial failure pass | ✅ | §22.2 列出 correctness/stability/maintainability/adversarial failure pass |
| Residual risk 不降 accepted contract 为 partial | ✅ | §23 第 1161 行明确此约束 |

---

## 用户指令 12 维度逐项回答

### 1. Topic 1-7 完整性 / Topic 8-9 / Issue 边界

**通过，有 note。** Topic 1-7 的 accepted code fixes 全部有对应 R01-R12 sub-WU 覆盖（§4 追踪表逐行映射到 sub-WU）。Topic 8-9、Issue 142/151/175/177/178 全部标记 deferred 或 no-code，并在 §3 非目标与 §4 追踪表中明确排除。Web/WeChat/render tracker 不被本 WU 实现。

潜在问题：见 DS-PF-11（R12/assets 措辞微调）。

### 2. 12 sub-WU / 30 slices 切分

**通过，有 note。** 合并理由（R03=R3+R4、R06=R6.1+R6.2、R07=R6.3+R6.7）均有语义 owner 依据。最大 3 slices/sub-WU 的约束满足。R01 与 R03 的交互见 DS-PF-08，风险低。

潜在问题：DS-PF-02（R07 的 speculative design 影响其 slice 数量——如果 `SourceDocumentSnapshot` 是新 public contract，R07 的 3 slices 可能不够）。

### 3. Sequencing 可实现性

**通过。** config→composition→behavior（R04→R05）、Fins transaction→complete publication→snapshot/read→domain/terminal/HKEX（R06→R07→R08/R09/R10）、CLI upload/init（R11/R12）的依赖图合理。no duplicate owner/downstream fallback。

### 4. R03 LLM-facing 修复是否回到 prompt/tool schema/producer owner

**通过，有修复需求。** 计划方向正确：删除 Host blacklist repair，优先使用 producer semantic query，否则使用 schema-owned canonical arguments。opaque refs internal-only。未创建另一套 normalization。

潜在问题：DS-PF-04（source scan 谓词覆盖不足，需补充人工审查承诺）。

### 5. Security retained/modified matrix 完整性

**需修复。** 见 DS-PF-01 和 DS-PF-03。核心问题：Windows `.cmd` quoting 方案不安全，且安全矩阵未将跨平台 quoting 列为独立 retained behavior。

其余 retained 行为（allowed_paths、containment/symlink、DNS/peer/resource budget、atomic/process fencing）全部正确列出且无删除。没有实现统一 authorization framework。

### 6. Speculative design 检查

**发现 speculative design。** 见 DS-PF-02。`_SOURCE_SNAPSHOT_MAX_ATTEMPTS = 3`、`SourceSnapshotChangedError`、`_CachedProcessor` snapshot lease 无当前代码证据。

其余设计元素（provider mode enum、host_runtime.json 字段名、R02 config 字段名与默认值、R12 catalog 表）均有 controller/design/OLD 代码直接证据。预算数值有 "财报页面需要较大默认值" 的业务理由。

### 7. Reset 删除 Dayu-owned .dayu/config/assets

**通过。** 计划 §19.3 正确处理：reset 删除 `.dayu`、`config`、product-present `assets`；永不删除 portfolio。Issue 151 deferred 正确。见 DS-PF-11（措辞微调建议）。

没有错误地把 assets 全部 deferred——reset 行为是 "如果存在则删，不存在不报错"，assets 的**创建和内容**归 Issue 151。

### 8. Windows .cmd quoting

**BLOCKING。** 见 DS-PF-01。`subprocess.list2cmdline` 不足以保证 `.cmd` batch 脚本安全执行。必须补充 cmd 元字符转义方案。

### 9. upload_filings_from 和 init 的 OLD-aligned 行为

**通过，有 minor 补充建议。**

upload_filings_from：
- 分类规则（annual≤5、periodic≤6、presentation≤6、call≤recognized count）与 OLD 一致 ✅
- 默认 output（`--base` workspace root 下含 ticker 的文件名）✅
- argv grammar（`python -m dayu.cli upload_filing|upload_material` 而非 JSON schema）✅
- 重生成注释 ✅
- 用户摘要（recognized/material/skipped counts）✅

init：
- provider/model/API key 交互选择 ✅
- optional Web/FMP/HF prewarm ✅
- preserve/overwrite/reset/lock/atomic rollback ✅
- 细节：DS-PF-09（OLD 代码引用补充）、DS-PF-10（catalog 与 current models.json 核对）

### 10. 测试命令、coverage、pyright、README、scan、smoke 闭合性

**通过，有 CI 依赖。** 每个 slice 有明确的 `pytest` 命令、`--include` coverage 集合、source scan 命令、README decision 表。文件路径与 §7.4 closed manifest 一致。

潜在问题：DS-PF-05（Windows CI 依赖未定义）。

### 11. Sub-WU plan→双 review→fix→双 re-review 流程一致性

**通过。** 计划 §7.3 要求每个 sub-WU 完成两路独立完整 code review（不是 aggregate 替代）。§7.1 要求先写/更新 owner-level contract tests。§22.2 要求 aggregate deepreview 前所有 sub-WU 双路 review 通过。计划没有用 umbrella 总计划替代每个 sub-WU 的 plan gate——§26 明确 plan gate 只允许进入 "独立 plan review gate"，然后由 umbrella controller 按 sub-WU 逐个推进。

与用户要求的 flow 一致：plan→双 review→fix→双 re-review→implementation→双 code review→fix→双 re-review→accepted commit。

### 12. 反例、failure injection、并发、取消、durable/LLM/state 一致性

**通过，有补充建议。**

- 反例/failure injection：R01（声明长度大但实际小）、R02（mix DNS、proxy conflict）、R05（late publication）、R06（crash recovery 每 phase）、R07（concurrent writer/reader 混合版本）、R09（missing/duplicate）、R11（adversarial argv）均有覆盖。
- 并发：R06（concurrent ticker lock）、R07（concurrent publish + read）、R12（两个 init 进程）。
- 取消：R01（cancellation terminates without faking complete）、R05（observation timeout + backoff）、R09（cancel doesn't synthesize second terminal）。
- durable/LLM/state 一致性：R03（ordinary/awaiting 同一 request atom → RunInput/Memory/Compact/Trace 同一投影）、R06（crash recovery 只见完整 A 或 B）、R07（snapshot 内所有 files 同一 revision）。

见 DS-PF-07（R05+R09 交叉场景未验证）。

---

## Finding 统计

| ID | 级别 | 类别 | 简述 |
| --- | --- | --- | --- |
| DS-PF-01 | **BLOCKING** | Windows quoting | `subprocess.list2cmdline` 对 `.cmd` 不安全 |
| DS-PF-02 | **BLOCKING** | Speculative design | R07 snapshot retry/新类型/lease 无代码证据 |
| DS-PF-03 | HIGH | Security matrix | 跨平台 quoting 未列入 retained matrix |
| DS-PF-04 | HIGH | R03 LLM scan | Source scan 谓词覆盖不足，需人工审查 |
| DS-PF-05 | HIGH | CI dependency | Windows smoke 依赖未定义的 CI gate |
| DS-PF-06 | MEDIUM | R08 contract | raw total internal/public 残留区分需澄清 |
| DS-PF-07 | MEDIUM | Cross-WU | R05+R09 交叉场景未验证 |
| DS-PF-08 | MEDIUM | Sequencing | R01→R03 隐式耦合未声明 |
| DS-PF-09 | MEDIUM | R11 OLD ref | OLD 代码引用缺失，细节补充 |
| DS-PF-10 | MEDIUM | R12 catalog | catalog model ID 与 current models.json 一致性 |
| DS-PF-11 | NOTE | R12/assets | 措辞微调建议 |
| DS-PF-12 | NOTE | 正面确认 | 6 类常见 plan 缺陷已正确避免 |

**Blocking: 2** | **High: 3** | **Medium: 5** | **Note: 2**

---

## Final Verdict

计划在语义所有权切分、sequencing、deferred/no-code 边界控制、安全 retained matrix 和每个 sub-WU 的验证闭环方面是**审慎且充分的**。两个 blocking finding（DS-PF-01、DS-PF-02）都是计划内部可修复的设计缺陷，不需要重新打开 controller 裁决或开始新的 design WU。

修复 DS-PF-01（Windows quoting）和 DS-PF-02（speculative design 降为实现细节）后，本计划可以进入 implementation。

三个 high finding（DS-PF-03、DS-PF-04、DS-PF-05）建议在 plan 修订中一并处理，但不应阻塞 implementation gate——它们可以在对应 sub-WU 的 plan review 中细化。

**无 blocking question 需要用户回答。** 所有 blocking 都是 plan 内部的技术缺陷，有明确的最小修复路径。
