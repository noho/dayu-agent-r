# WU-CLI-CONFORMANCE-F01-F07 S3/F03 Code Re-Review（MiMo）

## Scope

- Mode: re-review（controller adjudication + fix artifact + new test diff）
- Branch: `codex/interactive-oracle`
- Base: `fc1b4946`
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s3-code-rereview-mimo.md`
- Input artifacts：
  - `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-controller-adjudication.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s3-fix-codex.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-mimo.md`（原 review）
  - `docs/reviews/wu-cli-conformance-f01-f07-s3-code-review-ds.md`（原 review）
- Included scope: `tests/cli/test_run_keys.py`（新增 test diff）+ 三个 production files（完整性核对）
- Excluded scope: production 代码未修改（controller 裁决 production design accepted）

## Validation

```bash
# 四文件测试套件
pytest -q tests/cli/test_run_keys.py tests/cli/test_prompt_command.py tests/cli/test_interactive_composer.py tests/cli/test_interactive_command.py
# 结果：183 passed, 3 warnings in 9.79s

# pyright
python -m pyright dayu/cli/run_keys.py dayu/cli/session_execution.py dayu/cli/composer.py
# 结果：0 errors, 0 warnings, 0 informations
```

## Finding 逐项核对

### DS-F01：readable EOF + armed deadline

- **总控裁决**：`rejected-as-code-defect; accepted-as-test-gap`
- **Required action**：不改 production；增加 armed deadline + readable EOF 零 flush/零 action test
- **Fix 最终状态**：`已修复`

**核对**：

1. **Production 未修改**：`git diff dayu/cli/run_keys.py` 为空，确认 production 无变更。
2. **新增测试存在**：`test_reader_readable_eof_wins_over_armed_deadline_without_flush`（行 542-567）。
3. **测试正确覆盖 required scenario**：
   - 第一轮：`b"\x1b"` → readable=True → feed Escape → deadline armed
   - 第二轮：`b""` → readable=True → EOF → 零 flush/零 action
   - 断言 1：`actions == ()` — 零 action，不产生 `CANCEL_RUN`
   - 断言 2：`resolution_kinds == ["feed"]` — 只有 feed，没有 flush
4. **Recording parser 扩展正确**：`_RecordingVt100Parser` 新增 `resolution_kinds` 字段（行 186），`feed` 和 `flush` 方法分别记录 `"feed"` 和 `"flush"`（行 209、220）。
5. **测试通过**：183 passed（比原 182 多 1 个）。

**结论**：唯一 required action 已正确完成。production 设计不变，test gap 已补齐。

### DS-F02：exit-after-closeout + queued follow-up

- **总控裁决**：`rejected-with-reason`
- **Required action**：无
- **Fix 最终状态**：`证据失效`

**核对**：DS reviewer 正文已证明 normal completion 会提升并等待 queued terminal，exception cleanup 才取消 tasks。无反例。无需修改。

### DS-F03：terminal/accepted 同轮

- **总控裁决**：`rejected-with-reason`
- **Required action**：无
- **Fix 最终状态**：`证据失效`

**核对**：DS reviewer 正文证明三种 `FIRST_COMPLETED` 集合均正确收敛，terminal truth 优先。无需修改。

### DS-F04：second signal 保持 CANCELLING

- **总控裁决**：`rejected-with-reason`
- **Required action**：无
- **Fix 最终状态**：`证据失效`

**核对**：DS reviewer 正文证明符合 second Ctrl+C intent-only contract。无需修改。

### DS-F05：non-TTY outer trim

- **总控裁决**：`rejected-with-reason`
- **Required action**：无
- **Fix 最终状态**：`证据失效`

**核对**：该行为未由 S3 引入，且 TTY/non-TTY 语义一致。不属于 F03。无需修改。

### DS-F06：cleanup-only error 传播

- **总控裁决**：`rejected-with-reason`
- **Required action**：无
- **Fix 最终状态**：`证据失效`

**核对**：DS reviewer 正文证明 primary-vs-cleanup 传播正确。无需修改。

### DS-F07：`_pending_submit` 防御恢复测试

- **总控裁决**：`rejected-for-current-slice`
- **Required action**：无
- **Fix 最终状态**：`证据失效`

**核对**：Reviewer 承认当前实际路径不存在触发场景，且错误引用非本 S3 plan §6。没有证据证明 F03 diff 破坏该 contract。不扩张本 slice。

### MiMo：无实质 finding

- **总控裁决**：`accepted`
- **Required action**：无 production fix；保留九项 pass evidence
- **Fix 最终状态**：无 finding，状态不适用

**核对**：原 MiMo review 的九项 adversarial 检查点全部通过，无 finding。controller 已接受。

## Open Questions / Residual Risks 裁决核对

| 来源 | 总控 disposition | 核对结果 |
|---|---|---|
| DS-OQ01 / RR01：paste late continuation 与 EOF | `classified` | EOF test gap 已 fix；0.1s late continuation 为 accepted terminal residual，由 S8 覆盖 ✓ |
| DS-OQ02：thread start restore | `evidence-valid/pass` | 既有 owner test 已覆盖 ✓ |
| DS-OQ03：多个 Ctrl+T | `rejected-as-risk` | 每个 typed toggle 按输入顺序投递是直接语义 ✓ |
| DS-OQ04：Ctrl+D | `rejected-out-of-scope` | 非 F03 finding ✓ |
| DS-RR02：`_pending_submit` | `rejected-for-current-slice` | 不扩张本 slice ✓ |
| DS-RR03：CANCELLING 期间 Enter | `rejected-out-of-scope` | 引用了错误的非 S3 contract ✓ |

## Integrity

- Production 文件未修改：`git diff dayu/cli/run_keys.py dayu/cli/session_execution.py dayu/cli/composer.py` 均为空 ✓
- 新增测试正确：`test_reader_readable_eof_wins_over_armed_deadline_without_flush` 覆盖 required scenario ✓
- 测试通过：183 passed ✓
- Pyright：0 errors ✓
- Frozen registry SHA-256 不变（fix artifact 记录的值与 implementation artifact 一致）✓

## Verdict

**PASS。** 唯一 required action（readable EOF + armed deadline 零 flush/零 action test）已正确完成。Production 设计不变。其余 DS findings 全部被 controller rejected，未被扩张。无未修复或部分修复 finding。无 unclassified residual risk。

## Residual Risk

- **MEDIUM / covered by later S8 evidence**：真实终端分块、ESC/Alt 固有 0.1s ambiguity、不同 provider/tool/closeout timing 与完整 live PTY scenario evidence。当前 implementation 按 frozen oracle 抑制 ambiguity batch 的 Escape cancel。
- **LOW / inherent design**：`_read_loop` 的 `select` 超时粒度为 0.05s，在极端负载下可能导致 Escape 解析延迟最多 0.05s。不影响正确性。
