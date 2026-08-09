# WU-CLI-CONFORMANCE-F01-F07 S3 Plan Correction — Plan Re-review（DS）

## 0. Review 元数据

- **Reviewed targets**:
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md`（已修订主 plan §5 S3）
  - `docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-codex.md`（已修订 correction artifact）
- **Controller adjudication**: `docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-controller-adjudication.md`
- **Plan fix record**: `docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-fix-codex.md`
- **首轮 DS review**: `docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-review-ds.md`（F1–F6）
- **Work unit**: `WU-CLI-CONFORMANCE-F01-F07`
- **Slice**: `S3 / F03`
- **Gate**: Plan re-review（controller adjudication → plan fix → 两路 re-review → 下一 controller adjudication）
- **Review 模型**: deepseek-v4-pro
- **执行日期**: 2026-08-02（Asia/Shanghai）

## 1. Scope 与禁止动作

逐项复核首轮 DS review 的 6 个 finding（F1–F6）与 MiMo review 的 5 个 finding（MiMo-001 至 MiMo-005），参考 controller adjudication 的 11 项裁决与 plan fix 的落实记录。重点验证 focus area：

- 0.1s 固定值
- conservative armed deadline 不从 callback 推断 private state
- SIGINT owner（不形成第二 signal source）
- `RunningKeyAction` 唯一 contract
- key+data 双重条件
- paste+CtrlT 同 batch
- `_ActiveTurnCloseout` 与 outer cleanup 边界

禁止：改任何已有文件、production/tests/oracle/scenario，不 stage/commit/push。

## 2. 逐项复核

每项最终状态只用: `已修复` / `部分修复` / `未修复` / `证据失效`。

### 2.1 MiMo-001 / DS-F1：Ambiguity 常量未指定

- **Controller 裁决**: `accepted`
- **当前状态**: **已修复**
- **证据**:
  - 主 plan §5.2(3): `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS: Final[float] = 0.1`
  - Correction artifact: `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS: Final[float] = 0.1`
  - Owner tests: 可控 monotonic clock/`select` seam 推进 `0.099s → 0.1s`，禁止 wall-clock sleep
- **验证结论**: 值已固定为 0.1s，与 prompt_toolkit 3.0.52 默认 `ttimeoutlen` 量级一致。实现 agent 不再需要自行做产品级决策。通过。

### 2.2 MiMo-002：Chunk read size 未指定

- **Controller 裁决**: `rejected-with-reason`
- **当前状态**: **证据失效**
- **证据**: controller 裁定 correctness 由 incremental decoder + public parser resolution boundary 决定，不依赖具体 read size。主 plan 已追加 "chunk read size只是非语义性能参数，不得改变batch定义"。
- **验证结论**: 原 finding 的 functional concern 不成立。实现 agent 可自由选择合理 chunk size。通过。

### 2.3 MiMo-003：Ctrl+C 未显式排除 classifier

- **Controller 裁决**: `accepted`（clarity）
- **当前状态**: **已修复**
- **证据**:
  - 主 plan §5.2: "Ctrl+C不属于该contract，**只由SIGINT monitor产生与计数**，VT parser/batch classifier不得处理或合成Ctrl+C"
  - Correction artifact: "Ctrl+C不属于VT input语义，**只由SIGINT monitor产生、计数和区分first/second signal**；public parser callback classifier不得识别、投影或合成Ctrl+C，避免形成第二个signal owner"
  - Owner tests: "VT control byte不能产生Ctrl+C cancel intent；只有SIGINT monitor驱动状态迁移"
- **验证结论**: SIGINT monitor 是 Ctrl+C 的唯一 owner 已显式声明。VT parser 的 batch classifier 不得产生 Ctrl+C intent。通过。

### 2.4 MiMo-004：ESC+普通字符与 Alt 不可区分

- **Controller 裁决**: `accepted-as-residual`
- **当前状态**: **已修复**（作为 residual risk 记录）
- **证据**: 两份 plan 显式分类为 terminal 物理限制：0.1s window 内相同 bytes 统一不 cancel；S3 owner test 与 S8 PTY 留证，不新增 oracle/scenario 或产品语义。
- **验证结论**: 不可区分性是 terminal byte protocol 的物理事实，已正确记录为 residual risk。通过。

### 2.5 MiMo-005：Deadline 后 continuation 到达

- **Controller 裁决**: `accepted-as-residual`
- **当前状态**: **已修复**（作为 residual risk 记录）
- **证据**: 固定 0.1s 有限边界；S3 覆盖正常/代表性跨 chunk，S8 覆盖真实 PTY timing；不扩张为网络 terminal protocol。
- **验证结论**: 任意有限 timeout 都无法证明无限迟到 continuation，已正确记录。通过。

### 2.6 DS-F2：完整 sequence 后 deadline 未清除

- **Controller 裁决**: `rejected-as-functional-finding; accepted-as-clarity-fix`
- **当前状态**: **已修复**
- **证据**:
  - 主 plan §5.2(4): "deadline采用 **conservative armed until one flush**：一旦含ESC的raw chunk使其armed，就不能根据本次callback batch为空、非空或callback形状推断public parser是否仍有pending prefix，也不能在feed后提前清除"
  - 关键规则: "`select`没有新字节且deadline到期时，由同一reader thread调用恰好一次`parser.flush()`...并在该次flush返回后无条件清除deadline；已解析完整sequence时这一次空flush是预期no-op，不得循环或重复cancel"
  - Correction artifact invariants §5: "0.1s deadline一旦armed就保持到一次flush返回；不能从callback batch推断private pending"
  - Owner tests: "complete sequence产生非空callback后deadline仍armed，到期恰好一次空flush并清除"；"同一feed产生callback且以ESC结尾时仍在0.1s后flush出standalone cancel"
- **验证结论**: controller 正确拒绝了从 callback batch 推断 private state 的错误规则。conservative armed 规则是最小安全规则——它不要求访问 parser private state，且覆盖了"前有 callback 但尾随 ESC"和"完整 sequence 解析后空 flush no-op"两种场景。DS 首轮 finding 的 functional 部分证据失效，clarity 部分已落实。通过。

### 2.7 DS-F3：`_ActiveTurnCloseout` 隐式副作用边界

- **Controller 裁决**: `accepted-in-part`
- **当前状态**: **已修复**
- **证据**:
  - Correction artifact §`_ActiveTurnCloseout` method contract: 完整的五方法 typed contract 表，每个方法有明确的 `managed` 列和 `不等待/不执行` 列
  - `wait_closeout()`: "**不等待或执行** composer/display/cursor/attachment/key/signal cleanup"
  - 主 plan §5.2: prompt outer driver 拥有 "thinking/runtime display finish、cancel-requested/terminal render、prompt key monitor与SIGINT monitor teardown，以及既有prompt exit mapping"
  - 主 plan §5.2: interactive outer driver 拥有 "InteractiveComposerPhase.CANCELLING/RUNNING/IDLE切换、thinking/runtime display finish、cancel-requested/local-exit/terminal render、advance_cli_terminal_cursor、queued promotion，以及composer/key/signal/attachment teardown"
  - 显式偏序: "canonical terminal observation与outer cleanup是两个明确的时序点"
  - 统一时序: "outer driver在`wait_closeout()`返回后完成各自UI/resource cleanup，最后才根据intent与既有terminal mapping决定130"
  - 禁止项: "不得把composer/display/cursor/attachment引用塞进coordinator，也不得让`wait_closeout()`伪装成全invocation cleanup barrier"
  - Owner tests: "coordinator未取得composer/display/cursor/attachment/key/signal cleanup ownership"
- **验证结论**: controller 正确拒绝了让 `wait_closeout()` 拥有 UI/resource cleanup 的建议（那会违反已批准的最小 shared coordinator boundary）。修订后 contract 精确定义了 coordinator 与 outer driver 的边界。通过。

### 2.8 DS-F4：Known meta tuple 需要精确 key+data 检查

- **Controller 裁决**: `accepted`（clarity/test）
- **当前状态**: **已修复**
- **证据**:
  - 主 plan §5.2(6): "`CANCEL_RUN`只有一个产生条件：ambiguity deadline触发的 **flush batch** 长度精确为1，且唯一member同时满足`key is Keys.Escape`与`data == "\x1b"`。只匹配key或只匹配data均非法；known-meta中`key is Keys.Escape`但`data`为完整sequence的callback不得取消"
  - Correction artifact: "只检查其中一个字段不合格，known-meta中携带完整sequence data的Escape callback不得取消"
  - Owner tests: "错误key/错误data均为0"
- **验证结论**: key+data 双重条件已显式声明。已知 meta tuple 的 Escape callback（data 为完整 CSI sequence，非 `"\x1b"`）不会误触发 cancel。通过。

### 2.9 DS-F5：`RunningKeyAction` 与 `_PromptControlKey` 重复

- **Controller 裁决**: `accepted`
- **当前状态**: **已修复**
- **证据**:
  - 主 plan §5.2: "`RunningKeyAction`保留为`run_keys`唯一typed key contract：reader只可投递`CANCEL_RUN`或`TOGGLE_ACTIVITY`，prompt/interactive driver直接消费；不新增`_PromptControlKey`或第二个等价enum"
  - Correction artifact: "`RunningKeyAction`保留为`run_keys`唯一typed key contract...不新增`_PromptControlKey`或任何等价enum"
  - 全文检索: `_PromptControlKey` 仅在两个 artifact 中各出现 1 次，均在删除声明中
- **验证结论**: `_PromptControlKey` 已从 plan 中删除。`RunningKeyAction` 是唯一 typed key contract。通过。

### 2.10 DS-F6：Paste end 与 Ctrl+T 同 batch 未显式覆盖

- **Controller 裁决**: `accepted`
- **当前状态**: **已修复**
- **证据**:
  - 主 plan §5.2(7): "`Keys.BracketedPaste`自身始终是running-action no-op，但同一resolution batch中paste end之后的`Keys.ControlT`仍独立产生一次`TOGGLE_ACTIVITY`"
  - Correction artifact: "`Keys.BracketedPaste`自身始终是no-op；同一batch中paste callback之后的`Keys.ControlT`仍独立投影为一次`TOGGLE_ACTIVITY`"
  - Owner tests: "`[BracketedPaste, ControlT]`同一batch只toggle一次"
- **验证结论**: paste+CtrlT 同 batch 场景已显式覆盖。Paste no-op 不吞掉后续 ControlT。通过。

## 3. Focus Area 逐项验证

### 3.1 0.1s

**已修复。** 常量 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS: Final[float] = 0.1` 在主 plan §5.2(3) 和 correction artifact 中均已固定。Owner tests 使用可控 monotonic clock/`select` seam 推进 `0.099s → 0.1s`，禁止 wall-clock sleep。实现 agent 不需要自行选择产品级值。

### 3.2 Conservative armed deadline 不从 callback 推断 private state

**已修复。** 关键约束连锁正确：

- "一旦含ESC的raw chunk使其armed，就不能根据本次callback batch为空、非空或callback形状推断public parser是否仍有pending prefix"
- "不能从callback batch推断private pending"
- "一次flush返回后无条件清除deadline"
- "已解析完整sequence时这一次空flush是预期no-op，不得循环或重复cancel"

该规则的最坏情况行为是一次空 flush（no-op），不会产生 spurious cancel。而"从 callback 非空推断 parser 无 pending"的错误规则会导致真实尾随 ESC 被遗漏（例如 feed 在多字符后以 `\x1b` 结尾）。

### 3.3 SIGINT owner

**已修复。** 三处一致：

- VT parser batch classifier: "不得处理或合成Ctrl+C"
- SIGINT monitor: "只由SIGINT monitor产生、计数和区分first/second signal"
- Owner tests: "VT control byte不能产生Ctrl+C cancel intent；只有SIGINT monitor驱动状态迁移"

不会形成第二 signal source。注意：此约束适用于 `run_keys.py` 的 Vt100Parser。Interactive composer 的 Ctrl+C key binding（`_cancel_active_with_ctrl_c`）不受影响——它是 prompt_toolkit 的 key binding，不是 VT parser batch classifier。

### 3.4 RunningKeyAction 唯一 contract

**已修复。** `RunningKeyAction` 保留为 `run_keys` 唯一 typed key contract，值仅 `CANCEL_RUN` 和 `TOGGLE_ACTIVITY`。`_PromptControlKey` 已从两份 plan artifact 中删除。Prompt 与 interactive driver 直接消费 `RunningKeyAction`。

### 3.5 key+data 双重条件

**已修复。** Standalone Escape 的三个条件连锁：

1. Flush batch（非 feed batch）
2. Batch 长度精确为 1
3. 唯一 member 同时满足 `key is Keys.Escape` AND `data == "\x1b"`

只匹配 key 或只匹配 data 均非法。Known-meta 中 `key is Keys.Escape` 但 `data` 为完整 CSI sequence 的 callback 不会误取消。Owner tests 加入错误 key/错误 data 反例。

### 3.6 paste+CtrlT 同 batch

**已修复。** `[BracketedPaste, ControlT]` 同 batch：paste callback no-op，ControlT 独立投影为 `TOGGLE_ACTIVITY` 一次。该组合场景的出现机制（parser 内 paste end 后递归 `self.feed(remaining)`）已在 review 中确认，owner tests 已加入精确断言。

### 3.7 `_ActiveTurnCloseout` 与 outer cleanup 边界

**已修复。** 完整 method contract 表定义了五个方法的 ownership boundary：

- `publish_accepted(run_id)`: 只管理 acceptance barrier
- `request_cancel(*, reason, exit_after)`: 冻结 reason 与至多一次 Host cancel task
- `wait_accepted_then_cancel()`: 只协调 accepted→cancel
- `observe_terminal(result)`: 只记录 canonical terminal
- `wait_closeout()`: 只等待 Host closeout 协调，**不等待或执行** composer/display/cursor/attachment/key/signal cleanup

Outer driver 在 `wait_closeout()` 返回后独立完成 UI/resource cleanup，最后决定 130。偏序显式为：`canonical terminal observed → outer cleanup → 130 decision`。Coordinator 不得持有 composer/display/cursor/attachment 引用。

## 4. 修订后新增 inconsisteny 检查

对修订后 plan 做一轮 adversarial pass，未发现新增问题：

| 检查项 | 结果 |
|---|---|
| conservative armed 规则中尾随 ESC 正确识别 | ✅ 同一 feed 有 callback 且以 ESC 结尾 → deadline 保持 armed → 0.1s flush 出 standalone cancel |
| 完整 sequence 解析后不误刷 cancel | ✅ 空 flush 是预期 no-op，清除后不循环 |
| `select` timeout 取 min(poll, remaining) | ✅ 不越过 deadline 阻塞 |
| deadline refresh 规则连续数据不抢先 flush | ✅ 每个非空 chunk 刷新为"本次 feed 时刻 + 0.1s" |
| prompt outer driver 不丢失 SIGINT 消费 | ✅ prompt outer driver "独立消费SIGINT monitor" |
| interactive outer driver 正确管理 composer phase | ✅ "InteractiveComposerPhase.CANCELLING/RUNNING/IDLE切换"在 outer driver 中 |
| `request_cancel` 的 `exit_after` 参数单向性 | ✅ 只有 SIGINT monitor 的 second Ctrl+C 可升级 `exit_after=True`，Escape 不累计 |
| 重复 cancel 幂等 | ✅ "后续调用幂等" |
| `wait_closeout()` 返回后 terminal truth 不被 outer cleanup 篡改 | ✅ 时序显式: "outer cleanup完成后...return 130 : 返回既有terminal mapping" |
| 无 `_PromptControlKey` 残留 | ✅ 两文件各 1 次命中均为"不新增"声明 |
| `RunningKeyAction` 值不变 | ✅ `CANCEL_RUN`、`TOGGLE_ACTIVITY` |
| frozen registry SHA-256 不变 | ✅ 由 plan fix gate 确认 |

## 5. Residual Risk

| 风险 | 跟踪 | 覆盖 |
|---|---|---|
| ESC+普通字符与 Alt 在 0.1s 内不可区分 | S3 owner tests + S8 real PTY evidence | terminal 物理限制，已显式记录 |
| continuation 晚于 0.1s 到达 | S3 代表性 chunk tests + S8 real PTY timing | 任意有限 deadline 的固有限制 |
| resolved dependency 将来改变 public callback shape | S3 public seam contract test fail closed | 不依赖 private API 或依赖 pin |
| `_ActiveTurnCloseout` 重构中 outer driver 遗漏 cleanup 步骤 | S3 owner tests 逐项验证 composer phase / display / cursor / attachment / key / signal teardown 偏序 | method contract 已显式声明各 driver 职责 |

无 unclassified residual risk。无 blocking open question。

## 6. Gate Verdict

**PASS**

首轮 DS review 的 6 个 finding 与 MiMo review 的 5 个 finding 共 11 项，经 controller adjudication 裁决与 plan fix 落实后：

- **已修复**: F1（0.1s）、F2（conservative armed）、F3（closeout boundary）、F4（key+data）、F5（enum 统一）、F6（paste+CtrlT）、MiMo-001、MiMo-003、MiMo-004、MiMo-005
- **证据失效**: MiMo-002

七个 focus area 全部通过验证。修订后 plan 未引入新增 inconsisteny。Plan 已 code-generation-ready，可直接进入 S3/F03 implementation gate。

## 7. Review Integrity

- 未修改 plan、production、tests、oracle/scenario。
- 未 stage、commit、push。
- 所有 parser 行为引用基于 Python 3.11 + prompt_toolkit 3.0.52 public API 独立复验。
