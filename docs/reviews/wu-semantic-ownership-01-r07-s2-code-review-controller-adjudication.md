# WU-SEMANTIC-OWNERSHIP-01 R07-S2 cumulative code review Controller adjudication

## 1. Gate 与输入

- Active WU：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- Internal remediation sub-WU：R07；checkpoint：累计 S1+S2 complete code review。
- AgentMiMo artifact：`docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-mimo.md`，verdict `PASS`，0 material finding，0 blocker，2 observations。
- AgentDS artifact：`docs/reviews/wu-semantic-ownership-01-r07-s2-code-review-ds.md`，verdict `PASS WITH 1 MATERIAL FINDING`，1 material finding，0 blocker，5 observations。
- Controller 已完整读取两份 artifact；reviewer verdict 不自动授权下一 gate。

## 2. Finding 裁决

### `R07-S2-CR-F01` — consumer snapshot close failure masks active primary failure

- 来源：AgentDS `R07-S2-DS-F01`。
- 严重度：**Medium**。
- Controller 裁决：**ACCEPTED / FIX REQUIRED NOW**。
- 直接证据：
  - `dayu/fins/ingestion_runtime.py`、`dayu/fins/pipelines/sec_fiscal_fields.py`、`dayu/fins/pipelines/sec_6k_primary_document_repair.py` 均使用 `finally: snapshot.close()`。
  - 当 processor/fiscal/6-K 业务路径已有主失败且 snapshot temp-root cleanup 同时失败时，Python 会把 close failure 作为最外层异常，原始业务失败只留在 raw `__context__`；这与本累计树已建立的 primary-preservation/path-free exception graph 语义不一致。
  - Batch safety 本身不回退，但最外层错误原因 owner 被 cleanup secondary 覆盖，属于当前 S2 resource lifecycle 缺口，不能推迟为“后续优化”。
- 唯一 owner：storage snapshot resource lifecycle。consumer 只应使用 owner 提供的生命周期操作，不应在三个下游各自实现 `sys.exc_info()`、异常 note 或 cleanup fallback。
- 最小修复边界：
  1. 由 snapshot protocol/private implementation 提供一个统一的 Python context-manager lifecycle；具体实现类名、retry budget、temp locator 继续 private。
  2. resource owner 的 exit 语义必须是：无 active primary 时 close failure 正常传播；有 active primary 时保留 active primary，close failure 只通过现有 `_append_secondary_error_note(...)` 追加 path-free action/type/errno；不得保留 raw close exception cause/context/message/path。
  3. 三个 S2 consumers 全部改为消费同一 lifecycle，不得各自复制 exception-preservation helper，不得新增 public glue/facade 或 compatibility branch。
  4. 在现有获准测试文件补 owner-level 双失败测试：至少覆盖 active primary + close secondary、无 primary + close primary、完整 exception graph path-free；并通过 consumer source/behavior tests 证明三个 consumer 已切换且原业务算法/rollback/commit 顺序不变。
- 禁止项：不得借机进入 S3 cache/borrow/read-runtime migration；不得设计新的通用 resource framework；不得改变 `close()` 的显式、幂等、失败后可重试 contract；不得吞掉无 active primary 的 close failure。

### 其余 reviewer observations

| 项目 | Controller 裁决 |
|---|---|
| MiMo OBS-1 imports | **not a finding**：artifact 自己确认 `ProcessedHandle` 等由 `isinstance` 消费，scoped Ruff 通过。 |
| MiMo OBS-2 existing `Any` | **no-action / outside accepted S2 diff**：为 pre-existing typed debt，不允许借 R07-S2 扩大修改。 |
| MiMo residual direct tests | **no-action**：当前 owner contract 已由真实 filesystem 集成路径覆盖且 changed production coverage 达标；不得以建议为由新建测试文件或扩大 S2 allowlist。 |
| MiMo null/control/whitespace identity note | **rejected design alternative remains rejected**：当前裁决是 exact opaque nonempty UTF-8 identity，filename/path channel 另行严格验证。 |
| DS O01–O05 | **design confirmations / no-action**：private revision algorithm、light validation chain、private retry limit、snapshot-local materialize 与 fiscal best-effort 均符合 accepted plan。 |
| existing Ruff 152 / edgar warnings | **pre-existing evidence only**，不转化为当前 accepted finding。 |

## 3. Ledger

| 类别 | 数量 | 状态 |
|---|---:|---|
| accepted material finding | 1 | `R07-S2-CR-F01` open，必须当前修复 |
| rejected/no-action observation | 8 groups | closed with reason |
| deferred accepted scope | S3 read-runtime/cache/borrow only | 保持 deferred，不是 finding destination |
| blocker | 0 | — |

S1 `R07-S1-CR-F01..03` / `R07-S1-CR-CV-F01` 与 S2 `R07-S2-CV-F01..03` 均保持关闭。当前唯一 open accepted finding 是 `R07-S2-CR-F01`。

## 4. Next gate

下一 gate 是 AgentCodex 在累计 S1+S2 worktree 内完成 `R07-S2-CR-F01` exact-scope fix、测试与 fix artifact；随后 Controller validation 和 AgentMiMo/AgentDS 双路完整累计 S1+S2 re-review。未授权 S1/S2 commit、S3、R08+、Issue 142/151/175/177/178、统一 authorization、push 或 PR。
