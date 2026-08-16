# UF-FIX08 existing-source-auto-repair：Slice 5 implementation

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`implementation`
- slice：`Slice 5：SEC/CN/HK workflow 与 downstream`
- 日期：2026-08-16
- baseline / current HEAD：`4812878b5a3a4884b8b8522e7113d196c4e479d9`
- accepted plan：`docs/gateflow/uf-fix08-existing-source-auto-repair-plan-20260816.md`
- 前置 artifacts：Slice 1–4 implementation、code review、adjudication 与 code-review-fix artifacts
- code review：`docs/reviews/code-review-20260816-174830.md`、`docs/reviews/code-review-20260816-175716.md`
- completion status：`CODE REVIEW FIXED / awaiting re-review`
- blocking questions：无
- 下一入口：Slice 5 re-review

## 动机与语义 owner 裁决

动机成立，且 accepted plan 与当前代码证据一致。Slice 4 已让 SEC/CN/HK workflow 把 fresh validator 产生的
`repair_disposition` 原样传入 shared service，identity guard 也已只比较 canonical ticker、document ID 与 internal document ID；但 fresh
`read_filing_upload_state()` 与 validator 位于 workflow 执行期 failure boundary 之外。因此 fresh `FinsUploadPrevalidationError`、仍可能出现的
path-free `ValueError/FileNotFoundError` 会从 async stream 旁路 typed terminal，无法由 durable runtime 持久化同一个 closed failure。

本 slice 保持以下唯一 owner：

- filesystem storage inspector 继续拥有 source integrity status/revision/reasons；workflow 不读 raw meta、不扫目录、不检查路径存在性。
- validator 继续是 repair eligibility 与 authoritative disposition 唯一 producer；workflow 丢弃 preflight disposition，只消费 fresh result。
- `DoclingUploadService` 与 storage staged repair 继续拥有完整 preparation、Phase B recheck、reset 与 publication。
- `upload_failure.py` 继续拥有 public failure kind/code/message/retry hint；workflow 只精确复用既有 factory 或 prevalidation exception 的 typed
  reason，不读取异常字符串重分类。
- source snapshot 的 exact primary 与 runtime preprocess 是 downstream 唯一消费链；processed meta 不新增 source revision 字段，因为现有
  contract 明确不把 opaque revision token投影进 processed publication。

## 实际修改

### Fresh authoritative boundary

- `dayu/fins/pipelines/_filing_upload_fresh_validation.py` 是三市场唯一 fresh-validation owner；SEC 与 CN/HK workflow 只机械调用其
  朴素接口，不再各自复制异常映射规则。
- shared resolver 把 fresh state read 与同一次 authoritative validator 调用放在同一显式 `try` 中，并返回
  `ValidatedFinsUploadFilingRequest | FinsUploadFailureReason`：
  - `FinsUploadPrevalidationError` 原样返回 `exc.failure`；
  - `FileNotFoundError/OSError/RuntimeFileLockError` 使用既有 prevalidation IO failure；
  - path-free structural `ValueError` 使用既有 prevalidation corruption failure；
  - `FinsUploadUsageError` 保持用户输入异常语义并原样抛出。
- workflow 对 typed reason 产生唯一 `UPLOAD_FAILED` 并立即结束；未发 `UPLOAD_STARTED`、未调用 converter、未创建 batch。
- shared resolver 形式保留 Slice 1–4 已冻结的 filing workflow 顶层执行期 handler 顺序：仍只有
  `FinsUploadFailureError -> OSError -> Exception` 一个顶层 execution `try`，没有把 fresh failure 混入 generic runtime。
- fresh authoritative request 继续把 `repair_disposition` 原样传 shared service。identity guard 未扩大，仍只比较 ticker、document ID、internal
  document ID，不比较 status、revision、reasons、action 或 company decision。

### 真实 filesystem workflow 覆盖

- SEC 真实 publication 覆盖 original missing、same-size digest drift、primary Docling missing、meta digest mismatch、canonical manifest missing
  五类 repairable corruption；每例均先由 production validator 产生 `REPAIR_REQUIRED`，再经 workflow fresh read/validator 进入 shared repair。
- SEC success 断言 public `COMPLETE`、新 revision、两个 requested originals 等于两个 stored originals、唯一 primary Docling、manifest、physical
  size/digest、snapshot exact primary，以及 company/source 使用同一 batch token原子 commit。
- CN 与 HK 各有独立真实 filesystem repair success，断言 market projection、新 revision、完整 originals/primary/manifest/digest、snapshot 与同批
  company/source publication；没有以“共用 CN facade”替代 HK wiring assertion。
- CN/HK 各有真实 fresh `UNSAFE` publication，validator 产生唯一 `source_integrity_unsafe` failed event，converter/batch/company/source mutation
  均为零，failure 不含 undeclared filename或 `unexpected_runtime`。
- CN 另在 repair conversion 后改变真实 published target，Phase B 精确投影 `source_revision_stale`，唯一 batch rollback、commit 为零，外部变更后的
  published tree保持不变。
- SEC fresh state read 的 `FileNotFoundError`、`RuntimeFileLockError` 与 structural `ValueError` 分别验证固定 path-free message、唯一 typed
  event、零 converter 与零 batch/company/source mutation。

### Snapshot、process_filing 与 durable failure

- downstream 测试使用逐次产生不同 bytes 的 converter，先证明 repair 前 light snapshot 固定拒绝非完整 source，再证明 repair 后 full snapshot
  只返回新 revision 的 `repair-primary-v2` exact primary。
- 测试从真实 `FinsDirectCommandService.process_filing()` direct stream 进入 runtime，通过 processor registry source spy 证明 processor 只收到该新
  primary bytes；不扫描 original 或 companion。process 成功后 source 仍为同一个新 `COMPLETE` revision。
- durable runtime 测试从真实 SEC upload 建立 publication，fresh validation 遇到 undeclared file 后，job `failure_summary` 与
  `result_summary.failure` 均逐字段等于 `source_integrity_unsafe` owner JSON，未写 generic exception message、路径或文件名。

## Changed files

Production：

- `dayu/fins/pipelines/_filing_upload_fresh_validation.py`
- `dayu/fins/pipelines/sec_upload_workflow.py`
- `dayu/fins/pipelines/cn_pipeline.py`

Tests：

- `tests/fins/test_sec_pipeline_upload_filing_stream.py`
- `tests/fins/test_cn_pipeline.py`
- `tests/fins/test_processor_read_consistency.py`
- `tests/fins/test_fins_ingestion_runtime.py`（仅新增 typed failed job projection）

Artifact：

- `docs/gateflow/uf-fix08-existing-source-auto-repair-slice5-implementation-20260816.md`

没有修改 download、README、evidence、oracle、scenario、UF-FIX10/11 或任何 Slice 1–4 owner 文件。

## Validation

运行环境：仓库 `.venv`，Python 3.11。

四个直接受影响测试文件：

```text
python -m pytest \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_processor_read_consistency.py \
  tests/fins/test_fins_ingestion_runtime.py -q

430 passed, 3 warnings in 6.74s
```

`process_filing` direct entry最终强化后单文件复验：

```text
python -m pytest tests/fins/test_processor_read_consistency.py -q
55 passed, 3 warnings in 2.00s
```

accepted plan §10 focused matrix：

```text
1221 passed, 3 warnings in 45.53s
```

完整 Fins suite：

```text
python -m pytest tests/fins -q
1842 passed, 1 skipped, 3 warnings in 58.70s
```

Service/CLI regression：

```text
python -m pytest tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q
188 passed, 3 warnings in 10.58s
```

完整 Fins suite branch coverage：

```text
coverage run --branch --source=dayu/fins -m pytest tests/fins -q
1842 passed, 1 skipped, 3 warnings in 72.34s

dayu/fins/pipelines/_filing_upload_fresh_validation.py  100%
dayu/fins/pipelines/sec_upload_workflow.py               92%
dayu/fins/pipelines/cn_pipeline.py                        92%
```

三个修改生产文件逐文件 branch coverage 均达到 `>=80%`。唯一 skip 是仓库既有环境条件 skip；三条 warning 均来自已安装 `edgar` 包的
deprecated imports。

全仓类型检查（最终 downstream test强化后重跑）：

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

## Scope、frozen guards 与 README decision

- `git diff --check`：通过。
- HEAD 精确保持 `4812878b5a3a4884b8b8522e7113d196c4e479d9`；未 commit、未 staged、未 push、未创建 PR。
- production/tests diff 仅落在用户列出的六份 allowed files、Controller 授权的一个 shared-owner production module；另新增本
  implementation artifact与 code-review-fix artifact。
- `README.md`、`dayu/fins/README.md`、`tests/README.md`、`dayu/README.md` 无 diff。
- `docs/cli_ci_oracles.json`、`docs/cli_ci_scenarios.json`、`docs/host/design.md`、`docs/engine/design.md` 无 diff。
- 未运行 `dayu-cli`、UF-PF08、UF-PF12 或真实 provider/converter evidence。
- 新增 production 未使用 `Any`、`object`、反射、compatibility shim、raw meta fallback、目录扫描或异常字符串判定。

README 按用户明确限制与 accepted Slice 6 owner保持不改；本 slice不提前写最终用户 workflow 文档。

## Residual risks 与后续 owner

| residual / 未覆盖项 | 分类与 owner |
| --- | --- |
| SEC/CN download unsafe 与 whole-manifest-missing 回归 | accepted Slice 6；本 slice禁止修改 download |
| 最终用户与 developer README 汇总 | accepted Slice 6 |
| 一般并发收敛/重试 | `UF-FIX10`；本 slice只验证 repair Phase B stale并零重试 |
| fresh company meta warning | `UF-FIX11` |
| material existing-source repair | 后续独立 work unit；filing workflow未扩大 authorization |
| 旧 schema compatibility/migration | 后续显式 migration work unit（若授权） |
| 真实 evidence、oracle、scenario | UF-PF08/UF-PF12 evidence work unit |

没有未分类 blocking risk。本 slice不改变 download或对外文档，因此不声称 UF-FIX08 已整体 closeout。

## Code review fix：reviews 174830 / 175716

Controller 接受并设为 blocker 的 findings 已完成最小修复：

| Finding | 最终状态 | 修复证据 |
| --- | --- | --- |
| fresh state owner 漏捕 `RuntimeFileLockError` | `已修复` | shared resolver 精确使用 `except (OSError, RuntimeFileLockError)` 并复用既有 prevalidation IO factory；真实 workflow test断言唯一 `storage_io` event、零 `UPLOAD_STARTED`/converter/batch/company/source mutation且无异常文本 |
| SEC/CN fresh resolver 双 owner | `已修复` | 新增 `_filing_upload_fresh_validation.py` 作为唯一 owner；两份 workflow 删除本地 helper与相关 validator/failure imports，只 import同一个 resolver并机械投影 typed reason；测试 monkeypatch 边界同步迁移到 shared owner，无 compatibility re-export |

Controller 明确 rejected findings 的裁决如下：

- fresh `FinsUploadUsageError` 继续原样抛出。durable generic exception 是既有通用 runtime 边界，当前 `FinsUploadFailureCode` 没有等价 usage
  code；本 work unit 不扩大 durable schema，也不把 usage 错误伪装成 storage/runtime failure。catch 顺序固定为 usage 在 structural
  `ValueError` 前。
- CN/HK 各一个真实 corruption success 已满足 accepted plan §11.4；完整 corruption grid由 shared service/storage与 SEC market tests覆盖，
  不机械复制 SEC 五类矩阵。
- SEC/CN 测试 JSON helper 属各自 market fixture setup；抽取会新增跨 scope test-support owner，本 slice不做无业务收益的测试基础设施重构。
- shared resolver只捕获 closed prevalidation、usage、I/O/lock与 structural `ValueError`；其它 `RuntimeError` 和 workflow identity invariant继续
  fail-loud，不被误投影为 storage corruption或 generic typed upload failure。

Fix artifact：`docs/gateflow/uf-fix08-existing-source-auto-repair-slice5-code-review-fix-20260816.md`。

## 下一入口

Slice 5 code-review fix 已完成并停在 re-review gate。下一步应对当前未提交 diff执行独立 re-review；本 artifact 不表示 re-review
acceptance，也不授权 commit、进入 Slice 6、创建 PR 或 final closeout。
