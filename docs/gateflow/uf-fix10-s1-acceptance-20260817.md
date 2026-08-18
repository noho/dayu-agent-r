# UF-FIX10 S1 acceptance

## Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- slice：`S1 — behavior-preserving owner contracts`
- gate：`accepted slice`
- 日期：2026-08-17
- completion status：`S1 ACCEPTED / READY TO COMMIT`
- artifact path：`docs/gateflow/uf-fix10-s1-acceptance-20260817.md`
- accepted commit：待创建；本 acceptance gate 只记录裁决，下一 gate 按用户要求在当前分支提交
- blocking open questions：无
- 下一入口：`S1 accepted slice commit`，完成后进入 `S2 implementation`

## Scope 与结论

S1 已通过两路独立 code-review re-review：

- `docs/reviews/code-review-20260817-015152.md`：`Pass`，确认 accepted F2–F5 与 C1
  均在 owner boundary 修复，F1/Q1/Q2 裁决符合 accepted plan，S1 无 S2 接线或行为漂移。
- `docs/reviews/code-review-20260817-020029.md`：`Pass`，逐项挑战真实跨 owner identity、
  §7.4 conflict grid、UNSAFE/stable invariant、strict text contract、空 staging read 与 F1
  defer 对 S2 的影响；无 blocker、无 open question。

本 acceptance gate 只记录 S1 review loop 的 durable decision，并同步 plan/implementation
gate 状态；不修改生产代码、测试或 README，不创建 commit，也不进入 S2 implementation。

## Accepted findings closure

| Finding | 最终状态 | Closure evidence |
| --- | --- | --- |
| F2 prepared/durable identity 跨 owner 等价缺口 | `已修复` | 真实多文件 prepare → publish → storage read，exact identity 与逐资产 metadata/role 全等 |
| F3 §7.4 conflict grid、UNSAFE 与 stable invariant 缺口 | `已修复` | 五格表驱动 typed conflict、initial/fresh UNSAFE raise、stable REPAIR_REQUIRED action raise |
| F4 required text/content_type 运行时类型缺口 | `已修复` | identity/asset contract 在 owner `__post_init__` 显式严格校验字符串，直接非法构造测试通过 |
| F5(a) 空 staging 合法 document batch read | `已修复` | 返回完整 MISSING/空 meta/空 identity，读取前后 workspace tree 精确不变 |
| F5(b) published 空 document_id fail-fast | `已修复` | accepted intended contract 已由 ValueError 与零 mutation 测试固定 |
| C1 stable REPAIR_REQUIRED fresh action 检查 | `已修复` | owner 分支检查 fresh resolved action，stable invariant 测试固定 fail-closed 行为 |

F1 按 `rejected-with-reason` 保持 accepted plan §6.3 的 rebase version contract；Q1/Q2
同样按 `rejected-with-reason` 保持既有 preparation process 与 company disposition public
contract。不存在 accepted finding 未闭合、证据失效或部分修复。

## Validation acceptance

- amended focused pytest：`944 passed, 3 warnings`。
- 完整 `pytest tests/fins -q`：`1884 passed, 1 skipped, 3 warnings`。
- full pyright（`dayu/ tests/ utils/`）：`0 errors, 0 warnings`。
- owner-inclusive coverage.py 单次采集：`338 passed`；arbitration `87%`、Docling `88%`、
  storage batch-state core `95%`、typed failure `84%`，总计 `88%`，满足
  `--fail-under=80`。冻结 pytest-cov 多 source 入口的本机 NumPy duplicate-load collection
  error 已在 implementation artifact 中记录，不作为代码 failure。
- `git diff --check`：通过。
- 两路 re-review 中第二路独立复跑 focused、完整 Fins、全仓 pyright 与 diff-check，结果一致；
  第一、二路均结论 pass。

未运行 UF-PF10/UF-PF12；未修改 SEC/CN/HK workflow、workflow tests、oracle、scenario、
registry 或 frozen evidence；未接通 S2 lifecycle。

## README decision

不更新 README。S1 是 behavior-preserving owner contract/infrastructure slice，现有 filing
early skip、SEC/CN/HK workflow、CLI、Service API、安装/排障与用户工作流均未变化；Controller
也明确要求本 acceptance gate 不修改 README。S2 真正接通 shared publication route 后，再按
accepted plan §12 对 `dayu/fins/README.md` 与 `tests/README.md` 执行职责内更新。

## Residual risks

| Residual | 分类 / owner | 对 S1 acceptance 的影响 |
| --- | --- | --- |
| 多文件 role-ambiguous 输入下 sequential prepare 与 concurrency rebase 的 document version 可能不同 | `assigned to later work unit`：未来独立 document-version policy work unit | accepted plan 已冻结 rebase 同 fingerprint 保留 fresh version、不同 fingerprint 递增；不影响 S2 skip/conflict/publish correctness，非 blocker |
| `test_fins_service_runtime.py` 动态 monkeypatch fake 只实现 published read | `assigned to future triggering work unit`：该 fixture 语义 owner | 本 work unit 无 batch-read 可达路径经过该 fake；未来路径或 required protocol 变化时再同步，非 blocker |

无未分类 residual risk。

## Acceptance decision

S1 review/fix/re-review loop 已通过，全部 accepted findings 已修复并由两路 re-review 验证，
验证与 docs decision 完整，故裁决：`S1 ACCEPTED / READY TO COMMIT`。

本 acceptance gate 不创建 commit；下一入口严格为按用户要求在当前分支执行
`S1 accepted slice commit`。该 commit 完成后才能进入 `S2 implementation`，不得跳过或并行接线。
