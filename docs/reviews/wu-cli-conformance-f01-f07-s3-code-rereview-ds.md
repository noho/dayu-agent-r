# Code Re-Review — S3/F03 Implementation (WU-CLI-CONFORMANCE-F01-F07)

## Scope

- Mode: current changes (uncommitted workspace), re-review after controller adjudication + fix
- Branch: `codex/interactive-oracle`
- Base: `fc1b4946`
- Prior review: `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-ds.md`
- Controller adjudication: `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-cli-conformance-f01-f07-s3-fix-codex.md`
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s3-code-rereview-ds.md`
- Included scope: 7 changed files（同首轮），加新增 fix artifact 与仅 test 的 delta
- Excluded scope: Host、Service、Engine、registry、design、README
- Parallel review coverage: 无

## Controller Adjudication Summary

总控对首轮 DS review 的全部 7 个 titled findings 与 4 个 open questions / 3 个 residual risks 逐项裁决：

- **唯一 required action**：DS-F01 的 test gap——新增 `armed deadline + readable EOF` 确定性 owner test，证明零 flush、零 action、零 cancel。**production 不改**。
- 其余 DS-F02 至 DS-F07 全部 `rejected`（正文自证正确/引用非 S3 contract/无直接证据证明 F03 diff 破坏现有行为）。
- OQ01/RR01 分类为 `classified`（EOF test gap 本次修复，late continuation 由 S8 覆盖）。
- OQ02/OQ03/OQ04/RR02/RR03 分别 `evidence-valid`、`rejected-as-risk`、`rejected-out-of-scope`。

## Fix Verification

### Production 不变检查

`dayu/cli/run_keys.py`、`dayu/cli/session_execution.py`、`dayu/cli/composer.py` 的 diff 与首轮 review 完全一致——未增加任何 production 修改。

确认 `running_key_action_from_bytes` 从 production 与 tests 中彻底删除（`grep` 零命中），旧 raw-byte action helper 不再存在。

### 新增 test

`tests/cli/test_run_keys.py` 新增确定性 owner test `test_reader_readable_eof_wins_over_armed_deadline_without_flush`（第 542 行）：

1. 第一轮 scripted `select` 返回 readable，`os.read` 返回 `b"\x1b"` → parser feed 接收 `\x1b`，deadline armed
2. 第二轮 clock 精确推进 `0.1s`，`select` 返回 readable + `os.read` 返回 EOF `b""`
3. `_RecordingVt100Parser.resolution_kinds` 断言为 `["feed"]`——证明 **零 flush**
4. queue actions 断言为 `()` ——证明 **零 action、零 cancel**

该测试使用已有的 `_ScriptedSelectClock`、`_ScriptedRead`、`_RecordingVt100Parser`、`_RecordingEventLoop` 和 `_run_scripted_reader` seam，不建立第二 parser、不读取 production private state、不通过 fake 改写 owner 语义。测试的 parser resolution thread id 记录验证 production 的 parser 构造与 resolution 都在 reader thread 内。

### Validation

- Focused pytest（四文件 suite）：`183 passed, 3 warnings in 9.84s`（首轮 182 passed → 新增 1 test）
- Focused pyright：`0 errors, 0 warnings, 0 informations`
- `running_key_action_from_bytes` 全仓零命中

## Finding 最终状态核对

按总控裁决逐项核对，每项仅用 `已修复` / `部分修复` / `未修复` / `证据失效`：

| 来源 / finding | 首轮判定 | 总控裁决 | 当前状态 | 证据 |
|---|---|---|---|---|
| DS-F01：readable EOF + deadline | 低 severity，二选一建议 | `rejected-as-code-defect; accepted-as-test-gap` | **已修复** | 新增 `test_reader_readable_eof_wins_over_armed_deadline_without_flush`；production 未改，EOF 直接 return 正确落实 accepted plan §5.2(9)/§5.3 的 "close/EOF 不合成 flush 或 action" contract |
| DS-F02：exit-after-closeout + queued | 自证正确，无实际缺陷 | `rejected-with-reason` | **证据失效** | 首轮正文已完整走读证明 normal completion 路径正确，且引用非 S3 F09/§6 contract；总控确认无反例 |
| DS-F03：terminal/accepted 同轮 | 自证正确 | `rejected-with-reason` | **证据失效** | 首轮正文证明三种 `FIRST_COMPLETED` 集合均正确收敛，terminal truth 优先 |
| DS-F04：second signal CANCELLING | 自证正确 | `rejected-with-reason` | **证据失效** | 首轮正文证明 second Ctrl+C 只登记 exit-after-cancel，不改变 composer phase，符合 contract |
| DS-F05：non-TTY outer trim | 设计一致 | `rejected-with-reason` | **证据失效** | 非 S3 引入行为，TTY/non-TTY 路径一致 strip，不属于 F03 finding |
| DS-F06：cleanup-only error 传播 | 自证正确 | `rejected-with-reason` | **证据失效** | 首轮正文证明 primary-vs-cleanup 传播正确，`__cause__` 链保持 primary identity |
| DS-F07：`_pending_submit` 防御测试 | 低 severity，建议新增测试 | `rejected-for-current-slice` | **证据失效** | 无直接证据证明 F03 diff 破坏该 contract；当前实际路径不存在触发场景 |
| MiMo review：9 项 adversarial check | 全部 pass | `accepted` | **不适用** | MiMo 未发现实质 finding；总控确认九项 pass evidence 成立 |

## Open Questions / Residual Risks 最终状态

| 来源 | 总控 disposition | 当前状态 |
|---|---|---|
| DS-OQ01/RR01：paste late continuation 与 EOF | `classified` | EOF test gap 已在本 slice 修复；0.1s late continuation 为 accepted terminal residual，由 S8 real PTY evidence 覆盖 |
| DS-OQ02：thread start restore | `evidence-valid/pass` | 既有 test 已覆盖；无需修改 |
| DS-OQ03：多个 Ctrl+T | `rejected-as-risk` | 每个 typed toggle 按输入顺序投递是直接语义；无需修改 |
| DS-OQ04：Ctrl+D | `rejected-out-of-scope` | 符合既有 composer 行为，不是 F03 finding |
| DS-RR02：`_pending_submit` | `rejected-for-current-slice` | 同 DS-F07 |
| DS-RR03：CANCELLING 期间 Enter | `rejected-out-of-scope` | 引用非 S3 contract；本 fix 不重新裁决 queued-submit 语义 |

## Integrity 检查

- 两路 review（MiMo + DS）均已产生 durable artifact，总控已逐项裁决并记录于 fix artifact
- 新增 test 仅扩展现有 `_RecordingVt100Parser` 的 `resolution_kinds` 记录，不引入新 seam 类型
- 四个 test 文件 183 个 test 全绿，pyright 零 error
- `running_key_action_from_bytes` 从 production 与 tests 中彻底删除（`grep` 零命中）
- two frozen registry SHA-256 未变（`docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`）
- 未修改 production、其它 test、plan、oracle/scenario、design、README；未 stage/commit/push

## Gate Verdict

**PASS** — re-review 通过。

总控唯一 required action（DFS-F01 test gap）已精确修复：新增确定性 owner test 证明 `armed deadline + readable EOF` 路径零 flush、零 action、零 cancel，production 未做任何修改。其余全部 finding 按总控裁决归为 `证据失效`，无扩张、无新增 finding、无未修复项。

183 个 focused test 全绿，pyright 零 error/warning。无 unclassified residual risk，无 blocking open question。
