# UF-FIX10 S1 second blocker plan acceptance

## 0. Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- gate：`second plan re-review -> amendment acceptance`
- 日期：2026-08-17
- reviewed amendment：`docs/gateflow/uf-fix10-s1-second-blocker-plan-amendment-20260817.md`
- reviewed plan：`docs/gateflow/uf-fix10-same-request-concurrency-plan-20260816.md`
- review artifacts：
  - `docs/reviews/plan-review-20260817-010842-mimo.md`
  - `docs/reviews/plan-review-20260817-010619-ds.md`
- completion status：`SECOND AMENDMENT ACCEPTED / S1 RESUME AUTHORIZED`
- artifact path：`docs/gateflow/uf-fix10-s1-second-blocker-plan-acceptance-20260817.md`
- 下一入口：`S1 implementation resume`

## 1. Review decision

两路定点 plan re-review 结论均为 `pass`，共同确认：`tests/fins/test_fins_ingestion_tools.py:2474:40` 的 tools forbidden fake 是当前唯一 pyright-checkable blocker；正确且最小的 owner 修复是 required batch method、独立 `batch_calls`、record-then-`AssertionError` 与既有 filing static-admission cases 双空记录断言。production protocol、S1 零 observable 行为、S1/S2 activation boundary 与 README decision 均不变；禁止 cast、default、optional method、`hasattr/getattr`、wrapper 或 fallback。

Controller pin 定 implementation 范围：只在现有 filing static-admission cases 已经断言 `state_repository.calls == []` 的位置增加 `batch_calls == []`；使用同一 builder 但丢弃仓储且无既有 calls 断言的 material ticker-identity case不动。tools 文件新增 `BatchToken` import 属 required method 的机械必然。

## 2. Residual risk adjudication

MiMo review 识别的 `tests/fins/test_fins_service_runtime.py::_UnsafeFilingUploadStateRepository` 通过动态 class monkeypatch 注入，静态 protocol census 不可见。Controller 裁决其为非阻塞 residual，且不纳入 S1 或 S2：本 work unit 的 batch-read route 不经过该 service prevalidation fake，因此没有当前 pyright 或 runtime failure mode。只有未来 work unit 使该路径消费 batch read或协议再次扩展 required method 时，才由该 fixture 语义 owner 同步 conform。

DS 提出的 §10.1 #13 措辞张力已由上述 Controller pin 定消除。无 blocking open question，无未分类 residual risk。

## 3. Scope、validation 与 decision

- accepted implementation scope：只恢复 second amended §10.1 对 tools forbidden fake 的同型 protocol conformance与精确零行为断言。
- 当前 production/tests partial diff仍不可提交；本 acceptance gate 不修改 production/tests/README/oracle/scenario/registry/evidence，不运行 pytest、pyright、coverage，不 commit。
- 本 gate 只执行 docs diff、结构与 whitespace 检查。
- README decision：不更新；acceptance 仅迁移 Gateflow 状态，没有生产或用户可见行为变化。
- gate decision：`SECOND AMENDMENT ACCEPTED / S1 RESUME AUTHORIZED`。
- 下一入口：`S1 implementation resume`；不得提前接通 S2 lifecycle。
