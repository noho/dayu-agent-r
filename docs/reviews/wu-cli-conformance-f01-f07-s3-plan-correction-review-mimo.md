# WU-CLI-CONFORMANCE-F01-F07 S3 Plan Correction — Adversarial Review（MiMo）

## Review 元数据

- Review target：`docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-codex.md`（S3 plan correction）及其对 `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md` §5 的修订
- Blocked artifact：`docs/reviews/wu-cli-conformance-f01-f07-s3-implementation-codex.md`
- Review 范围：S3/F03 public parser batch strategy、acceptance barrier、double Ctrl+C、Host terminal owner
- 执行日期：2026-08-02（Asia/Shanghai）
- Review posture：adversarial，默认假设 plan 至少有一个重要问题，直到证据证明足够可靠
- 状态：`COMPLETE`

## Assumptions Tested

1. Public `Vt100Parser` feed/flush callback batch 是否足以区分 standalone Escape 与 Alt continuation
2. 跨 chunk、同 raw read 多按键、CSI/SS3/Home/Delete、bracketed paste 的 batch 行为
3. Alt+Ctrl+T 在混合 batch 中的独立分类
4. deadline/readable/close 竞态安全性
5. 单 parser/decoder、reader-thread owner 是否足够
6. 是否影响 acceptance barrier、double Ctrl+C、Host terminal owner

## 直接验证事实

### prompt_toolkit 3.0.52 Vt100Parser 源码验证

已完整读取 `.venv/lib/python3.11/site-packages/prompt_toolkit/input/vt100_parser.py`（251 行）。

Parser 核心机制：
- `_input_parser_generator()` 是 coroutine state machine，逐字符 yield 接收输入
- `prefix` 变量累积未匹配字符；`_IS_PREFIX_OF_LONGER_MATCH_CACHE` 判断是否为已知序列前缀
- `_Flush()` 是内部 sentinel，`flush()` 通过 `send(_Flush())` 触发
- `_call_handler()` 对 tuple key（如 Alt 序列 `(Keys.Escape, 'x')`）递归展开为独立 callback
- Bracketed paste 由 `_in_bracketed_paste` 标志管理，`_paste_buffer` 累积直到 end marker

### 实测 callback batch 表

| 输入与 boundary | callback batch | S3 typed action |
|---|---|---|
| `feed("\x1b")` | `[]`（无 callback） | 无 |
| deadline `flush()` | `[Escape(data="\x1b")]` | `CANCEL_RUN` 一次 |
| `feed("\x1bx")` | `[Escape(data="\x1b"), x(data="x")]` | 无 cancel |
| 跨 chunk `feed("\x1b")` / `feed("x")`（无中间 flush） | 第二个 feed 后 `[Escape(data="\x1b"), x(data="x")]` | 无 cancel |
| `feed("\x1b[A")` (CSI Up) | `[Up(data="\x1b[A")]` | 无 cancel |
| 跨 chunk `feed("\x1b")` / `feed("[A")` | `[Up(data="\x1b[A")]` | 无 cancel |
| `feed("\x1bOH")` (SS3 Home) | `[Home(data="\x1bOH")]` | 无 cancel |
| `feed("\x1b[3~")` (Delete) | `[Delete(data="\x1b[3~")]` | 无 cancel |
| `feed("\x1b[3;3~")` (Ctrl+Delete) | `[Escape(data="\x1b[3;3~"), Delete(data="")]` | 无 cancel（known meta tuple） |
| `feed("\x1b\x14")` (ESC+Ctrl+T) | `[Escape(data="\x1b"), ControlT(data="\x14")]` | 只 `TOGGLE_ACTIVITY` 一次 |
| `feed("\x1bx\x14")` (ESC+x+Ctrl+T) | `[Escape(data="\x1b"), x(data="x"), ControlT(data="\x14")]` | 只 `TOGGLE_ACTIVITY` 一次 |
| `feed("\x1b你")` (Alt+Unicode) | `[Escape(data="\x1b"), 你(data="你")]` | 无 cancel |
| `feed("\x1bOA")` (SS3 Up) | `[Up(data="\x1bOA")]` | 无 cancel |

### 关键 parser 状态行为

- `flush()` 后 parser 内部 prefix 清空（generator 在 `_Flush` 分支处理后 prefix=""）
- `flush()` 后续 `feed("x")` 产生独立 `x` KeyPress，不与已 flushed 的 Escape 合并
- Bracketed paste 由 parser 内部 `_in_bracketed_paste` 标志管理，`_paste_buffer` 累积直到 `\x1b[201~` end marker，然后产生单一 `Keys.BracketedPaste` callback
- `feed()` 逐字符 send 到 generator，每字符检查 prefix 匹配；匹配成功立即 callback 并清空 prefix
- 长序列前缀（如 `\x1b[`）在 `is_prefix_of_longer_match=True` 时保持 pending，不产生 callback

### 当前 run_keys.py 代码行为

当前 `_read_loop()` 读取单字节（`_READ_SIZE_BYTES = 1`），`running_key_action_from_bytes()` 对 ESC 字节立即返回 `CANCEL_RUN`。这导致方向键、Home/Delete、Alt 等完整 CSI/SS3 序列的首字节 ESC 被误判为取消。

### 当前 session_execution.py cancel 行为

`_cancel_prompt_turn_after_local_request()` 在 line 1037 调用 `submit_task.cancel()`，立即取消 submit task。计划将其改为：submit task 继续跨 acceptance barrier，Host accepted 后再调用 Host graceful cancel。

## Findings

### 001-unfixed-LOW-Ambiguity 常量未指定

- **位置**: S3 plan correction "Ambiguity deadline" 节
- **问题类型**: 契约缺失
- **当前写法**: plan 提到 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 命名常量，但未指定具体值
- **反例/失败场景**: 值过小（如 0.05s）可能导致终端分块 CSI 序列被抢先 flush；值过大（如 2s）导致 standalone Escape 响应迟钝
- **为什么有问题**: implementation agent 需要选择具体值；不同值对 UX 和正确性有直接影响
- **直接证据**: plan 文本只说"命名常量 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS`"，未给值
- **影响**: 实施 Agent 可能选择不当值，导致用户可感知的行为差异
- **建议改法和验证点**: 建议 plan 明确推荐值（如 0.5s），并说明选择依据；owner test 应覆盖 boundary timing
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 002-unfixed-LOW-Chunk read size 未指定

- **位置**: S3 plan correction "单一 parser / decoder 与 resolution batch" 节
- **问题类型**: 契约缺失
- **当前写法**: plan 说"reader thread 用 chunk read"，当前代码用 `_READ_SIZE_BYTES = 1`
- **反例/失败场景**: 若实现仍用 1 字节读取，每次 read 产生一个 chunk，每次 feed 一个字符，虽然功能正确但效率低且 deadline 逻辑更频繁触发
- **为什么有问题**: 从单字节到 chunk read 是行为变更；plan 应明确期望的 read size 范围
- **直接证据**: 当前 `run_keys.py` line 24: `_READ_SIZE_BYTES: Final[int] = 1`；plan 说"chunk read"但未指定大小
- **影响**: 轻微效率差异；功能正确性不受影响（parser 逐字符处理）
- **建议改法和验证点**: 建议 plan 指定合理 chunk size（如 1024），或说明"任何合理值均可"
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 003-unfixed-LOW-Ctrl+C 不经 batch classifier

- **位置**: S3 plan correction "batch classifier" 节
- **问题类型**: 契约缺失
- **当前写法**: batch classifier 只提到 `Keys.Escape` 和 `Keys.ControlT` 的处理；Ctrl+C 由 SIGINT signal handler 处理，不经 `run_keys` 的 batch classifier
- **反例/失败场景**: 无实际失败风险——Ctrl+C 走 SIGINT 是正确的架构分离
- **为什么有问题**: plan 的 batch classifier 矩阵应显式说明 Ctrl+C 不在 classifier 范围内，避免 implementation agent 误解
- **直接证据**: 当前 `session_execution.py` line 961: `sigint_task = asyncio.create_task(sigint_monitor.wait_next(observed_sigint_count))`；SIGINT 与 key monitor 是独立 task
- **影响**: 无功能影响；文档清晰度
- **建议改法和验证点**: 建议在 batch classifier 规则中显式排除 Ctrl+C/SIGINT，说明其由 signal handler 独立处理
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/严重）**: 低

### 004-unfixed-MEDIUM-ESC 普通字符与 Alt 不可区分的终端事实

- **位置**: S3 plan correction "不可区分事实与语义边界" 节
- **问题类型**: 状态机漏洞（已知、已记录、不可修复）
- **当前写法**: plan 正确记录了终端层 ESC+普通字符与 Alt+该字符的不可区分性，并决定该 batch 不 cancel
- **反例/失败场景**: 用户按 ESC 意图取消，但在 ambiguity window 内紧接输入普通字符；该 batch 被分类为 Alt-like，不 cancel
- **为什么有问题**: 这是终端物理限制，不是 plan 设计缺陷。plan 的处理（不 cancel）是正确的保守选择，因为误取消 Alt 比延迟取消 standalone ESC 更有害
- **直接证据**: 实测 `feed("\x1bx")` 产生 `[Escape, x]`，与 Alt+X 完全相同；terminal 层面 `\x1bx` 一个字节序列
- **影响**: 用户按 ESC 后快速输入字符时，取消不会发生；用户需要在 ESC 后等待 ambiguity window（约 0.5s）再输入才能触发 cancel
- **建议改法和验证点**: plan 已正确记录此限制。owner test 应断言两种情况均不 cancel，并记录为 terminal ambiguity accepted observation，不提升为新 oracle
- **修复风险（低/中/高）**: 无（已正确处理）
- **严重程度（低/中/高/严重）**: 中（用户可能困惑，但这是终端物理限制）

### 005-unfixed-LOW-Deadline 后 CSI 分块的 ESC 被 flush 风险

- **位置**: S3 plan correction "Ambiguity deadline" 节
- **问题类型**: 并发恢复风险
- **当前写法**: plan 规定"fd readable 与 deadline 同轮成立时，先读取、decode 并 feed 新字节；只有确认本轮没有新字节才允许 flush"
- **反例/失败场景**: ESC 到达 → deadline 开始 → 终端发送 `[D`（CSI Left 的剩余字节）→ 如果 `[D` 在 select() timeout 之后到达（即 deadline 先触发 flush），standalone ESC 被错误 cancel
- **为什么有问题**: 这要求 ambiguity timeout 大于终端发送 CSI 序列各字节间的最大间隔。正常终端通常原子发送完整序列（<1ms），但远程终端、SSH 转发或高负载下可能有更大延迟
- **直接证据**: 实测 `feed("\x1b")` + `flush()` + `feed("[D")` 产生 `[Escape]` 然后 `[bracketleft, D]`（三个独立 KeyPress），而非 `[Up]`
- **影响**: 在极端网络/负载条件下，CSI 序列可能被拆分为 standalone ESC + 普通字符，导致误取消
- **建议改法和验证点**: ambiguity timeout 应设置为足够大（如 0.5s）以覆盖正常终端延迟；owner test 应覆盖"ESC + 超时后 CSI 到达"的边界情况
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低（正常终端条件下不会触发；极端条件是已知 terminal 限制）

## Open Questions

无。所有技术假设已通过源码阅读和实测验证。

## Residual Risks

| 风险 | 等级 | 收敛方式 |
|---|---|---|
| ESC ambiguity window 内普通字符与 Alt 不可区分 | MEDIUM/ACCEPTED | 终端物理限制；plan 正确选择不 cancel；owner test 记录为 accepted observation |
| ambiguity timeout 值选择影响 UX | LOW | 建议 plan 明确推荐值；owner test 覆盖 boundary timing |
| 极端网络条件下 CSI 序列跨 chunk 被拆分 | LOW | ambiguity timeout 足够大时可覆盖；real PTY evidence 在 S8 验证 |
| chunk read size 对 deadline 频率的影响 | LOW | 功能正确性不受影响；效率差异微小 |
| Ctrl+C 经 SIGINT 而非 batch classifier 的架构分离 | LOW | 已由当前代码直接证明是正确分离；plan 建议显式记录 |

## Gate Verdict

**pass-with-risks**

S3 plan correction 的核心策略——使用 public `Vt100Parser` 的 feed/flush callback batch，通过 provisional Escape + ambiguity deadline 区分 standalone Escape 与 Alt/CSI continuation——已通过完整源码阅读和实测验证。所有关键 batch 形状（standalone Escape、Alt ASCII/Unicode、CSI arrows、Home/Delete、SS3、bracketed paste、混合 Ctrl+T）均与 plan 声称的行为一致。

单 parser/decoder + reader-thread owner 架构是正确的最小化方案，不引入第二套 raw-byte parser，不访问 private API，不依赖 `KeyProcessor`。feed batch vs flush batch 的区分规则（只有 flush-only standalone Escape 才 cancel）是区分 standalone Escape 与 Alt continuation 的充分条件。

acceptance barrier、double Ctrl+C 和 Host terminal owner 语义不受 S3 parser correction 影响：S3 只改变 key classification 层，`_ActiveTurnCloseout` 仍只消费 typed local intent，Host 仍唯一拥有 accepted Run、graceful cancel 和 canonical terminal。

Residual risks 均为 LOW 或已知终端物理限制（MEDIUM/ACCEPTED），不构成 implementation blocker。建议 implementation agent 在选择 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS` 值时参考 0.5s，并在 owner test 中覆盖 timing boundary。
