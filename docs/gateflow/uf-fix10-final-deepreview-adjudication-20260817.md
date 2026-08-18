# UF-FIX10 final deepreview adjudication

## Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- gate：`final deepreview fix adjudication`
- 日期：2026-08-17
- base：`656b926c`（UF-FIX10 首个提交的直接父提交）
- reviewed commits：`46972e72..047691c8`
- reviewed artifacts：
  - `docs/reviews/code-review-20260817-033113.md`（AgentMiMo）
  - `docs/reviews/code-review-20260817-034314.md`（AgentDS）
- scope：只允许补强 `tests/fins/test_sec_pipeline_upload_filing_stream.py`、本 gate/fix/closeout
  artifacts 与 plan metadata；禁止生产代码、README、oracle/scenario/registry/evidence、UF-PF10/12

## 结论

MiMo final deepreview 为 pass；DS 同样确认生产 correctness、stability、maintainability、唯一
语义 owner、linearization、typed failure、cancellation/rollback、same/different ticker 与 scope
均通过，但发现 accepted plan §10.2 三个低严重度端到端证据缺口。三项均是已冻结验收断言，
不能以 owner 级间接覆盖替代，全部接受并只在 SEC workflow test owner 内补齐；不授权任何
生产改动。

## Findings 裁决

### D-F1 — multi-file concurrent loser events / winner snapshot

- 裁决：`accepted-low`。
- 根因：现有并发 case 只断言 final status/count/token 与 durable COMPLETE，没有证明 loser 的
  `FILE_SKIPPED` 覆盖 primary+companion 全部 originals，也没有把 durable publication identity
  与 winner prepared target 做 exact 对照。
- 修复边界：在真实 SEC stream 并发路径捕获每个 caller 的事件序列；loser 必须逐 original
  `FILE_SKIPPED` 且无 conversion events，winner 的 durable role/assets/manifest 必须与其 prepared
  snapshot exact equal。不得复制 production identity 计算逻辑；复用既有 owner projection/helper。

### D-F2 — same-ticker different-filing union 缺 manifest/assets exact union

- 裁决：`accepted-low`。
- 根因：两个 document 各自 COMPLETE 与 alias union 只能间接证明，没有固定 ticker-level filing
  manifest 与 asset 集在第二次 commit 后保留 first+second exact union。
- 修复边界：从 repository/storage owner 公开读面读取最终 manifest/filing state，断言两个 exact
  document IDs 及各自 assets 均存在且无额外项；保持 alias union 断言。禁止目录扫描或 raw
  consumer 绕过仓储 owner。

### D-F3 — concurrent create-overwrite rebase durable invariants 缺端到端断言

- 裁决：`accepted-low`。
- 根因：owner helper 单测证明 rebase 规则，但并发 workflow case 没有证明后 writer 确实使用
  fresh winner meta。
- 修复边界：在真实并发 create+overwrite route 记录两个 commit 的 owner-level source meta/
  revision snapshot，断言后 commit 保持 winner `first_ingested_at/created_at`、同 fingerprint
  document_version 不增加，并由 storage owner 写入不同 opaque revision；不得用时间窗口、sleep、
  目录扫描或内部路径猜测。

## 修复后验证要求

- 三项定点 SEC tests；
- accepted UF-FIX10 focused suites；
- 完整 `pytest tests/fins -q`；
- 全仓 `python -m pyright dayu/ tests/ utils/`；
- `git diff --check` 与 scope audit；
- 两路 final deepreview re-review 均 pass 后进入 final closeout commit。

禁止运行 UF-PF10/UF-PF12；禁止修改生产、README、oracle/scenario/registry/frozen evidence；
禁止新增 sleep/retry/polling、目录扫描、generic exception fallback 或测试专用生产 hook。
