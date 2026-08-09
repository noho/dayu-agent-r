# WU-CLI-CONFORMANCE-F01-F07 S3 Plan Correction — Re-review（MiMo）

## Re-review 元数据

- Re-review target：已修订的 `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md` §5 与 `docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-codex.md`
- Controller adjudication：`docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-controller-adjudication.md`
- Fix artifact：`docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-fix-codex.md`
- 原 review：`docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-review-mimo.md`
- 执行日期：2026-08-02（Asia/Shanghai）
- 状态：`COMPLETE`

## 逐项 Finding 复核

### MiMo-001：Ambiguity 常量未指定

- **Controller 裁决**：`accepted`
- **Required action**：固定 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS = 0.1`；owner test 用可控 clock/select seam
- **修订验证**：
  - 主 plan §5.2(3) 已写：`_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS: Final[float] = 0.1`
  - Correction artifact 已写：`ambiguity常量固定为_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS: Final[float] = 0.1`
  - Test matrix 已写：`可控monotonic clock与patched select.select推进0.1s，不使用wall-clock sleep`
  - Acceptance barrier 已写：`固定0.1s conservative armed deadline`
- **最终状态**：`已修复`

### MiMo-002：Chunk read size 未指定

- **Controller 裁决**：`rejected-with-reason`（correctness 不依赖 read size）
- **Required action**：无
- **修订验证**：主 plan 与 correction 均明确"chunk read size只是非语义性能参数，不得改变batch定义"。Controller 基于直接证据拒绝，不要求 plan 指定具体值。
- **最终状态**：`证据失效`

### MiMo-003：Ctrl+C 未显式排除 classifier

- **Controller 裁决**：`accepted`（clarity）
- **Required action**：明确 Ctrl+C 只由 SIGINT monitor 拥有
- **修订验证**：
  - 主 plan §5.2 末尾已写：`RunningKeyAction` 保留为唯一 typed key contract；`Ctrl+C不属于该contract，只由SIGINT monitor产生与计数，VT parser/batch classifier不得处理或合成Ctrl+C`
  - Correction artifact 已写：`Ctrl+C不属于VT input语义，只由SIGINT monitor产生、计数和区分first/second signal；public parser callback classifier不得识别、投影或合成Ctrl+C`
  - 实测确认：VT parser 对 `\x03` 产生 `KeyPress(Keys.ControlC, "\x03")`，但 `run_keys.running_key_action_from_bytes()` 对 `b"\x03"` 返回 `None`，不投递到 queue
- **最终状态**：`已修复`

### MiMo-004：ESC+普通字符与 Alt 不可区分

- **Controller 裁决**：`accepted-as-residual`
- **Required action**：分类为 terminal 物理限制，S3 owner test + S8 PTY evidence 覆盖
- **修订验证**：两份计划均显式记录为 terminal 物理限制；0.1s window 内相同 bytes 统一不 cancel；不新增 oracle/scenario 或产品语义。
- **最终状态**：`已修复`

### MiMo-005：Deadline 后 continuation 才到达

- **Controller 裁决**：`accepted-as-residual`
- **Required action**：固定 0.1s 有限边界；S3 覆盖代表性跨 chunk，S8 覆盖真实 PTY timing
- **修订验证**：两份计划均固定 0.1s 边界；test matrix 包含 `fd readable与deadline同轮时先feed continuation并refresh deadline且零cancel`；residual risk 分类为 S3 + S8 覆盖。
- **最终状态**：`已修复`

## Controller 额外 Required Actions 复核

### DS-F1（= MiMo-001）：常量值 → `已修复`（同 MiMo-001）

### DS-F2：Conservative armed deadline

- **Controller 裁决**：`rejected-as-functional-finding; accepted-as-clarity-fix`
- **Required action**：不从 callback 推断 private state；conservative armed until one flush；明确空 flush 是预期 no-op
- **修订验证**：
  - 主 plan §5.2(4) 已重写为完整的 conservative armed 规则：`不能根据本次callback batch为空、非空或callback形状推断public parser是否仍有pending prefix，也不能在feed后提前清除`
  - Correction artifact 已写：`deadline采用 conservative armed until one flush：含ESC后保持armed，不能从callback batch为空、非空或具体callback推断public parser private pending state`
  - Test matrix 已写：`complete sequence产生非空callback；同一feed有callback且尾随ESC` → `不从callback推断pending；前者到期一次空flush后清除，后者到期flush并cancel一次`
  - 实测确认：`feed('\x1b[A')` 产生 `[Up]` 后，`flush()` 产生 0 callbacks（空 flush no-op）；`feed('\x1b[A\x1b')` 产生 `[Up]` 后 ESC pending，`flush()` 产生 `[Escape]`
- **最终状态**：`已修复`

### DS-F3：`_ActiveTurnCloseout` 外部副作用边界

- **Controller 裁决**：`accepted-in-part`
- **Required action**：补齐 method contract 与 prompt/interactive 时序；拒绝让 coordinator 拥有 composer/display/cursor/attachment cleanup
- **修订验证**：
  - 主 plan 已添加完整的 method contract 表（`publish_accepted`、`request_cancel`、`wait_accepted_then_cancel`、`observe_terminal`、`wait_closeout`），每个 method 有明确的"不"约束
  - `wait_closeout()` contract：`不等待或执行 composer/display/cursor/attachment/key/signal cleanup；这些属于outer driver`
  - Prompt/interactive outer driver 时序已明确：`wait_closeout()` 返回后才完成 UI/resource cleanup，最后才决定 130
  - Correction artifact 补齐相同 contract
  - Test matrix 已写：`coordinator不调用UI/resource接口；outer完成display/composer/cursor/attachment/key/signal teardown后才决定130`
- **最终状态**：`已修复`

### DS-F4：Known-meta key+data 双重条件

- **Controller 裁决**：`accepted`（clarity/test）
- **Required action**：standalone Escape 要求 key 与 data 双重匹配；加入 known-meta 完整 sequence data 测试
- **修订验证**：
  - 主 plan §5.2(6) 已写：`batch长度精确为1，且唯一member同时满足key is Keys.Escape与data == "\x1b"`；`只匹配key或只匹配data均非法；known-meta中key is Keys.Escape但data为完整sequence的callback不得取消`
  - Correction artifact 同步更新
  - Test matrix 已写：`standalone key+data双重正例、错误key/错误data反例、known-meta完整sequence data`
  - 实测确认：known meta `Escape(data='\x1b[1;3H')` 满足 `key is Keys.Escape` 但 `data != "\x1b"`，双重条件正确拒绝
- **最终状态**：`已修复`

### DS-F5：`RunningKeyAction` 唯一 contract

- **Controller 裁决**：`accepted`
- **Required action**：删除 `_PromptControlKey`；保留 `RunningKeyAction` 为唯一 typed key contract
- **修订验证**：
  - 主 plan 已删除 `_PromptControlKey` enum；§5.2 末尾写：`RunningKeyAction保留为run_keys唯一typed key contract`
  - Correction artifact 同步更新：`不新增_PromptControlKey或任何等价enum`
  - 原有 `_LocalCancelIntent` enum 保留（这是 coordinator 内部状态，不是 key contract）
  - Test matrix 已写：`RunningKeyAction保持唯一typed key contract，Ctrl+C只由SIGINT monitor驱动`
- **最终状态**：`已修复`

### DS-F6：Paste end + Ctrl+T 同 batch

- **Controller 裁决**：`accepted`
- **Required action**：明确 `BracketedPaste` no-op；同 batch 后续 `ControlT` 独立 toggle；新增 owner test
- **修订验证**：
  - 主 plan §5.2(7) 已写：`Keys.BracketedPaste自身始终是running-action no-op，但同一resolution batch中paste end之后的Keys.ControlT仍独立产生一次TOGGLE_ACTIVITY`
  - Correction artifact 同步更新
  - Test matrix 已写：`[BracketedPaste, ControlT]` 同 batch 只 toggle 一次
  - 实测确认：`feed('test\x1b[201~\x14')` 在 paste mode 中产生 `[BracketedPaste('test'), ControlT]`
- **最终状态**：`已修复`

## 重点验证项复核

### 0.1s timeout

- 常量已固定为 `Final[float] = 0.1`
- 与 prompt_toolkit 默认 `ttimeoutlen`（0.1s）量级一致
- Test matrix 用可控 monotonic clock/`select` seam，不依赖 wall-clock
- **验证通过**

### Conservative armed deadline

- 规则已明确写入两份计划："含ESC后保持armed，不能从callback batch推断private pending state"
- 空 flush 是预期 no-op，不循环、不重复 cancel
- 同一 feed 有 callback 且尾随 ESC 时，deadline 仍保持 armed
- 实测：complete CSI 后 flush 为空（no-op）；trailing ESC 后 flush 为 standalone Escape
- **验证通过**

### SIGINT owner

- `RunningKeyAction` 只有 `CANCEL_RUN` 和 `TOGGLE_ACTIVITY`
- Ctrl+C 只由 SIGINT monitor 产生、计数和区分 first/second
- VT parser 对 `\x03` 产生 KeyPress 但 batch classifier 不识别（返回 None）
- 不存在第二个 signal owner
- **验证通过**

### RunningKeyAction 唯一 contract

- `_PromptControlKey` 已从计划中删除
- `RunningKeyAction` 保留为 `run_keys` 唯一 public typed contract
- `_LocalCancelIntent` 是 coordinator 内部 enum，不与 `RunningKeyAction` 重复
- **验证通过**

### key+data 双重条件

- standalone Escape 要求 `key is Keys.Escape` AND `data == "\x1b"`
- known-meta `Escape(data='\x1b[1;3H')` 被正确拒绝（key 匹配但 data 不匹配）
- Test matrix 覆盖正例、反例和 known-meta
- **验证通过**

### paste+CtrlT

- `BracketedPaste` 自身始终 no-op
- `[BracketedPaste, ControlT]` 同 batch 只 toggle 一次
- 实测确认：paste end + Ctrl+T 产生 `[BracketedPaste, ControlT]`
- **验证通过**

### `_ActiveTurnCloseout` 与 outer cleanup 边界

- Coordinator 只拥有 acceptance、cancel intent、exactly-once Host cancel task、canonical terminal observation
- `wait_closeout()` 不等待或执行 composer/display/cursor/attachment/key/signal cleanup
- Prompt/interactive outer driver 在 `wait_closeout()` 返回后完成各自 cleanup，最后决定 130
- Test matrix 覆盖 method contract、outer side-effect timing 和 coordinator 不触碰 UI/resource 接口
- **验证通过**

## Registry 完整性

- `docs/cli_ci_oracles.json` SHA-256：`f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4` ✅
- `docs/cli_ci_scenarios.json` SHA-256：`7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef` ✅
- 未修改 production、tests、oracle/scenario、design truth
- 未 stage/commit/push

## Finding 最终状态汇总

| 来源 | 原 finding | 最终状态 |
|---|---|---|
| MiMo-001 | Ambiguity 常量未指定 | `已修复` |
| MiMo-002 | Chunk read size 未指定 | `证据失效` |
| MiMo-003 | Ctrl+C 未显式排除 classifier | `已修复` |
| MiMo-004 | ESC+普通字符与 Alt 不可区分 | `已修复` |
| MiMo-005 | Deadline 后 continuation 才到达 | `已修复` |
| DS-F1 | 常量值未指定（= MiMo-001） | `已修复` |
| DS-F2 | Conservative armed deadline | `已修复` |
| DS-F3 | `_ActiveTurnCloseout` 外部副作用边界 | `已修复` |
| DS-F4 | Known-meta key+data 双重条件 | `已修复` |
| DS-F5 | `RunningKeyAction` 唯一 contract | `已修复` |
| DS-F6 | Paste end + Ctrl+T 同 batch | `已修复` |

## Gate Verdict

**pass**

所有 11 项 finding 已通过复核：10 项 `已修复`，1 项 `证据失效`（controller 基于直接证据拒绝，不要求修改）。所有 controller required actions 已落实到两份计划 artifact 中。核心方案（provisional Escape + conservative armed deadline + feed/flush batch classification）保持不变，补充了 0.1s 常量、key+data 双重条件、SIGINT-only Ctrl+C、`RunningKeyAction` 唯一 contract、paste+CtrlT 覆盖和 `_ActiveTurnCloseout`/outer cleanup 边界。

修订后的 S3 plan correction 足够 code-generation-ready，可以交给 implementation agent。

## Residual Risks

| 风险 | 等级 | 覆盖方式 |
|---|---|---|
| ESC+普通字符与 Alt 在 0.1s 内不可区分 | MEDIUM/ACCEPTED | Terminal 物理限制；S3 owner test 记录，S8 PTY evidence |
| Continuation 晚于 0.1s 到达 | LOW | S3 代表性跨 chunk + S8 真实 PTY timing |
| Resolved dependency 改变 public synchronous callback shape | LOW | S3 public seam contract test fail closed |
| 0.1s 值在极端环境下可能不当 | LOW | 可控 clock seam 测试覆盖 boundary；S8 real PTY 验证 |

没有 unclassified residual risk，没有 blocking open question。
