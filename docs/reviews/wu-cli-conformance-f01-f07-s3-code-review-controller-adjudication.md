# WU-CLI-CONFORMANCE-F01-F07 S3/F03 Code Review — Controller Adjudication

## Gate 元数据

- Work unit：`WU-CLI-CONFORMANCE-F01-F07`
- Slice：`S3 / F03`
- Gate：`code review -> controller adjudication`
- Entry HEAD：`fc1b4946`
- Review artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-ds.md`
- 状态：`TEST FIX REQUIRED — production design accepted，无 blocking open question`

## 总体裁决

MiMo 对九个指定 adversarial focus area 未发现实质 finding。DS 的 artifact 记录了七个标题项，但 F02-F06 在正文中都自行证明为正确路径；F01 的标题标为“严重”而正文最终 severity 为低，且建议存在二选一。总控不能用两路 verdict 一致替代逐项证据，因此按 accepted S3 plan §5、直接代码和测试逐项裁决如下。

## Finding 逐项裁决

| 来源 / finding | 裁决 | 直接理由与 required action |
|---|---|---|
| MiMo：无实质 finding | `accepted` | 单 parser/decoder、batch truth、SIGINT owner、acceptance barrier、Host terminal、130 cleanup偏序与182项 focused tests证据成立。真实 PTY timing继续由已批准S8覆盖。 |
| DS-F01：readable EOF + deadline | `rejected-as-code-defect; accepted-as-test-gap` | Accepted plan §5.2(9)和§5.3明确规定 close/EOF不得为了清空parser合成flush或新action；在EOF前调用`parser.flush()`会把pending Escape合成为cancel，正是被禁止的语义。当前`data == b""`直接return是正确owner行为。接受唯一测试缺口：新增确定性case，证明deadline已armed且readable返回EOF时零action、零flush/cancel。不得改production。 |
| DS-F02：exit-after-closeout + queued follow-up | `rejected-with-reason` | Reviewer完整路径走读已证明normal completion会提升并等待queued terminal，exception cleanup才取消tasks；其正文明确“无实际问题”。此外该项大量引用非本S3 plan的F09/§6契约，不能作为本slice finding。 |
| DS-F03：terminal/accepted同轮 | `rejected-with-reason` | 正文证明三种`FIRST_COMPLETED`集合均正确收敛，terminal truth优先；无反例。 |
| DS-F04：second signal保持CANCELLING | `rejected-with-reason` | 正文证明符合contract；无缺陷。 |
| DS-F05：non-TTY outer trim | `rejected-with-reason` | 该行为未由S3引入，且正文证明TTY/non-TTY一致；不属于F03。 |
| DS-F06：cleanup-only error传播 | `rejected-with-reason` | 正文证明primary-vs-cleanup传播正确；无缺陷。 |
| DS-F07：`_pending_submit`防御恢复无显式测试 | `rejected-for-current-slice` | Reviewer承认当前实际路径不存在触发场景，并错误引用非本S3 plan §6；没有证明本次F03变更破坏contract。不能把未证实的防御测试扩张为当前验收标准。 |
| DS-OQ01 / RR01：paste/late continuation与EOF | `classified` | 0.1s后才到达continuation是accepted terminal residual，由S3代表性分块和S8 real PTY覆盖；EOF test按F01 required action补齐。 |
| DS-OQ02：thread start restore | `evidence-valid/pass` | 已有owner test覆盖；无需修改。 |
| DS-OQ03：多个Ctrl+T | `rejected-as-risk` | 多个独立typed toggle按顺序投递是用户多次输入的直接语义，不是丢失或重复；不新增文档承诺。 |
| DS-OQ04：Ctrl+D | `rejected-out-of-scope` | Reviewer已证明符合既有composer行为，且不是F03 finding。 |
| DS-RR02：`_pending_submit` | `rejected-for-current-slice` | 同DS-F07。 |
| DS-RR03：CANCELLING期间Enter | `rejected-out-of-scope` | Artifact引用了错误的S2/F09与§6语义；当前S3 frozen truth只定义Escape/Ctrl+C cancel与退出收口，不重新裁决既有queued-submit产品语义。没有直接证据表明本diff新增第二Run或违反本slice accepted oracle。 |

## Required fix

AgentCodex 只需：

1. 在 `tests/cli/test_run_keys.py` 增加 readable EOF 与已armed deadline同轮时零action的owner test，明确EOF/close不flush、不合成cancel；
2. 新增 `docs/reviews/wu-cli-conformance-f01-f07-s3-fix-codex.md`，逐项记录上述裁决状态；
3. 运行 `tests/cli/test_run_keys.py`、四文件focused suite、focused/full pyright、coverage与diff/hash检查；
4. 不修改production、其它test、plan、oracle/scenario/design/README，不stage/commit/push。

修订后由MiMo/DS做独立 re-review。没有未分类 residual risk或 blocking open question。

## Artifact path

`docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-controller-adjudication.md`
