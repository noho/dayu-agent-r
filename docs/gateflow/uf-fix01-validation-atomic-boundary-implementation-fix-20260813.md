# UF-FIX01 validation-atomic-boundary — Implementation Fix Artifact

## 1. Gate context

- baseline HEAD：`54c867f8224290659e01ac454caf463349b20c67`
- implementation commit：`3caca6fa0091a738c5c78cc5165a49fed82c6458`
- adjudication：`docs/gateflow/uf-fix01-validation-atomic-boundary-implementation-review-adjudication-20260813.md`
- review inputs：`docs/reviews/code-review-20260813-114536.md`、`docs/reviews/code-review-20260813-115401.md`
- fix scope：只处理裁决 A1–A5/C1–C3；不运行 UF-PF01，不修改 UF-FIX09 converter、date/year/format 集合、其它 WU、frozen evidence/registry
- branch policy：仅创建本地 fix commit；不创建 PR、不 push、不更新 main

## 2. Frozen owner chain

最终调用链固定为：

```text
CLI prevalidation
  -> Service/runtime typed validated request identity
  -> SEC/CN/HK facade
  -> workflow fresh snapshot + same validator + identity fail-closed
  -> authoritative prepare/stage/commit
```

- Service/runtime/facade 不把 `ValidatedFinsUploadFilingRequest` 还原为散参。
- workflow 通过注入的同一个 `FilingUploadStateRepositoryProtocol` 读取 fresh snapshot，对 preflight raw request 调用同一 validator，并核对 canonical ticker、document ID、internal document ID。
- 只有 authoritative `resolved_action`、`published_state.source_meta`、`company_meta_decision` 驱动后续状态机。
- `DoclingUploadService.prepare_upload` 接受 caller-owned `previous_meta` 且不自行读取 state；material 调用方继续从其既有 owner 取得 meta。
- filing 以 `stage_upload_company_meta_decision` stage company；company/source 共用同一 caller-owned `BatchToken`，无补偿删除或二次 batch。

## 3. Adjudicated fixes

| Finding | Status | Owner-level fix |
| --- | --- | --- |
| A1 | 已修复 | SEC/CN/HK facade 与 workflow 接收 typed validated request；workflow fresh recheck、identity fail-closed，并只消费 authoritative action/source/company decision。 |
| A2 | 已修复 | stale preflight 后的旧 action/company decision 被丢弃；普通冲突仍由同一 validator 以 closed actionable usage reason 拒绝，不以异常字符串或 generic/storage 文案重分类。 |
| A3 | 已修复 | SEC/CN 真实 FS owner tests 固定 BatchToken identity、begin/commit/rollback 次数、fresh/existing tree 与逐文件 SHA-256、company/source stage rollback、并发旧派生值丢弃；SEC 额外固定 rollback failure 的 primary/recovery evidence。 |
| A4 | 已修复 | prevalidation I/O/lock 与 descriptor corruption 进入专用 typed operational exception；CLI 固定 path-free bounded reason、exit `1`，operator log 保留 chained internal cause。 |
| A5 | 已修复 | `_upload_filing_stream` docstring 改为准确描述只透传 typed request 及 Service/runtime 异常。 |
| C1 | 已修复 | frozen UF usage cases 全部参数化穿过真实 CLI owner boundary，逐 case 断言 exact exit `2`、stdout empty、stderr exact、factory/service zero、workspace tree zero。 |
| C2 | 已修复 | filing workflow 显式按 cancelled → Docling → OSError/storage → generic 顺序处理；public result 只投影 closed typed reason，operator log 保留原始 cause，并以可观察 marker tests 固定顺序。 |
| C3 | 已修复 | material 继续使用既有 previous-meta owner、事务与 `str(exc)` 用户语义；SEC/CN material regression tests 固定该 non-goal。 |

为保持 rollback primary evidence，batch 生命周期 owner 新增 `rollback_prepared_upload_batch`：rollback 成功时继续传播原始异常；rollback 自身失败时以原始异常为 primary、rollback 为 cause 并附 recovery note。该 helper 不执行 delete、不创建第二 batch。

## 4. Tests and verification

实现遵循 tests-first：先补 owner failure tests，确认旧链路不能满足 authoritative handoff、atomicity、CLI matrix、operational failure 与 typed classification，再修改 production owner。

### Final affected suite

```text
591 passed, 1 skipped, 3 warnings in 32.56s
```

覆盖 CLI/import boundary、Service direct、ingestion runtime、storage atomicity/provider、Docling upload service 与 integration、SEC filing/material、CN/HK pipeline。3 条 warning 均来自第三方 `edgar` deprecation；skip 为既有测试条件。

coverage supplement 运行 SEC material/download 与 CN/HK download owner suites：`229 passed, 3 warnings`。

### Per-modified-production-file coverage

| Production file | Coverage |
| --- | ---: |
| `dayu/cli/commands/fins.py` | 85% |
| `dayu/fins/pipelines/cn_pipeline.py` | 93% |
| `dayu/fins/pipelines/docling_upload_service.py` | 85% |
| `dayu/fins/pipelines/sec_pipeline.py` | 86% |
| `dayu/fins/pipelines/sec_upload_workflow.py` | 93% |
| `dayu/fins/service_runtime.py` | 91% |
| `dayu/fins/upload_failure.py` | 96% |

每个文件均以独立 `coverage report --include=<file> --fail-under=80` 检查并 exit `0`。

### Type/static gates

- `python -m pyright dayu/ tests/ utils/`：`0 errors, 0 warnings, 0 informations`。
- Ruff、formatter check、`git diff --check`：通过。
- production diff audit：filing 路径不再调用旧 company upsert；`prepare_upload` 不再读取 previous meta；无新增 `hasattr/getattr`、字符串分类、补偿删除、compatibility shim、lazy import 或 `TYPE_CHECKING` import workaround。
- scope audit：`docling_process_converter.py`、date/year/format 集合、其它 WU、frozen evidence/registry 均无 diff。

## 5. Documentation decision

- 更新 `dayu/fins/README.md`：记录 typed handoff、workflow authoritative recheck、唯一 decision/source owner 与 operational failure projection。
- 更新 `tests/README.md`：记录 CLI frozen matrix、BatchToken/SHA/rollback/concurrency、typed catch 与 material non-goal owner coverage。
- 更新原 implementation artifact 并新增本 artifact。
- 根 README 的现有 upload_filing 段落已准确承诺 startup prevalidation、usage exit `2`、operational exit `1` 与 atomic publication，本 fix 未改变该公开契约，因此不机械重复修改。
- 分层、Host/Engine、config/schema/prompt 均未变化，不触发其它 README。

## 6. Residual risk and next gate

- UF-PF01 focused-real evidence 按 Controller 明确指示未运行；它属于双路 re-review PASS 后的下一 approved gate，不是本 fix 的未分类缺口。
- 未运行全仓 pytest；裁决明确不要求，本 fix 已运行计划完整受影响 suite、coverage supplement 与完整 pyright。
- 无已知未分类 correctness/owner/public protocol/architecture risk。
- 下一 gate：MiMo 与 DS 对本地 fix commit 做双路 implementation fix re-review；本 gate 不创建 PR 或 push。

## 7. R1/R2 implementation delta fix

### Gate 与 scope

- target HEAD：`0391b589de075f47a2c13f8e173e48e3ae0f1c5e`
- adjudication：`docs/gateflow/uf-fix01-validation-atomic-boundary-implementation-fix-rereview-adjudication-20260813.md`
- gate：implementation fix delta
- completion status：R1/R2 implementation delta **PASS**，等待两路独立 re-review
- artifact path：`docs/gateflow/uf-fix01-validation-atomic-boundary-implementation-fix-20260813.md`
- scope：严格只修 R1/R2；未运行 UF-PF01，未修改 owner/non-goals、date/year、suffix、material、converter、frozen registry/evidence

### Owner decision 与 changed files

- `dayu/fins/service_runtime.py`：`prevalidate_fins_upload_filing_request_for_workspace` 继续作为 concrete workspace prevalidation owner；将 `FsFilingUploadStateRepository` 构造与 state read 放入同一个既有 typed `try`，构造/resolve/read 的 `OSError`、lock failure 与 corruption 分别复用既有 I/O/corruption mapping。未新增 CLI fallback、异常字符串分类或兼容分支。
- `dayu/cli/commands/fins.py`：只修正 `_prevalidate_upload_filing_request` docstring，异常契约改为 `FinsUploadUsageError` / `FinsUploadPrevalidationError`，不改变 CLI 运行语义。
- `tests/fins/test_fins_service_runtime.py`：新增 service-runtime owner test，注入 repository 构造期 workspace `resolve()` 的 `PermissionError`，断言 exact typed reason、完整 path-free cause chain 与 fresh workspace 零 mutation。
- `tests/cli/test_fins_commands.py`：新增真实 `cli_main` boundary test，断言构造期 resolve failure 为 exit `1`、stdout empty、exact path-free stderr、operator log 保留底层 `PermissionError` cause、fresh workspace 零 mutation。

### Validation

- tests-first 红灯：修复前两个新增定点测试均失败；owner 直接收到 `PermissionError`，CLI generic branch 输出 storage 内部诊断，证实 R1 与代码根因同源。
- 定点转绿：`2 passed, 3 warnings`。
- 完整直接影响 suite：`pytest -q tests/fins/test_fins_service_runtime.py tests/cli/test_fins_commands.py` → `79 passed, 3 warnings in 1.54s`。warning 均为既有第三方 `edgar` deprecation。
- 完整类型检查：`python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`。
- 静态验证：受影响文件 Ruff check、Ruff format check、`git diff --check` 均通过。
- diff/static audit：production delta 只有一个 owner-boundary try 移动与一个 docstring contract 修正；无新增 `hasattr/getattr`、`str(exc)` 分类、generic CLI fallback、compatibility shim、lazy import、字符串错误分类或 non-goal 文件 diff。

### README decision 与 residual risk

- `dayu/fins/README.md` 已准确承诺 prevalidation storage I/O 通过 closed path-free typed reason 投影且 operator log 保留 cause；构造阶段纳入同一边界未改变稳定架构或 public contract，因此不重复修改。
- `tests/README.md` 已记录 prevalidation storage I/O 的 typed exit `1`、operator cause 与 fresh workspace owner coverage；新增测试未改变测试分层或维护命令，因此不重复修改。
- 根 README 的 exit `1` / 脱敏 operational failure 用户契约未变化；分层、Host/Engine、schema、config、prompt 均未变化，不触发其它 README。
- 未运行全仓 pytest；本 delta 只改变已由完整 CLI 文件与 owner 定点测试覆盖的 prevalidation try boundary。
- 无已知未分类 residual risk。下一 gate 仍是 MiMo、DS 对本地 delta commit 做第二轮独立 `$deepreview`；两路 PASS 后才可进入 UF-PF01，本轮不得运行 UF-PF01、push 或创建 PR。
