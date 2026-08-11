# `WU-CLI-DOWNLOAD-02-DL-F12-F14` Plan Re-review Fix Loop 2

## 1. Gate 与范围

- Work unit：`WU-CLI-DOWNLOAD-02-DL-F12-F14`
- Gate：plan re-review -> fix loop 2
- 日期：2026-08-10
- 修复对象：`docs/gateflow/wu-cli-download-02-plan-20260810.md`
- Re-review inputs：`docs/reviews/plan-review-20260810-164812.md`、`docs/reviews/plan-review-20260810-164911.md`
- 裁决真源：`docs/gateflow/wu-cli-download-02-plan-review-adjudication-20260810.md` 的“第一轮 re-review 裁决”
- Changed files：修订原 plan；新增本 artifact
- 明确未做：产品代码、tests、README、CLI、pytest、pyright、coverage、commit、push、PR
- Completion status：`fix complete / next=second MiMo+DS re-review`
- Artifact path：`docs/gateflow/wu-cli-download-02-plan-fix-2-20260810.md`

## 2. 第一性原理与直接代码复核

本轮不是设计方向变化，而是实施切片边界与措辞精度修复。四项裁决均由当前代码直接证实：

- `dayu/fins/pipelines/cn_report_selection.py:144` 与 `:198` 直接消费 `query.target_periods`；Slice 2 重命名 query 字段时不迁移这两处会立即破坏 typed contract。
- `CN_FISCAL_PERIOD_ORDER` 在 Slice 2 的 form policy 首次需要，故必须在 Slice 2 定义；Slice 3 只能复用，不能重复定义。
- `dayu/fins/domain/filing_semantics.py:79` 已存在 `FISCAL_PERIODS`，它拥有通用 period membership，无需创建新模块或替代常量。
- 当前 `commit_cn_filing_source_document(...)`、`_build_base_meta(...)`、`_build_upsert_request(...)` 都接收 `form_type`。正确边界是移除前两个 caller-facing 输入，使 identity 只来自 candidate；最后一个内部 builder 继续显式接收已派生的局部值。

动机成立且严重性没有被高估：DS N1 会使 Slice 2 无法独立通过 pyright，是 blocking allowed-files gap；其余三项是消除实现歧义所需的最小文档修复。没有引入新类型、fallback、兼容代码或额外 scope。

## 3. 逐 finding 修复证据

### DS N1：`cn_report_selection.py` 未纳入 Slice 2 — `已修复`

- 裁决：接受，blocking。
- Plan changes：
  - Slice 2 allowed production files 新增 `dayu/fins/pipelines/cn_report_selection.py`。
  - Slice 2 exact change 明确迁移当前两处 `query.target_periods -> query.discovery_periods`，且只做机械 rename。
  - Slice 2/3 共有文件边界新增该文件：Slice 2 只做 query rename；Slice 3 才做 category-first classification、candidate projection 与 selection sort。
  - 共有文件说明明确 Slice 2 完成后必须独立通过 pyright，不得提前修改 classifier/candidate schema。
- Test scope：`tests/fins/test_cn_report_selection.py` 已在 Slice 2、Slice 3 allowed tests 与 focused union 中，无需新增 test file。
- Plan evidence：§6 Slice 2 allowed files/items 1-2、共有文件边界表。

### DS N2：`CN_FISCAL_PERIOD_ORDER` slice 归属不清 — `已修复`

- 裁决：接受。
- Plan changes：
  - §5.2 明确常量在 Slice 2 首次定义并由 form policy 使用。
  - 共有文件表明确 `cn_download_models.py` 的 Slice 2 负责定义常量与 query rename。
  - Slice 3 的 `CnReportPeriodProjection` 和 `cn_report_selection.py` sort 只复用既有常量，不重新定义或内联排序 tuple。
- Plan evidence：§5.2、§6 Slice 2 item 1、共有文件边界表。

### MiMo C01：`FISCAL_PERIODS` 是否存在 — `已修复`

- 裁决：按直接代码证据关闭。
- Direct evidence：`dayu/fins/domain/filing_semantics.py:79` 定义
  `FISCAL_PERIODS: Final[frozenset[FiscalPeriod]]`，成员为 `FY,H1,Q1,Q2,Q3,Q4`。
- Plan changes：§5.3 明确该符号已存在，公共 result/public document 直接复用它做 membership 校验；不创建新模块、常量或替代校验真源。
- Ownership：`FISCAL_PERIODS` 拥有通用 membership；`CN_FISCAL_PERIOD_ORDER` 拥有 CN/HK download canonical order，职责不重叠。

### MiMo C07：删除 `form_type` 参数的表面矛盾 — `已修复`

- 裁决：接受文字澄清。
- Plan changes：
  - 明确删除的是 `commit_cn_filing_source_document(...)` 与 `_build_base_meta(...)` 对各自 caller 暴露的 `form_type` 参数。
  - `commit_cn_filing_source_document(...)` 内唯一派生局部 `identity_period = candidate.period_projection.identity_period`。
  - `_build_base_meta(...)` 从 candidate 派生 meta 的 `form_type`/`fiscal_period`/`report_kind`。
  - `_build_upsert_request(..., form_type=identity_period)` 的内部参数保留；它机械构造 storage request，不构成 caller 可写的第二真源。
- Plan evidence：§5.3 identity/durable/public projection。

## 4. Re-review 已关闭项保持不变

两份 re-review 对上一轮 mode invariant、SEC coverage、public JSON、rebuild missing、category-first matrix、raw HKEX evidence、fresh-schema strict parse、README 与整文件 coverage 口径均判定已关闭或通过。本轮没有改写这些 contract，也没有重新打开 finding。

## 5. Validation 与 docs decision

本轮只执行只读/文档级验证：

- branch/worktree preflight；
- 两份新增 re-review 与追加裁决完整读取；
- `rg` 核对 `cn_report_selection.py` 两处 query consumer；
- `rg`/源码核对 `filing_semantics.py::FISCAL_PERIODS`；
- 源码核对三个 source-upsert helper 的当前 `form_type` 参数边界；
- 修订后 `rg` 检查 Slice 2 allowed files、共有文件表、常量 slice ownership 与 caller-facing wording；
- 对两份本轮 artifact 执行 whitespace check。

本 gate 不修改或验证产品实现，因此不运行 pytest、pyright、coverage 或 CLI；README 也不更新。

## 6. Residual risks / uncovered areas

| Residual risk / uncovered area | 分类 | Owner / destination |
|---|---|---|
| 第二轮 MiMo/DS 尚未独立 re-review | covered by later approved slice | 总控下一 gate |
| implementation 开始前代码基线可能新增 query consumer | covered by later approved slice | plan 要求 Slice 2 开始前重跑相同 `rg`，发现漂移即停止 |
| 实现与 tests/coverage/CLI 尚未执行 | covered by later approved slice | accepted plan 后的 implementation/review/evidence gates |

没有 unclassified residual risk，没有 blocking open question。本 artifact 完成后停在 `next=second MiMo+DS re-review`，等待总控；不得形成 accepted plan commit 或进入 implementation。
