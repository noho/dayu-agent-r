# UF-FIX08 existing-source-auto-repair：Slice 6 code review fix

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`fix`
- slice：`Slice 6：download unsafe 回归、文档与全量验证`
- 日期：2026-08-16
- baseline / current HEAD：`1e062f6cc13c22232449b4dc80ffcccb93b796d7`
- accepted plan：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
- implementation artifact：`docs/gateflow/uf-fix08-existing-source-auto-repair-slice6-implementation-20260816.md`
- review artifacts：`docs/reviews/code-review-20260816-183959.md`、`docs/reviews/code-review-20260816-184513.md`
- completion status：`CODE REVIEW FIXED / awaiting re-review`
- blocking questions：无
- 下一入口：Slice 6 re-review
- artifact path：`docs/gateflow/uf-fix08-existing-source-auto-repair-slice6-code-review-fix-20260816.md`

## Controller 裁决

| Review finding / focus | Controller decision | Fix status |
| --- | --- | --- |
| DS Finding 1：SEC Phase B UNSAFE 真分支缺直接节点 | `accepted`，本 gate blocker | `已修复` |
| DS Finding 2：CN top-level generic terminal projection | `rejected-with-reason` | `未修改 production/schema/test` |
| AgentMiMo Focus 5：SEC Phase B 已由 whole-tree 真实测试证明 | 证据表述不准确；frozen review artifact 不修改 | 新直接节点已消解证据缺口 |

## 第一性原理与 owner 判断

DS Finding 1 成立。原 SEC `UNSAFE` 测试在 Phase A exact-target gate 或 whole-tree preflight 已经失败，不能证明 begin batch 后
`classify_staged_source_integrity(...) -> UNSAFE` 的真分支、SEC `finally` rollback ownership，以及 reset/blob/commit 的零调用。production
分支的顺序是正确的，缺口属于 test evidence owner，因此不应修改 production 或 README。

DS Finding 2 不在本 gate 修复：

- CN top-level per-filing generic projection 是既有 bounded/path-free policy；lower single-filing owner 已经以 typed exception fail closed。
- 当前 closed download failure reason contract 没有可安全新增的 integrity code。把 upload failure code、preflight reason value 或临时字符串借作
  download terminal code会制造错误 owner。
- accepted Slice 6 production allowlist 不含 `cn_download_workflow.py`，Controller 也明确禁止扩大 schema/production。
- 补测试固定 `filing_execution_failed` 会把当前 generic fallback固化为稳定业务 contract，同样不正确。

因此 Finding 2 记录为 `rejected-with-reason`；一般 download typed terminal projection 作为
`assigned to later work unit`，owner 是后续独立的 download failure projection contract/schema work unit，而不是 UF-FIX08 Slice 6。

## Fix 内容

只修改 `tests/fins/test_sec_pipeline_download.py`：

- 新增 `_SecPhaseBMutationCalls` 严格类型计数器。
- 新增 `test_sec_unsafe_phase_b_rolls_back_without_reset_blob_or_commit`：
  - 用真实 filesystem seed 建立 `COMPLETE` SEC source；
  - 以 `overwrite=True` 让 Phase A `COMPLETE` 继续 provider list/prefetch，不被 fast skip；
  - 真实执行 batch begin，staged classifier 单点返回 invariant-valid
    `SourceIntegrityClassification(status=UNSAFE, revision=None, reasons=(META_UNTRUSTED,))`；
  - 直接消费真实 SEC single-filing workflow；
  - 断言 exact `SourceIntegrityPreflightError` 且 reason identity 为 `UNSAFE_PUBLICATION`；
  - 断言 `begin=1`、`staged_classify=1`、`rollback=1`、`reset=0`、`blob=0`、`commit=0`；
  - 断言 provider prefetch 确实发生，证明不是 Phase A/whole-tree 提前失败；
  - 断言 published meta、payload、manifest bytes 完全不变，public reclassification 仍为 `COMPLETE`。

没有修改 production、README、CN workflow/test、storage owner、provider/retry/registry/schema 或 frozen review artifact。

## Validation

运行环境：仓库 `.venv`，Python 3.11；coverage 全程单进程执行，无其它 reviewer/agent 并发写 `.coverage`。

新增 node：

```text
python -m pytest \
  tests/fins/test_sec_pipeline_download.py::test_sec_unsafe_phase_b_rolls_back_without_reset_blob_or_commit -q
1 passed, 3 warnings in 0.86s
```

两份 download tests：

```text
python -m pytest tests/fins/test_sec_pipeline_download.py tests/fins/test_cn_download_workflow.py -q
201 passed, 3 warnings in 2.93s
```

accepted focused matrix：

```text
1230 passed, 3 warnings in 45.40s
```

完整 Fins suite：

```text
python -m pytest tests/fins -q
1851 passed, 1 skipped, 3 warnings in 50.10s
```

固定全仓 pyright：

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

单进程 focused branch coverage：

```text
coverage run --branch -m pytest <accepted focused matrix>
1230 passed, 3 warnings in 51.71s

dayu/fins/pipelines/sec_download_filing_workflow.py  83%
dayu/fins/pipelines/cn_download_filing_workflow.py   83%
```

两份修改 production 的 branch-aware coverage 均保持 `>=80%`；SEC Phase B UNSAFE raise 的直接 node 已进入采集。

三个 warning 均来自已安装 `edgar` package 的既有 deprecated imports；唯一 skip 是仓库既有环境条件 skip。

## Scope、docs 与 frozen guards

- 本 fix delta 只修改 `tests/fins/test_sec_pipeline_download.py`、更新 Slice 6 implementation artifact并新增本 fix artifact。
- production 与三份 README 没有本 gate 新改动；`tests/README.md` 原有 SEC/CN Phase A/B matrix 表述现在已有直接证据，无需修改。
- 两份 review artifact 保持 frozen，不修改 AgentMiMo Focus 5 的历史表述。
- `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/host/design.md`、`docs/engine/design.md` diff 为空。
- `git diff --check`：通过。
- 未执行 `dayu-cli`、UF-PF08、UF-PF12 或真实 provider/converter evidence。
- HEAD 保持 `1e062f6cc13c22232449b4dc80ffcccb93b796d7`；未 commit、未 staged、未 push、未 clear、未创建 PR。

## Residual risks

| Residual | Classification / owner |
| --- | --- |
| 一般 download typed terminal projection contract/schema | `assigned to later work unit`；后续独立 download failure projection owner，DS Finding 2 不在当前 allowlist 固化 generic fallback |
| 一般 preparation 并发的 success/skip 收敛 | `assigned to later work unit`：`UF-FIX10` |
| fresh company meta warning | `assigned to later work unit`：`UF-FIX11` |
| material existing-source repair | `assigned to later work unit`：后续独立 material repair work unit |
| 旧 schema compatibility/migration | `assigned to later work unit`：后续显式 migration work unit（若授权） |
| 真实 CLI/provider/converter evidence 与 registry/oracle adjudication | `assigned to later work unit`：UF-PF08/UF-PF12 evidence owner |

DS Finding 1 已在当前 slice fix；没有未分类 residual risk，没有 blocking question。

## 下一入口

Code review fix 已完成，按用户要求停在 Slice 6 re-review gate。下一步应独立 re-review 当前未提交 diff、implementation artifact 与本 fix
artifact；本轮不 commit、不 clear、不进入 aggregate deepreview 或 closeout。
