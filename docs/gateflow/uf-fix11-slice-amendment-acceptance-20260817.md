# UF-FIX11 slice-boundary amendment acceptance

- Work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- Gate：`plan amendment acceptance`
- 裁决：`accepted`
- 下一入口：原子 `S1+S2 implementation`

## 接受证据

- 原始 blocker：`docs/gateflow/uf-fix11-s1-slice-boundary-blocker-20260817.md`
- 修订说明：`docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md`
- Review fix：`docs/gateflow/uf-fix11-slice-amendment-review-fix-20260817.md`
- MiMo final re-review：`docs/reviews/uf-fix11-slice-amendment-rereview-mimo-20260817.md`，结论 `pass`
- DS final re-review：`docs/reviews/uf-fix11-slice-amendment-rereview-ds-20260817.md`，结论 `pass`

## Controller 裁决

1. 接受将原 Slice 1 与 Slice 2 合并为不可拆分的原子 S1+S2；该边界是关闭 producer intent、publication-lock 最终裁决、metadata-only skip commit、typed warning、terminal producer 与 strict parser 因果链的最小绿色边界。
2. DS Finding-001 已关闭：并发 blocker 测试的新终态冻结为 `skipped + metadata-only commit`，并精确约束 begin/commit/rollback/stage token、规范 warning、final company metadata bytes、source tree 以及 stale preflight decision 丢弃语义。
3. DS Finding-002 已关闭：§12.2 combined regression 是 S1+S2 进入 review 与 accepted commit 前的硬门，任何失败均禁止接受或递延给 S3。
4. DS Finding-003 已关闭：`ingestion_runtime.py` 与 `service_runtime.py` 已按符号划分 S1+S2 parser contract 和 S3 summary/durable projection，禁止双向漂移。
5. DS OQ-1 已关闭：本 plan-gate commit 仅包含 amendment 文档；当前 production/test partial diff 不得 stage。后续 S1+S2 code commit 明确排除本 gate 文档。
6. DS re-review 指出的唯一非实质陈旧表述已在 acceptance 前同步为 `plan amendment re-review`；该编辑不改变已复审的业务、切片或验证契约。

## Commit 文件集

本 gate 只允许逐文件 stage：

- `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- `docs/gateflow/uf-fix11-s1-slice-boundary-blocker-20260817.md`
- `docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md`
- `docs/gateflow/uf-fix11-slice-amendment-review-fix-20260817.md`
- `docs/gateflow/uf-fix11-slice-amendment-acceptance-20260817.md`
- `docs/reviews/uf-fix11-slice-amendment-review-ds-20260817.md`
- `docs/reviews/uf-fix11-slice-amendment-review-mimo-20260817.md`
- `docs/reviews/uf-fix11-slice-amendment-rereview-ds-20260817.md`
- `docs/reviews/uf-fix11-slice-amendment-rereview-mimo-20260817.md`

提交前必须以 cached diff 证明不存在 production/test path。当前 production/test partial implementation 保留在工作区，仍未被接受。

## 最终状态

Plan amendment gate 已接受。可以恢复原子 S1+S2 implementation；不得拆分提交，不得跳过完整 focused suite、combined regression、逐文件 coverage、全仓 pyright、static boundary checks 与 implementation review/fix/re-review。
