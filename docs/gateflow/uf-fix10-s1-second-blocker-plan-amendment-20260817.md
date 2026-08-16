# UF-FIX10 S1 second blocker plan amendment

## 0. Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- gate：`second plan amendment`
- 日期：2026-08-17
- amended plan：`docs/gateflow/uf-fix10-same-request-concurrency-plan-20260816.md`
- blocker evidence：`docs/gateflow/uf-fix10-s1-implementation-20260816.md`
- completion status：`SECOND AMENDMENT / RE-REVIEW REQUIRED / S1 RESUME NOT AUTHORIZED`
- accepted commit：无；当前 production/tests partial implementation 与本 amendment 均不可提交
- artifact path：`docs/gateflow/uf-fix10-s1-second-blocker-plan-amendment-20260817.md`
- 下一入口：`plan re-review`

## 1. Scope 与不变量

本 gate 只修订 accepted plan 的 Gate 元数据、`§8.2` affected-test census、`§10.1 Slice S1` fixture/protocol-conformance 边界与对应 residual risk，并新增本 artifact；同时只在既有 S1 implementation artifact 末尾追加第二次 blocker 历史。当前 production/tests partial implementation原样保留，不修改任何生产代码、测试、README、oracle、scenario、registry 或 frozen evidence，不运行 pytest、pyright、coverage，不 commit、push 或创建 PR。

本 amendment 不改变 UF-FIX10 goal、production owner、S1 零 observable 行为要求、S1/S2 activation boundary、S2 exact changes、README decision 或 validation exclusions。S1 仍不得接通 filing typed disposition/shared publication route，不得改变 filing early-skip 或 SEC/CN/HK workflow 行为；S2 仍是唯一启用新 filing 语义的原子 slice。

## 2. Direct full-pyright evidence 与 root cause

首次 amendment 恢复 S1 后，implementation 已完成首次 amendment 明列的 `tests/fins/test_fins_ingestion_runtime.py` 两个 fake conformance；其 focused pyright 为 `0 errors`，focused tests、完整 `tests/fins` 与 coverage threshold 也已通过。随后执行冻结的全仓命令：

```text
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

在本轮新增 test narrowing errors 由其 owner 文件修复且 scoped pyright 回到 `0 errors` 后，剩余 blocking structural evidence 为：

```text
tests/fins/test_fins_ingestion_tools.py:2474:40
_ForbiddenFilingUploadStateRepository is incompatible with
FilingUploadStateRepositoryProtocol: read_filing_upload_state_in_batch is not present
```

直接代码证据确认该 fake 位于 `tests/fins/test_fins_ingestion_tools.py`，由 `_runtime_with_static_admission_guard()` 无 cast 地直接注入 `FinsIngestionRuntime.create()`。它只实现 published `read_filing_upload_state()` 并以 `AssertionError` 固定 tool calendar/year static admission 前禁止 state read；新增 required batch method 后，它与首次 amendment 的 runtime forbidden fake 属于同一 protocol-conformance 语义，但未被首次 amendment 的“两 fake”census 覆盖。

root cause 是 accepted plan 与首次 amendment 的 structural implementer census 仍不完整，不是 production protocol 过严，也不是 tool runtime 需要 fallback。正确 owner 是该 structural fake 自身的真实 required protocol conformance；用 cast、protocol default、optional method、`hasattr/getattr`、compatibility wrapper 或 runtime fallback 都会掩盖 contract drift，继续禁止。

## 3. Second amendment decision

`§10.1` 的唯一第二次 scope amendment 如下：

1. allowed tests 增加 `tests/fins/test_fins_ingestion_tools.py`，但只授权该文件既有 `_ForbiddenFilingUploadStateRepository` 同步 required batch method与对应零行为断言。
2. fake 新增独立于现有 `calls` 的 `batch_calls: list[tuple[BatchToken, str]]`。
3. `read_filing_upload_state_in_batch(batch, document_id)` 使用 required protocol 精确签名，先记录 `(batch, document_id)`，再明确抛出 `AssertionError`，固定 tool static admission 禁止 published/batch 两类 state read。
4. 新增 direct exact conformance signal：显式 `BatchToken` 调用必须 record-then-fail，且既有 `calls` 不变。
5. 所有使用 `_runtime_with_static_admission_guard()` 的现有 static-admission cases 只在既有 `calls == []` 与零副作用断言旁增加 `batch_calls == []`；不得修改其它 assertion、fixture、tool schema 或业务语义。
6. 不得新增 cast、default、optional method、`hasattr/getattr`、兼容 wrapper 或 runtime fallback；focused pyright 扩展为同时检查 runtime/tools 两个文件，full pyright仍为最终 required signal。

除上述 amendment 外，所有 production/test scope、S1 零行为约束、S2边界与 validation contract 保持不变。

## 4. 当前 partial implementation 与验证事实

当前 production/tests partial implementation 继续保留，且本 gate 不对其做任何写入。进入第二次 blocker 前已取得以下 implementation evidence：

- frozen focused 八文件测试：`834 passed, 3 warnings`。
- 完整 `pytest tests/fins -q`：`1871 passed, 1 skipped, 3 warnings`。
- coverage：冻结两测试集对精确四模块的总覆盖率为 `82%`；加入各 owner 测试后的逐文件结果为 arbitration `86%`、Docling `88%`、storage batch-state core `95%`、typed failure `84%`，总计 `88%`。原多 `--cov=<同包模块>` pytest-cov 入口在本机重复加载 NumPy，使用同一测试集的 coverage.py 单次采集取得上述阈值事实；不得把环境 collection error 伪装成代码 failure。
- `python -m pyright tests/fins/test_fins_ingestion_runtime.py`：`0 errors`，证明首次 amendment 的两个 fake 已真实 conform。
- 本轮新增四个 owner test 文件 scoped pyright：`0 errors`。
- full pyright：被上述 `tests/fins/test_fins_ingestion_tools.py:2474:40` 第三个 fake 阻塞，不能声明全仓通过。

上述通过结果不消除 full-pyright blocker，也不授权提交。当前 partial diff 不构成 accepted S1；第二次 re-review pass 前不得继续修改 production/tests。

## 5. Validation 与 docs decision

- 本 second amendment gate 不运行 pytest、pyright 或 coverage；只记录 implementation gate 已产生的直接 evidence。
- plan 的 metadata、affected-test census、§10.1 allowed tests/exact changes/assertions/validation/completion/stop condition与 residual risk 同步修订。
- 本 gate 只执行 docs diff、结构与 whitespace 检查。
- README decision：不更新。该 gate 只修订 plan/test-fixture boundary，没有生产行为、最终用户工作流或 README 职责范围内变化。

## 6. Findings、residual risks 与 decision

- blocking finding：首次 amendment 的 structural implementer census 仍漏列 tool static-admission 第三个 fake；状态为 `second plan amended / re-review required`。
- production/tests partial implementation：focused/full tests 与 coverage已通过，但 full pyright 未闭合，仍不可提交；owner 为第二次 re-review 通过后获授权恢复的 S1 implementation gate。
- 未分类 residual risk：无。第三个 fake 的唯一最小修订路径已冻结，但尚未通过 plan re-review，因此不能恢复 S1。
- 未修改 material、UF-FIX11、SEC/CN/HK workflow、workflow tests、README、oracle、scenario、registry 或 frozen evidence；无新增 S2 lifecycle route。
- gate decision：`SECOND AMENDMENT / RE-REVIEW REQUIRED / S1 RESUME NOT AUTHORIZED`。
- 下一入口：对 second amended plan 执行 plan re-review；只有 re-review pass 并由 Controller 明确重新授权后，才能恢复 S1 implementation。
