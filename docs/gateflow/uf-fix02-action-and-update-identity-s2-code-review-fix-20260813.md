# UF-FIX02 action-and-update-identity — S2 Code-review Fix

## 1. Gate metadata

- Work unit：`UF-FIX02 action-and-update-identity`
- Slice：`S2 — Complete-set replacement, restore, and cross-market propagation`
- Gate：`code review -> fix`
- Controller adjudication：
  `docs/gateflow/uf-fix02-action-and-update-identity-s2-code-review-adjudication-20260813.md`
- Reviewed implementation：
  `docs/gateflow/uf-fix02-action-and-update-identity-s2-implementation-20260813.md`
- Findings source：
  `docs/reviews/code-review-20260813-184708-uf-fix02-s2-ds-20260813.md`、
  `docs/reviews/code-review-uf-fix02-s2-mimo-20260813.md`
- Base / current HEAD：`08316516ca3da7f98299ee90d3fa753c32c59020`
- Branch：`codex/upload-filing-oracle`
- Decision：**FIX IMPLEMENTATION PASS；STOP BEFORE RE-REVIEW**
- Artifact path：
  `docs/gateflow/uf-fix02-action-and-update-identity-s2-code-review-fix-20260813.md`

## 2. Scope and owner decision

Controller 只接受了两项 finding，本 gate 没有扩大范围：

1. DS Finding 1：reset→create 后 `created_at` 漂移。
2. MiMo Finding 1：final mutation 测试 double 保留不可达 update override。

问题成立。`created_at` 是 durable source 的首次创建事实，与 `first_ingested_at` 一样不能因内部 mutation 从 update 变为
reset→create 而变化。storage 在 reset 后只看见 missing meta，无法知道旧值；在 storage、workflow、adapter 或展示层补偿都会制造
第二真源。`DoclingUploadService._build_upsert_meta(...)` 在 reset 前已收到 `previous_meta`，同时负责 publication meta 派生，因而是
唯一 owner boundary。

本 gate 的 fix changed files 仅为：

- `dayu/fins/pipelines/docling_upload_service.py`
- `tests/fins/test_docling_upload_service.py`
- S2 implementation artifact addendum
- 本 fix artifact

没有修改 storage、batch/admission/workflow、SEC/CN/HK/material workflow 生产代码、README、registry、oracle、evidence、Host/Engine
design 或既有 review/adjudication artifact。

## 3. Tests-first RED

先只修改 owner tests：

- renamed update 保持 `created_at`；
- filing deleted equal/changed restore 保持 `created_at`；
- material replacement 与 deleted restore shared-owner parity 保持 `created_at`；
- 原 version / `first_ingested_at` / active / integrity assertions 全部保留。

测试通过 monkeypatch 同时控制 upload owner 与真实 FS storage 时钟：初次创建为
`2020-01-01T00:00:00+00:00`，替换/恢复为 `2020-01-02T00:00:00+00:00`，避免 `now_iso8601()` 秒级精度导致
偶然假绿。生产 owner 尚未修改时运行：

```bash
source .venv/bin/activate
pytest \
  'tests/fins/test_docling_upload_service.py::test_execute_upload_existing_full_input_replaces_exact_complete_set' \
  'tests/fins/test_docling_upload_service.py::test_execute_upload_deleted_input_republishes_complete_source' -q
```

精确结果：**6 failed**。失败参数为：

- filing same-name update；
- filing renamed update；
- material existing create-overwrite；
- filing deleted equal restore；
- filing deleted changed restore；
- material deleted equal restore。

六项失败均只命中新增 owner assertion：实际 `created_at` 为第二阶段时间，预期为初次创建时间。该 RED 直接证明 root cause，
没有依赖日志、下游投影或间接迹象。

## 4. Fix implementation

### 4.1 Publication meta owner

`DoclingUploadService._build_upsert_meta(...)` 现在：

- `previous_meta` 存在且包含非空 `created_at` 时复用该值；
- previous `created_at` 缺失时使用本次唯一 `now`；
- 将结果显式写入 final create 的 meta。

实现与既有 `first_ingested_at` 派生同形，仍以 reset 前 `previous_meta` 为唯一真源；没有 storage/downstream fallback、loose
parsing、默认兼容分支或二次重算。

### 4.2 Test double cleanup

删除 `_FailingFinalUploadSourceRepository.update_source_document(...)`。保留
`create_source_document(...)` 的 `create_failed` 失败注入；
`test_execute_upload_update_failure_keeps_previous_document` 仍断言
`events[-1] == "create_failed"`，继续证明 reset 后 final mutation 只走 create。

## 5. GREEN and regression validation

### 5.1 Exact owner/failure GREEN

```text
8 passed in 0.69s
```

包含六个 `created_at` 场景及 final-create failure 的两个 overwrite 参数。

### 5.2 S2 focused

```text
74 passed, 3 warnings in 1.85s
```

### 5.3 Full owner/boundary focused

```text
321 passed, 3 warnings in 10.25s
```

### 5.4 UF-FIX01 / atomicity / cancellation regressions

```text
343 passed, 3 warnings in 27.80s
```

上述 warning 全部为已安装 `edgar` 包的三条既有 deprecation warning。

## 6. Coverage and type check

使用 `mktemp -d` 下的独立 coverage data file；仓库内未写入 coverage 产物：

```text
Name                                            Stmts   Miss  Cover
-------------------------------------------------------------------
dayu/fins/pipelines/docling_upload_service.py     391     50    87%
-------------------------------------------------------------------
TOTAL                                             391     50    87%
```

本 gate 唯一修改生产文件 coverage 为 **87%**，满足逐文件 `>=80%`。

完整类型检查：

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

pyright 另提示可升级工具版本，不是类型错误或项目 warning。

## 7. Diff, static, and no-touch audit

- `git diff --check`：通过。
- `git diff --exit-code -- docs/cli_ci_scenarios.json docs/cli_ci_oracles.json docs/host/design.md docs/engine/design.md`：通过。
- frozen registry SHA-256：
  - `docs/cli_ci_scenarios.json`：`a357e5a1e0ee11cb42f8ab6e25083b23761a4c8181d14ddc1876f0bf9a788efb`
  - `docs/cli_ci_oracles.json`：`88b04ca47472f320b614ad1374a9f0a243443efaca1e0565eaf29b5f0cb770b8`
- `rg -n '_resolve_upsert_mode' --glob '*.py' .`：exit `1`、无输出，Python 源码零命中。
- production added-lines audit：无新增 `hasattr/getattr`、`Any/object`、`str(exc)`、lazy import、compat
  wrapper/re-export、basename/stem identity、默认 deleted state或下游 fallback。
- publication audit：无 commit 后补偿删除、跨 batch replacement、ticker 级清空或 second lock recheck。
- scope audit：没有 UF-FIX03–08/10/11、UF-PF02 或 UF-PF03–12 内容。

README 决策：既有 README 已承诺 reset 前 meta 是版本与首次创建事实真源；本 fix 不改变用户可见 action/publication 语义、分层、
装配、入口、测试能力边界或排障方式，因此不修改 README。

## 8. Finding status and residual risks

| Finding | Fix status | Evidence |
| --- | --- | --- |
| DS F1：reset→create 重置 `created_at` | 已修复，等待 re-review | 精确 RED 6；owner GREEN 6；S2/regression/coverage/pyright 全通过 |
| MiMo F1：dead update override | 已修复，等待 re-review | override 已删除；create failure 两参数 GREEN，`create_failed` 断言保留 |

既有 residual risks 及 owner 不变：UF-FIX10 concurrency、UF-FIX08 repair、UF-FIX07 collision、UF-FIX06 format、UF-FIX03
counts/errors、UF-FIX11 company warning、UF-PF12 broader conformance、后续统一 frozen evidence refresh，以及 material broader typed
projection/focused-real。没有新增未分类 residual risk。

## 9. Completion and stop

- Code-review fix gate：**PASS**。
- Re-review：**未进入**；finding 的最终裁决留给后续独立 re-review。
- UF-PF02：**未进入**。
- Commit / push / PR：**均未执行**。
- Current HEAD：`08316516ca3da7f98299ee90d3fa753c32c59020`。
- Stop condition：按 Controller 指令在本 fix artifact 与 validation 完成后停止。

## 10. S2 re-review documentation closeout addendum（2026-08-13）

双路 S2 re-review 均为 **PASS**：

- `docs/reviews/code-review-20260813-190336-uf-fix02-s2-rereview-ds-20260813.md`
- `docs/reviews/code-review-uf-fix02-s2-rereview-mimo-20260813.md`

AgentDS 提示 `dayu/fins/README.md` 的 source publication 契约只把 version 与 `first_ingested_at` 列为 reset 前 source meta
真源，遗漏了当前实现已从同一 `previous_meta` 派生并保持的 `created_at`。该提示不改变双路 re-review 的 PASS 裁决；Controller
接受其为文档精确性修复。

本 documentation closeout 只将 README 的该句补全为 version、`first_ingested_at` 与 `created_at` 共用 reset 前 source meta
真源，并追加本 addendum。§7 的 README 决策保留为 fix gate 当时记录，由本 addendum 记录后续 Controller 裁决；生产、测试、其它
README、既有 review/adjudication 均未修改，也未改变任何 contract、schema、状态机或用户可见行为。

验证只执行文档 closeout 所需的 `git diff --check`、frozen no-touch 与全文语义核对；因无代码变化，不重复测试或 pyright。没有
新增 residual risk；commit、push、PR 与下一 gate 均未执行，完成后停止。
