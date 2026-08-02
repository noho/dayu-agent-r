# WU-CLI-CONFORMANCE-F01-F07 S3 Plan Correction — 独立 Adversarial Plan Review（DS）

## 0. Review 元数据

- **Reviewed target**: `docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-codex.md`
- **Parent plan**: `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`（未提交修订，§5 S3）
- **Blocked implementation artifact**: `docs/reviews/wu-cli-conformance-f01-f07-s3-implementation-codex.md`
- **Work unit**: `WU-CLI-CONFORMANCE-F01-F07`
- **Slice**: `S3 / F03`
- **Branch**: `codex/interactive-oracle`
- **Gate**: Plan correction review（第二轮独立 plan re-review 前的 adversarial pass）
- **Review posture**: adversarial，默认怀疑；目标不是证明 plan 可行，而是寻找最强反例
- **执行日期**: 2026-08-02（Asia/Shanghai）
- **Review 模型**: deepseek-v4-pro

## 1. Review Scope 与禁止动作

本 review 只检查 S3 plan correction 是否 code-generation-ready。重点 adversarial review：

- public feed/flush callback batch 是否足以区分 standalone Escape 与 Alt continuation
- 跨 chunk、同 raw read 多按键、CSI/SS3/Home/Delete、bracketed paste、Alt+Ctrl+T
- deadline/readable/close race
- 是否坚持单 parser/decoder、reader-thread owner
- 是否影响 acceptance barrier、double Ctrl+C、Host terminal owner

**禁止动作**：不改 plan、production、tests、oracle/scenario，不 stage/commit/push。

## 2. 审查依据

### 2.1 直接复验的证据

以下结果均通过当前 resolved dependency（`prompt_toolkit==3.0.52`，Python 3.11）的 public API 直接复验：

| 输入与 boundary | callback batch（实测） | 结论 |
|---|---|---|
| `feed(ESC)` | `[]` | 与 plan 一致 |
| deadline `flush()` | `[Escape(data="\x1b")]` | 与 plan 一致 |
| `feed(ESC + x)` | `[Escape("\x1b"), 'x']` | 与 plan 一致 |
| 跨 chunk `feed(ESC)` / `feed(x)` | 第二个 feed = `[Escape("\x1b"), 'x']` | 与 plan 一致 |
| `feed(ESC [ D)` | `[Left("\x1b[D")]` — 单 callback，无 Escape | 与 plan 一致 |
| `feed(ESC O H)` | `[Home("\x1bOH")]` — 单 callback，无 Escape | 与 plan 一致 |
| `feed(ESC [ 3 ~)` | `[Delete("\x1b[3~")]` — 单 callback，无 Escape | 与 plan 一致 |
| Known meta tuple `ESC [ 1 ; 3 H` | `[Escape("\x1b[1;3H"), Home("")]` | 与 plan 一致 |
| `feed(ESC + x + Ctrl+T)` | `[Escape("\x1b"), 'x', ControlT("\x14")]` | 与 plan 一致 |
| `feed(ESC + Ctrl+T)` | `[Escape("\x1b"), ControlT("\x14")]` | 与 plan 一致 |
| Bracketed paste | `[BracketedPaste(payload)]` — 单 callback | 与 plan 一致 |
| 跨 chunk paste | start+content 无 callback；end 一个 `BracketedPaste` | 与 plan 一致 |
| Alt+Unicode (é) | `[Escape("\x1b"), 'é']` | 与 plan 一致 |
| 空 flush | `[]` | 与 plan 一致 |

上游 3.0.52 `test_inputstream.py` 的 `test_escape`、`test_flush_1`、`test_flush_2`、`test_special_double_keys`、`test_meta_arrows`、`test_invalid` 全部与上述实测一致。

### 2.2 关键 parser 内部事实

- `Vt100Parser` 内部使用 generator-based state machine（`_input_parser_generator`），通过 `_IS_PREFIX_OF_LONGER_MATCH_CACHE` 判断当前 prefix 是否为更长匹配的前缀。
- `feed("\x1b")` 不产生 callback 的原因是 `_IS_PREFIX_OF_LONGER_MATCH_CACHE["\x1b"]` 为 `True`（ESC 是所有 escape sequence 的前缀），且 `flush()` 未到达。
- `feed("\x1bx")` 产生 `[Escape, 'x']` 的原因是 `\x1bx` 不是任何已知 ANSI sequence 的前缀（`_IS_PREFIX_OF_LONGER_MATCH_CACHE["\x1bx"]` 为 `False`），parser 回退并匹配最长已知前缀（`\x1b`→Escape），剩余 `x` 作为普通字符。
- Ctrl+T (`\x14`) 在 ANSI_SEQUENCES 中映射为 `Keys.ControlT`，不是 escape sequence 前缀。因此 `ESC + Ctrl+T` 的解析与 `ESC + x` 完全相同：先产生 Escape，再产生 ControlT。

### 2.3 ANSI_SEQUENCES 中不存在简单 Alt+字母映射

经验证，`ANSI_SEQUENCES` 中 **没有任何** `\x1b` + 单个字母 → tuple 的映射。所有已知 meta tuple（共 62 个）都是扩展 CSI 序列（如 `\x1b[1;3D` → `(Escape, Left)`）。这意味着 Alt+字母在 Vt100Parser 中总是产生 `[Escape, letter]` callback batch，与 plan 描述的完全一致。

### 2.4 Frozen F03 Oracle 摘要

- `prompt.17-running-escape-sequence-disambiguation`（accepted）："prompt Run期间只有standalone Escape表达取消；input owner必须等待并解析足以区分standalone chord与完整ESC-prefixed sequence的输入"。禁止："看到ESC prefix立即取消Run，导致方向键、Home/Delete、Alt或bracketed paste误触发cancel"。

- `interactive.18-running-escape-sequence-disambiguation`（accepted）：active Run 期间只有 standalone Escape 取消；CSI/Alt/paste 进入 composer navigation/editing/draft。禁止首 byte ESC 误取消。

- `interactive.11-running-escape-cancels-without-exit`（accepted）：standalone Escape 跨 acceptance barrier 取消当前 Run，Host canonical cancel terminal 完成后恢复 composer。

## 3. Assumptions Tested

| # | Assumption | 证伪结果 |
|---|---|---|
| A1 | `Vt100Parser.feed()` 同步回调与 `flush()` 构成可依赖的 batch boundary | **成立**。源码与上游 tests 共同证明 parser 在每次 `feed()`/`flush()` 返回前同步完成所有 callback。 |
| A2 | Alt 序列 callback shape 为 `[Escape, continuation]` 在同一 batch | **成立**。直接复验证实。 |
| A3 | CSI/SS3/Home/Delete 完整序列只产生单一非 Escape callback | **成立**。直接复验证实。 |
| A4 | Bracketed paste 不影响 Escape 分类 | **成立**。paste 产生单一 `BracketedPaste` callback，且 parser 内 paste mode 的快速路径（`data[i:]` 递归）不影响外层 batch boundary。 |
| A5 | UTF-8 incremental decoder + Vt100Parser 串接正确处理多字节截断 | **成立**。ESC (`\x1b`) 在 UTF-8 中是单字节控制字符，不会是任何多字节序列的 continuation byte。 |
| A6 | Reader thread 单 parser/decoder 模式无竞态 | **成立**。所有 parser/decoder/collector 操作在同一线程，callback batch 同步完成。 |
| A7 | `_ActiveTurnCloseout` 不改变 Host terminal owner | **成立**。Host 仍唯一拥有 accepted Run、graceful cancel 和 canonical terminal。 |
| A8 | Plan correction 不改变 acceptance barrier / double Ctrl+C 语义 | **成立**。原计划语义完整保留。 |

## 4. Findings

### F1-未修复-中-`_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 值未指定

- **位置**: Plan correction §Ambiguity deadline；主 plan §5.2(3)
- **问题类型**: 不可直接实施
- **当前写法**: "命名常量 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 对应的 monotonic deadline"。plan 只命名了常量但未指定具体值或可接受范围。
- **反例/失败场景**:
  - 值过短（<20ms）：正常跨 chunk 到达的 CSI/Alt 字节被 deadline flush 抢先拆分，用户按方向键或 Alt 时误触发 cancel。
  - 值过长（>500ms）：用户按 ESC 取消时感知到明显延迟，UX 变差。
  - 值未指定导致 implementation agent 自由选择，不同 agent 可能选择差异巨大的值，且 reviewer 无法判断是否正确。
- **为什么有问题**: prompt_toolkit 3.0.52 本身使用 `ttimeoutlen`（默认 0.1s = 100ms）解决同一问题。plan 的 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 本质上是同一概念，应明确取值或声明与 prompt_toolkit 配置的关系。不指定值意味着实现 agent 需要做出产品级决策，plan 不够 code-generation-ready。
- **直接证据**:
  - Plan §5.2(3): "命名常量 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS`"
  - prompt_toolkit 3.0.52 源码中 `ttimeoutlen` 默认值 0.1s（`prompt_toolkit.application.application.Application.ttimeoutlen`）
  - 实测：`select` 的 `_POLL_INTERVAL_SECONDS` 当前为 0.05s。若 deadline 设为此值的整数倍，需要明确倍数关系。
- **影响**: 实施 Agent 可能选择不安全的值，导致 edge case 下 Alt 误取消或 cancel 延迟。
- **建议改法和验证点**:
  1. 明确指定 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS = 0.1`（100ms），与 prompt_toolkit 的 `ttimeoutlen` 默认值一致。
  2. 或: 明确声明该值必须可被 `_POLL_INTERVAL_SECONDS` 整除，且不小于 `2 * _POLL_INTERVAL_SECONDS`，并给出推荐范围 [0.05, 0.2]。
  3. 在 owner tests 中加入 deadline 边界测试：极短 deadline（如 0.001s）不误 cancel 完整 CSI 序列；正常 deadline 下 standalone ESC 在约定时间内 cancel。
- **修复风险**: 低（追加一个常量赋值）
- **严重程度**: 中

---

### F2-未修复-中-Deadline 在 feed 完成序列后未明确清除

- **位置**: Plan correction §Ambiguity deadline；主 plan §5.3 不变量
- **问题类型**: 状态机漏洞
- **当前写法**: "ambiguity pending时每个后续非空chunk刷新deadline"；"flush完成并清空deadline后不得因空flush重复cancel"。但 plan 未描述当 `feed()` 调用成功解析完整 escape sequence（如 CSI 箭头）后 deadline 应如何处置。
- **反例/失败场景**:
  1. `os.read` 返回 `\x1b`，设置 deadline。
  2. 下一个 `select` 循环，`os.read` 返回 `[D`。
  3. `feed("[D")` → parser 将 `\x1b[D` 解析为 `Left` callback，batch 分类为 no-op。
  4. deadline 未被清除（plan 只说 flush 后清除，没说 feed 解析后清除）。
  5. 下一个 `select` 循环可能无新数据，deadline 到期触发 flush。
  6. `flush()` 产生空 batch（parser 无 pending prefix），no-op。
  7. 虽然本轮不产生错误 action，但多了一次无效 flush 调用。
- **为什么有问题**: 状态清理不完整。deadline 作为 "ESC ambiguity pending" 的标志位，在 ambiguity 已由 `feed()` 解析消除后应立即清除。不清除会造成后续无意义的 flush 循环（直到下一次 read 或下一次 deadline 到期）。更关键的：若在解析后、清除前的窗口中 fd 又变为可读且读到新 `\x1b`，旧的 deadline 可能与新 ambiguity 混淆。
- **直接证据**:
  - Plan §5.3: "deadline/readable竞态中continuation优先feed；deadline/close竞态中close优先且不得合成cancel。flush完成并清空deadline后不得因空flush重复cancel。"
  - 实测：`feed("\x1b")` → `feed("[D")` → `Left` callback，parser 内 prefix 已清空。
- **影响**: 低概率的功能性 bug（deadline 状态泄漏）；主要风险是 implementation agent 不理解 deadline 生命周期而引入复杂的状态管理逻辑。
- **建议改法和验证点**:
  1. 在不变量中增加："batch 分类后若 collector 不含 provisional Escape（即本次 feed 已完成序列解析），立刻清除 deadline。"
  2. 更简单的规则：每次 batch 分类完成后，若 parser collector 在 `feed()` 调用后为空（表明无 pending prefix），清除 deadline。此规则不需要访问 parser private state——collector 为空且 batch 已分类即意味着 parser 内部已无 pending prefix。
  3. 在 owner tests 中验证：CSI 箭头 feed 完成后，下一次 `select` 超时不应触发 flush。
- **修复风险**: 低（追加不变量描述）
- **严重程度**: 中

---

### F3-未修复-中-`_ActiveTurnCloseout` 重构涉及 8 个协调点，refactoring 边界风险高

- **位置**: 主 plan §5.2 items 390-398（机械映射表）；plan correction §原计划保持不变的语义
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: plan 以机械映射表描述 8 个旧 state/site 到新 `_ActiveTurnCloseout` 的对应关系，并声明 "旧 `_PromptAcceptedRunState`、`_InteractiveAcceptedRunState` 与只做透传的兼容 wrapper全部删除"。
- **反例/失败场景**:
  1. `_request_interactive_cancel`（当前 `session_execution.py:1807`）同时管理 composer phase transition（`composer.set_phase(InteractiveComposerPhase.CANCELLING)`）、thinking display finish（`runtime_display.finish_thinking_display()`）和 Host cancel task 创建。`_ActiveTurnCloseout.request_cancel()` 需要接管这些职责，但它不持有 composer 或 display controller 引用。
  2. `_drive_interactive_tty_repl` 的 finally block 和 `_wait_interactive_batch_terminal_handling_sigint` 的 finally block 各自管理 `cancel_task`、`acceptance_task`、`submit_task` 的清理顺序。收敛到 `_ActiveTurnCloseout.wait_closeout()` 后，cleanup 顺序可能被意外改变。
  3. `_finish_interactive_terminal` 在 terminal render 后执行 cursor advance。若 `_ActiveTurnCloseout` 在 render 之前就返回 terminal result，cursor 可能未持久化。
  4. `_cancel_prompt_turn_after_local_request` 当前调用 `submit_task.cancel()`。plan 要求删除本地 task cancellation、改为跨 barrier 等待。这改变了 prompt 的 cancel 时序，需要确保 `_ActiveTurnCloseout` 对 prompt 和 interactive 两种模式都正确处理。
- **为什么有问题**: 机械映射表覆盖了识别出的 site，但未覆盖 site 之间的隐式依赖（composer phase、display state、cursor advancement 与 terminal observation 的相对顺序）。implementation agent 可能在重构时破坏这些隐式依赖。
- **直接证据**:
  - 主 plan §5.2 items 390-398: 8 行映射表
  - `session_execution.py:1807-1846`（`_request_interactive_cancel` 的 composer/display 副作用）
  - `session_execution.py:1380-1416`（terminal completion 后的 composer phase reset 和 cursor advance）
  - `session_execution.py:1889-1927`（`_finish_interactive_terminal` 的 display/terminal/cursor 顺序）
- **影响**: 重构可能破坏 composer phase transition 时序、display cleanup 顺序或 cursor 持久化。debug 困难（涉及 asyncio task ordering）。
- **建议改法和验证点**:
  1. 在 plan 中明确 `_ActiveTurnCloseout` 的 public method 签名和每个 method 的 side-effect contract（包括必须由调用方完成的 composer phase、display state 和 cursor advancement）。
  2. 明确 `wait_closeout()` 返回前必须保证的 invariant：composer 已恢复 IDLE/RUNNING、display 已 finish、cursor 已 advance、attachment 未泄漏。
  3. 为 prompt 和 interactive 分别列出 `_ActiveTurnCloseout` 使用的最小时序图，标注哪些步骤由 coordinator 完成、哪些由 outer driver 完成。
  4. 在 owner tests 中增加 "cancel 后 composer phase 恢复" 和 "cancel 后 cursor 持久化" 的精确断言。
- **修复风险**: 中（需要细化 plan 中的 contract 描述，不改变设计方案本身）
- **严重程度**: 中

---

### F4-未修复-低-Known meta tuple 分类依赖 `data == "\x1b"` 精确比对

- **位置**: 主 plan §5.2(6)：`CANCEL_RUN` 产生条件
- **问题类型**: 契约缺失
- **当前写法**: "`CANCEL_RUN`只有一个产生条件：ambiguity deadline触发的 **flush batch** 精确只包含一个standalone形状的`KeyPress(key=Keys.Escape, data="\x1b")`"。
- **反例/失败场景**: 已知 meta tuple（如 `\x1b[1;3H` → `[Escape("\x1b[1;3H"), Home("")]`）的第一个 callback 也是 `Keys.Escape` 但 `data` 字段为完整 CSI 序列（如 `"\x1b[1;3H"`）而非 `"\x1b"`。若 implementation agent 只检查 `key is Keys.Escape` 而忽略 `data` 字段，meta tuple 的 Escape 会被误判为 standalone。
- **为什么有问题**: plan 的表述已正确——明确要求 `data="\x1b"`——但由于当前 `run_keys.py` 的 `running_key_action_from_bytes` 只检查 `data == _ESC`（字节比对），implementation agent 可能延续此模式只检查 key 类型。plan 未显式强调 `data` 字段检查的关键性。
- **直接证据**:
  - 主 plan §5.2(6): 条件已包含 `data="\x1b"`
  - 实测：meta tuple Escape data = `"\x1b[1;3H"` ≠ `"\x1b"`
  - 当前 `run_keys.py:271`: `if data == _ESC:` — 只做字节比对，与新 `KeyPress` 类型不同
- **影响**: implementation agent 可能忽略 `data` 字段检查，导致已知 meta tuple 的第一个 Escape callback 被误判为 cancel。
- **建议改法和验证点**:
  1. 在 plan correction 的 batch 分类规则中显式注释："注意：known meta tuple 的 Escape callback 携带完整 CSI data（非 `\x1b`），只有 `data == '\x1b'` 的 Escape 才可能是 standalone。"
  2. 在 owner tests 中增加：已知 meta tuple 的 flush batch（虽然实际不会单独出现）中的 Escape 不产生 cancel。
- **修复风险**: 低（追加注释和 1 个 test case）
- **严重程度**: 低（plan 已包含正确条件，只是 clarity gap）

---

### F5-未修复-低-`RunningKeyAction` 枚举值命名与 `_PromptControlKey` 不一致

- **位置**: `run_keys.py:32-36` vs 主 plan §5.2
- **问题类型**: 不可直接实施
- **当前写法**: `run_keys.py` 中 `RunningKeyAction` 有 `TOGGLE_ACTIVITY`、`CANCEL_RUN`。主 plan §5.2 引入 `_PromptControlKey(StrEnum)` 有 `CANCEL`、`TOGGLE_THINKING`。plan correction 未说明这两个 enum 的关系。
- **反例/失败场景**: implementation agent 不确定是保留 `RunningKeyAction` 还是替换为 `_PromptControlKey`，或者两者并存时需要映射。enum 值差异会导致 `_submit_prompt_turn_handling_sigint` 中的 `if action is RunningKeyAction.TOGGLE_ACTIVITY` 与新 coordinator 期望的 `_PromptControlKey.TOGGLE_THINKING` 不匹配。
- **为什么有问题**: 同一语义（toggle activity/thinking view、cancel run）在两个 enum 中以不同名字出现，implementation agent 需要推断映射关系，增加出错概率。
- **直接证据**:
  - `run_keys.py:34-36`: `RunningKeyAction.TOGGLE_ACTIVITY`、`CANCEL_RUN`
  - 主 plan §5.2: `_PromptControlKey.CANCEL`、`TOGGLE_THINKING`
- **影响**: 编译/类型检查可通过（都是 StrEnum 的不同成员），但运行时逻辑断裂。
- **建议改法和验证点**:
  1. 明确 `RunningKeyAction` 是否保留（建议保留，因为它是 `run_keys` 模块的 public contract）。
  2. 若保留，明确 `_PromptControlKey` 是 `RunningKeyAction` 的重命名还是新增的 coordinator-internal enum，若是后者则明确映射规则。
  3. 或者在 plan 中统一使用 `RunningKeyAction` 并删除 `_PromptControlKey` 定义。
- **修复风险**: 低（命名统一）
- **严重程度**: 低

---

### F6-未修复-低-Paste payload 内 Ctrl+T 不会误触发 toggle 的验证不够显式

- **位置**: Plan correction §Owner-level test matrix "paste parser" row
- **问题类型**: 测试缺口
- **当前写法**: "paste parser | start/content/end跨chunk；payload内Ctrl+T；end后Ctrl+T | paste payload不触发action；end后独立Ctrl+T只toggle"
- **反例/失败场景**: 实测确认 `Vt100Parser` 在 bracketed paste mode 内部将整个 payload（包括其中的 `\x14` 字节）作为 `BracketedPaste` 的 data 一次性回调。但 plan 的 batch 分类器在看到 `BracketedPaste` callback 时需明确"不触发任何 running action"。若 batch classifier 只处理 `Keys.Escape` 和 `Keys.ControlT` 而遗漏 `Keys.BracketedPaste`，payload 中的 Ctrl+T 不会被解析但也不会有害（因为 parser 不会为 paste 内容产生 `ControlT` callback）。真正的风险是 paste end marker 后的独立 `\x14` 与 paste callback 在同一 batch 时，batch classifier 必须正确处理 `[BracketedPaste, ControlT]` 这种 batch。
- **为什么有问题**: plan 没有显式列出 `[BracketedPaste, ControlT]` 这个 batch 组合。实测：若 paste end 和 Ctrl+T 在同一 `os.read` 块中到达，parser 的递归 `self.feed(remaining)` 可能使 paste callback 和后续 `ControlT` 出现在同一 `feed()` 解析结果中。
- **直接证据**:
  - 实测：`feed("\x1b[200~payload\x1b[201~\x14")` → `[BracketedPaste("payload"), ControlT("\x14")]` — 同一 feed batch。
  - Vt100Parser 源码 `feed()` 方法第 218 行：paste end 后调用 `self.feed(remaining)` 递归，使后续字节与 paste callback 同步产生的 ControlT 在同一 feed 调用中解析。
- **影响**: 若 batch classifier 不处理此组合，ControlT 可能被静默丢弃（不影响 correctness 但丢失 toggle 功能）。
- **建议改法和验证点**:
  1. 在 batch 分类规则中显式声明：`BracketedPaste` callback 自身不产生 running action；同 batch 中的后续 callback 仍按自身语义独立分类。
  2. 在 owner tests 中增加 `feed(paste_sequence + Ctrl+T_byte)` 的精确断言。
- **修复风险**: 低
- **严重程度**: 低

---

## 5. Adversarial Focus Area 压测结论

### 5.1 public feed/flush callback batch 足以区分 standalone Escape 与 Alt continuation

**结论：充分。** 证据链：

1. `feed("\x1b")` → 零 callback。parser 内部 `_IS_PREFIX_OF_LONGER_MATCH_CACHE["\x1b"]` 为 `True`。
2. `flush()` 后 → `[Escape("\x1b")]`。这是 standalone Escape 的唯一合法产生路径。
3. `feed("\x1bx")` → `[Escape("\x1b"), 'x']`。Alt+X 在同一 batch 中产生两个 callback。
4. 跨 chunk：`feed("\x1b")` 零 callback → `feed("x")` 产生 `[Escape("\x1b"), 'x']`。
5. CSI/SS3/Home/Delete 完整序列 → 单 callback，不含 Escape。
6. Known meta tuple → `[Escape(full_data), Key("")]`，Escape 的 data ≠ `"\x1b"`。

plan 的 batch 分类规则（provisional Escape + flush-only standalone cancel）与上述行为完全匹配，且不依赖 parser private state。

### 5.2 跨 chunk、同 raw read 多按键

**结论：正确处理。**

- 同 raw read 多按键：Vt100Parser 逐字符解析，一个 `feed()` 调用可能产生多个 key callback。plan 的 batch boundary 就是 `feed()` 调用，batch 分类规则处理任意 callback 序列。
- 跨 chunk：parser 内部 generator state machine 跨 `feed()` 调用保持 prefix 状态。plan 的 deadline 机制正确地在跨 chunk 等待期间保持 ESC ambiguity pending。

### 5.3 CSI/SS3/Home/Delete

**结论：不会误取消。**

CSI 箭头（`\x1b[D`）、SS3 Home（`\x1bOH`）、Delete（`\x1b[3~`）在 parser 中均产生单 callback（分别为 `Left`、`Home`、`Delete`），callback 中不包含 `Keys.Escape`。batch classifier 对这些 callback 不产生任何 running action（它们是 navigation/editing key，不是 control key）。

### 5.4 Bracketed paste

**结论：不会误取消或误触发。**

Paste 在 parser 中通过专用 fast path 处理：start marker 进入 paste mode，payload 累积，end marker 触发单一 `BracketedPaste` callback。Paste callback 不携带 Escape。唯一需要关注的是 paste end 后递归 `feed(remaining)` 导致 paste 与后续 key 在同一 batch（见 F6）。

### 5.5 Alt+Ctrl+T

**结论：不误取消且 toggle 独立触发。**

`feed("\x1b\x14")` → `[Escape("\x1b"), ControlT("\x14")]`。plan 规则：provisional Escape 因 ControlT continuation 被抑制，ControlT 独立产生 `TOGGLE_ACTIVITY`。正确。

### 5.6 Deadline/readable/close race

**结论：优先级正确。**

- fd readable 与 deadline 同时 ready：先 read/decode/feed。若 feed 解析并完成序列（如 CSI 箭头到达），batch 不产生 cancel。只有确认本轮无新字节才 flush。
- close 与 deadline 同时 ready：close 优先。teardown 不合成 flush，pending ambiguity 丢弃。正确。
- 空 flush 不产生 cancel。正确。

### 5.7 单一 parser/decoder、reader-thread owner

**结论：坚持了。**

plan 明确规定 reader thread 内创建唯一 `Vt100Parser`、唯一 UTF-8 incremental decoder、唯一 `list[KeyPress]` collector。只有 `call_soon_threadsafe` 跨越 thread boundary。parser private state/API 零导入。

### 5.8 Acceptance barrier、double Ctrl+C、Host terminal owner

**结论：不改变。**

plan correction 仅替换 parser callback 分类前提。`_ActiveTurnCloseout` 保持原计划语义：Host 唯一拥有 accepted Run、graceful cancel 和 canonical terminal；CLI 不伪造 `CANCELLED`；double Ctrl+C 等待 Host terminal 与全部 cleanup 后 exit 130。

## 6. Open Questions

无。所有关键问题均有直接证据支撑。

## 7. Residual Risks

| 风险 | 等级 | 跟踪建议 |
|---|---|---|
| `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 值选择 | LOW | 按 F1 建议修复后降为零。默认为 0.1s 与 prompt_toolkit 一致。 |
| `_ActiveTurnCloseout` 重构中隐式依赖破坏 | MEDIUM | 按 F3 建议细化 contract 后降低。由 owner tests 的 composer phase / cursor / display cleanup 断言覆盖。 |
| 真实 PTY chunk timing 与 deadline 的极端组合 | LOW | 已批准 S8 real evidence 覆盖。S3 的 deadline 常量可用测试注入覆盖边界情况。 |
| `prompt_toolkit` 未来版本改变 `Vt100Parser` 的 callback batch 形状 | LOW | S3 public seam contract test 在 resolved dependency 行为变化时 fail closed。项目声明 `>=3.0.0` 而非 pin 3.0.52。 |
| ESC + 普通字符与 Alt+字符的不可区分性 | ACCEPTED | 终端物理限制，plan 已正确记录且按"Alt 不误取消"优先。不扩张产品语义。 |

## 8. Gate Verdict

**PASS-WITH-FINDINGS**

Plan correction 的核心设计——暂存 provisional Escape 到 feed/flush batch 边界后分类——与 public `Vt100Parser` 3.0.52 的实际行为精确匹配。直接复验确认所有关键 sequence（standalone ESC、Alt+ASCII、Alt+Unicode、CSI、SS3、Home、Delete、known meta tuple、bracketed paste、ESC+Ctrl+T）的 callback batch 形状与 plan 的分类规则一致。单 parser/decoder、reader-thread owner、acceptance barrier、double Ctrl+C 和 Host terminal owner 均不改变。

6 个 finding 中：
- F1（deadline 值未指定）和 F3（`_ActiveTurnCloseout` 重构边界风险）需要在 implementation 前澄清，但不改变设计方案本身。
- F2、F4、F5、F6 均为低严重性的 clarity/consistency gap。

**建议**：按 F1、F3 建议微调 plan 后进入 S3 implementation。不要求第二轮 plan re-review。

## 9. Review Integrity

- 未修改 plan、production、tests、oracle/scenario。
- 未 stage、commit、push。
- 所有 parser 行为引用均基于 Python 3.11 + prompt_toolkit 3.0.52 public API 的独立复验。
- Frozen registry SHA-256 未验证（不在本 review scope；由 plan correction gate 已确认）。
