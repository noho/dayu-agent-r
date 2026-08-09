# WU-CLI-CONFORMANCE-F01-F07 S3 Plan Correction — Controller Adjudication

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Slice：`S3 / F03`
- Gate：`plan review -> controller adjudication`
- Entry HEAD：`16c6ddc8`
- Review artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-review-ds.md`
- 状态：`FIX REQUIRED — 核心方案 accepted，无 blocking open question`

## 独立证据裁决

两路 review 都用当前 resolved `prompt_toolkit==3.0.52` public `Vt100Parser` 复验了同一事实：`feed("\x1b")` 不回调，deadline `flush()` 才产生单一 standalone Escape；Alt+X 同 chunk 或跨 chunk 都在最终 `feed()` resolution batch 中产生 `Escape, X`；完整 CSI/SS3/Home/Delete、known meta tuple 与 bracketed paste 有不同 callback shape。因此用户批准的“resolution batch 完成后再投影 provisional Escape”方案成立，owner 仍是 CLI reader thread 的 public parser callback 到 typed local intent 边界，不改变 Host cancellation/terminal owner。

## Finding 逐项裁决

| 来源 / finding | 裁决 | 理由与 required action |
|---|---|---|
| MiMo-001 / DS-F1：ambiguity 常量未指定 | `accepted` | 该值影响 standalone Escape 响应与 continuation 等待，implementation 不应自行作产品级选择。固定 `_ESCAPE_SEQUENCE_AMBIGUITY_SECONDS = 0.1`，与当前 public prompt_toolkit 默认 escape timeout 量级一致；测试用可控 clock/select seam，不用 wall-clock 脆弱等待。 |
| MiMo-002：chunk read size 未指定 | `rejected-with-reason` | callback correctness 由 incremental decoder + public parser resolution boundary 决定，不依赖某个 read size。把 1024 等具体值写进 plan 只会硬编码非语义性能参数；owner tests 已覆盖代表性分块。implementation 可保留或选择合理 chunk size，但不得据此改变 batch 定义。 |
| MiMo-003：Ctrl+C 未显式排除 classifier | `accepted`（clarity） | Ctrl+C 继续由 SIGINT monitor 拥有，不经过 VT100 batch classifier；plan/fix artifact 应明确，防止建立第二个 signal owner。 |
| MiMo-004：ESC+普通字符与 Alt 不可区分 | `accepted-as-residual` | 这是 terminal byte protocol 的物理限制，不是可修代码 finding。冻结 oracle 要求 Alt 不误取消，因此 ambiguity window 内相同 bytes 统一不 cancel；由 S3 owner tests 与 S8 PTY evidence 记录，不新增 oracle/scenario。 |
| MiMo-005：deadline 后 continuation 才到达 | `accepted-as-residual` | 任意有限 timeout 都不能证明无限迟到 continuation；0.1s 是明确边界。正常与代表性跨 chunk 在 S3 测，真实 PTY timing 在 S8；不扩张为网络 terminal protocol。 |
| DS-F2：完整 sequence 后 deadline 未清除 | `rejected-as-functional-finding; accepted-as-clarity-fix` | 不访问 parser private state时，callback batch不能证明 parser 没有尾随 pending prefix；例如同一 feed 可先产出普通 key 又以 ESC 结尾。按“non-empty batch 就清 deadline”的建议会丢失真正 pending ESC。正确最小规则是 conservative armed deadline：含 ESC 后设置/刷新，若 sequence 已解析则到期做一次空 flush 并立即清除；新非空 chunk在到期同轮优先 feed 并刷新。plan 要明确一次 no-op flush 是预期行为、不会循环或重复 cancel。 |
| DS-F3：`_ActiveTurnCloseout` 隐式副作用边界 | `accepted-in-part` | 接受补足 method contract 与 prompt/interactive 时序；拒绝让 `wait_closeout()` 拥有 composer、display、cursor、attachment cleanup，因为这会违反已批准的最小 shared coordinator boundary。coordinator 只拥有 acceptance、cancel intent、exactly-once Host cancel task、canonical terminal observation；outer driver 明确拥有 composer phase、display finish、cursor advance、attachment/key/signal teardown，并在这些 cleanup 后才决定 130。 |
| DS-F4：known meta tuple 必须精确检查 data | `accepted`（clarity/test） | plan 已写精确 `KeyPress(Keys.Escape, "\x1b")`，但 fix 应再明确 `key` 与 `data` 双重条件，并加入 known-meta callback test，避免只按 key 类型误取消。 |
| DS-F5：`RunningKeyAction` 与 `_PromptControlKey` 重复 | `accepted` | 同一 typed key 语义不应有两个 enum。保留现有 `RunningKeyAction` 作为 `run_keys` 唯一 public typed contract，删除计划中的 `_PromptControlKey`；coordinator/driver 直接消费 `RunningKeyAction`。 |
| DS-F6：paste end 与 Ctrl+T 同 batch | `accepted` | 明确 `BracketedPaste` 自身 no-op，同 batch 后续 callback 仍独立分类；新增 `[BracketedPaste, ControlT]` 只 toggle 一次的 owner test。 |

## Required fix

AgentCodex 在不改 frozen truth、production 或 tests 的前提下：

1. 更新主 plan §5 与 plan-correction artifact，落实上述 accepted 项；
2. 新增 `docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-fix-codex.md`，逐项记录状态；
3. 保持单一 public parser/decoder、reader-thread owner、Host terminal owner和原 acceptance/double-Ctrl+C 语义；
4. 不采用 reviewer 建议中“从空/非空 callback 推断 parser private pending state”的错误规则；
5. 不修改 production、tests、oracle/scenario，不 stage、commit、push。

修订后进入两路 plan re-review。没有 blocking open question；所有 residual risk 已分类为 S3 owner tests 或已批准 S8 real PTY evidence 覆盖。

## Artifact path

`docs/reviews/wu-cli-conformance-f01-f07-s3-plan-correction-controller-adjudication.md`
