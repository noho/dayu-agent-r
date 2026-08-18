# UF-FIX09 Aggregate Fix Confirmation

## 1. Gate

- 日期：2026-08-12
- Work unit：`UF-FIX09 shared-interruptible-docling-converter`
- Gate：aggregate deepreview fix confirmation（no-op）
- Base：`3f24d75adba49868fbc8646ac9c81f5a0a4a3c2e`
- 冻结 target：`d40ac173fd308b3329ed7216e0c26b9951663cdc`
- 冻结 base..target diff SHA-256：`2b82f47832f8042b4f498765d08fd34043225fb86c97507ee83a39e6cf126aca`
- Artifact：`docs/gateflow/uf-fix09-aggregate-fix-confirmation-20260812.md`
- 下一入口：同一冻结 target 的双路 aggregate re-review

## 2. Scope

本 gate 只独立核查 aggregate deepreview controller 裁决是否由冻结 plan 与直接代码证据支持，并记录 no-op fix confirmation。只读输入为：

- `docs/reviews/uf-fix09-aggregate-deepreview-20260812-221109.md`
- `docs/reviews/code-review-20260812-220949.md`
- `docs/gateflow/uf-fix09-aggregate-deepreview-adjudication-20260812.md`
- `docs/gateflow/uf-fix09-shared-interruptible-docling-converter-plan-20260812.md` §11.1 与 S2
- `docs/gateflow/uf-fix09-s2-code-review-adjudication-20260812.md`
- 冻结 `base..target` production/test tree

本 gate 未修改生产代码、测试、accepted plan、既有 review/gate artifacts、oracle、scenario registry 或 README；未执行 UF-PF09；未 commit、push 或创建 PR。开始时两份 aggregate review artifact 与 controller adjudication 为未跟踪上游输入，本 gate 保持三者原样。

## 3. 第一性原理判断

no-op 动机成立。fix gate 的正确目标是只修复 controller 已接受且由 owner 级证据证明的当前缺陷，而不是把 reviewer 对正确行为的说明或已冻结 trade-off 转化为新需求。冻结 target 的直接代码与 accepted plan 均支持 controller 裁决；没有发现真实 accepted defect，也没有理由扩大 scope。

冻结性核查结果：

- 当前 `HEAD` 精确等于冻结 target。
- base 与 target 均可解析为指定 commit。
- 重新计算的完整 `base..target` diff SHA-256 精确等于 controller 记录的 `2b82f47832f8042b4f498765d08fd34043225fb86c97507ee83a39e6cf126aca`。

## 4. 逐项核查

### 4.1 AGG-01 — partial batch cancellation

**结论：同意 controller 裁决；不是 accepted finding，不修改代码。**

直接 plan/contract 证据：

- accepted plan §9.1 把 `commit_prepared_upload_batch` 定义为 publication 生命周期唯一 owner；`publish_prepared_upload` 只向 caller-owned batch 写入，不 commit、不 rollback。
- `DoclingUploadService.publish_prepared_upload` 的返回 contract 明确说明 cancelled 结果要求 caller rollback（`dayu/fins/pipelines/docling_upload_service.py:311`）。
- `_store_upload_assets` 的旧 source reset、逐文件 blob write 与最终 source upsert 都携带同一 `batch`（`dayu/fins/pipelines/docling_upload_service.py:435,456,741-792`），没有 batch 外部分发布。
- `commit_prepared_upload_batch` 在 cancelled summary 或 final precommit checkpoint 命中时，对同一 batch 执行一次 rollback 并返回 cancelled；异常发生于 ownership transfer 前时，`finally` 通过 `_rollback_precommit_upload_batch` 恰好一次回滚；进入 commit 后不再由 caller rollback（`dayu/fins/pipelines/docling_upload_service.py:799-877`）。

直接 caller inventory：

- production 中 `publish_prepared_upload(...)` 只有 `commit_prepared_upload_batch` 内一个调用点。
- production 中 publication helper 的业务调用点精确为四个：SEC filing、SEC material、CN/HK filing、CN/HK material（`dayu/fins/pipelines/sec_upload_workflow.py:243,446`；`dayu/fins/pipelines/cn_pipeline.py:898,1167`）。
- 没有绕过唯一 lifecycle owner 的当前 production caller。未来假设新增错误 caller 不能构成冻结 target 的当前缺陷。

owner tests 直接证明取消/失败后的 rollback 与 residue：

- overwrite conversion 后取消保留旧 source 与旧 blob 集合；
- final source upsert 失败时 rollback 一次，source 不存在且 blob residue 为空。

因此 AGG-01 描述的是当前正确 rollback 行为及未来 review 注意事项，不是需要修复的代码缺陷，也不是当前 residual risk。

### 4.2 AGG-02 — callable transport 到 canonical token 的 fail-closed 收窄

**结论：同意 controller 裁决；这是 S2 已冻结并双路复审的显式 trade-off，不修改代码。**

直接 plan/adjudication 证据：

- accepted plan §11.1 明确要求 adapter request 运输现有 `FinsJobCancellationChecker` concrete object：普通 download checkpoint 调用同一对象的 `__call__`，converter boundary 原样接收同一 canonical token，不创建 adapter（plan `:485-509`）。
- accepted S2 要求 direct/durable composite checker 同时实现 callable 与 canonical token contract，identity 从 ingestion 逐层到 converter 不变，且没有第二 flag/adapter（plan `:610-665`）。
- S2 code-review adjudication R1 已基于 SEC/CN/HK 共享 request、依赖方向与 Python 静态契约冲突拒绝该 finding；修复后双路 re-review 均通过，S2 gate accepted（`docs/gateflow/uf-fix09-s2-code-review-adjudication-20260812.md:23-28,74`）。

直接类型与调用路径证据：

- 公共 `CancellationToken` 是 runtime-checkable observation protocol；`FinsJobCancellationChecker` 在 ingestion owner 内同时继承该 protocol 并声明 `__call__`（`dayu/contracts/cancellation.py:20-43`；`dayu/fins/ingestion_runtime.py:904-917`）。
- durable `_RuntimeJobCancellationChecker` 与 direct `_DirectCancellationChecker` 都实现 callable、`is_cancelled`、`cancel_reason`、`requested_at`，同一对象同时满足两种消费面（`dayu/fins/ingestion_runtime.py:1290-1385,1571-1641`）。
- runtime 对 `FinsSourceDownloadAdapterRequest` 只有一个 production 构造点，并直接赋值 `context.cancellation_checker`（`dayu/fins/ingestion_runtime.py:4168-4176`）。
- CN/HK adapter 把 `request.cancellation_checker` 原样传给 `CnPipeline.download_stream`（`dayu/fins/pipelines/cn_pipeline.py:1320-1355`）；workflow 在 converter 调用点将 `_canonical_cancellation(cancel_checker)` 的结果原样传入（`dayu/fins/pipelines/cn_download_filing_workflow.py:307-312`）。
- `_canonical_cancellation` 对 `None` 返回 `None`，对 runtime-checkable canonical token 返回原对象，对纯 callable 显式抛出 `TypeError`（`dayu/fins/pipelines/cn_download_filing_workflow.py:889-908`）。不存在 loose parsing、fallback、wrapper、第二 token 或 identity 替换。

production 路径始终运输 composite concrete object，因此不会触发纯 callable 拒绝；standalone 纯 callable 只在真正进入 converter 时 fail closed。把共享 request 直接标成 `CancellationToken` 会丢失 SEC/普通 checkpoint 所需的 callable 静态契约；引用 ingestion-owned composite protocol 又会造成 pipeline 对上层 owner 的反向依赖。当前实现与冻结设计一致，AGG-02 不是新 defect 或 residual risk。

## 5. Code Change Decision

**无代码修改。**

本 gate 唯一新增文件是本 confirmation artifact。生产代码、测试、accepted plan、两路 aggregate artifacts、controller adjudication 与历史 S2 adjudication 均保持字节不变。没有新增 fallback、兼容分支、下游补偿、测试夹具特例或第二语义 owner。

## 6. Validation

### 6.1 Frozen target 与 caller inventory

- `git rev-parse HEAD`：`d40ac173fd308b3329ed7216e0c26b9951663cdc`。
- base/target commit resolution：通过。
- `git diff <base> <target> | shasum -a 256`：`2b82f47832f8042b4f498765d08fd34043225fb86c97507ee83a39e6cf126aca`，与 controller 一致。
- production `FinsSourceDownloadAdapterRequest(...)` constructor inventory：1 个。
- production `publish_prepared_upload(...)` caller inventory：1 个，位于唯一 lifecycle owner 内。
- production `commit_prepared_upload_batch(...)` business caller inventory：4 个，覆盖 SEC/CN/HK filing/material。

### 6.2 Focused owner tests

```text
source .venv/bin/activate && pytest -q \
  tests/fins/test_docling_upload_service.py::test_execute_upload_overwrite_cancel_after_conversion_keeps_previous_document \
  tests/fins/test_docling_upload_service.py::test_execute_upload_create_final_failure_leaves_document_absent \
  tests/fins/test_cn_download_runtime.py::test_default_runtime_injects_one_converter_into_all_fins_paths \
  tests/fins/test_cn_download_workflow.py::test_cn_download_cancel_after_docling_convert_skips_source_commit
```

结果：`4 passed, 3 warnings in 2.09s`。warnings 均来自已安装 `edgar` package 的既有 deprecation warning，不是本 gate failure。

### 6.3 Focused pyright

```text
source .venv/bin/activate && pyright \
  dayu/fins/pipelines/docling_upload_service.py \
  dayu/fins/pipelines/cn_download_filing_workflow.py \
  dayu/fins/pipelines/cn_pipeline.py \
  dayu/fins/ingestion_runtime.py \
  dayu/fins/service_runtime.py
```

结果：`0 errors, 0 warnings, 0 informations`。pyright 仅提示有可用的新版本，不是类型诊断。

### 6.4 Explicit exclusions 与 hygiene

- 未运行 UF-PF09、真实 CLI/provider 或额外 real Docling execution。
- `git diff --check <base> <target>`：通过。
- `git diff --check`：通过；tracked worktree 无修改。
- 本 artifact trailing-whitespace scan：通过。

## 7. Docs Decision

只新增本 Gateflow confirmation artifact。没有生产、测试、schema、分层、装配、用户工作流、CLI 输出或排障方式变化，因此不触发根 README、`dayu/README.md`、`dayu/fins/README.md`、`tests/README.md` 或其它 README 更新。既有 README decision 保持不变。

## 8. Residual Risks

- AGG-01：不是 residual risk；当前唯一 publication owner 已完整 rollback 同一 batch。
- AGG-02：不是 residual risk；是 accepted plan 与 S2 adjudication 已冻结的 fail-closed trade-off。
- `covered by later approved gate`：UF-PF09 fresh evidence 与 final validation；本 gate 按明确约束不执行 UF-PF09。
- `assigned to later work unit`：company meta 独立事务、Web fetch cancellation、非 POSIX descendant governance、格式/help/XBRL/multi-file 等冻结非目标。
- `requiring user decision`：无。
- 未分类 residual risk：无。

## 9. Completion Status

**NO-OP FIX CONFIRMATION COMPLETE — NO ACCEPTED CODE FINDING**

controller 对 AGG-01 与 AGG-02 的裁决均有 accepted plan、owner contract、冻结 target 调用路径与 focused validation 的直接支持。没有发现裁决错误或真实 accepted defect；冻结 target 保持不变，无生产代码或测试修改。下一入口是 controller 指定的同一冻结 target 双路 aggregate re-review；本 gate 不 commit。
