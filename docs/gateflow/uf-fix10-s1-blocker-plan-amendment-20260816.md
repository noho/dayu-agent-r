# UF-FIX10 S1 blocker plan amendment

## 0. Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- gate：`plan amendment`
- 日期：2026-08-17（文件名沿用 work unit 的 2026-08-16 plan 日期）
- amended plan：`docs/gateflow/uf-fix10-same-request-concurrency-plan-20260816.md`
- blocker evidence：`docs/gateflow/uf-fix10-s1-implementation-20260816.md`
- completion status：`PLAN AMENDMENT / RE-REVIEW REQUIRED / S1 RESUME NOT AUTHORIZED`
- accepted commit：无；当前 partial implementation 与本 amendment 均不可提交
- artifact path：`docs/gateflow/uf-fix10-s1-blocker-plan-amendment-20260816.md`
- 下一入口：`plan re-review`

## 1. Scope 与不变量

本 gate 只修订 accepted plan 的 Gate 元数据、`§10.1 Slice S1` fixture/protocol-conformance 边界及为消除正文矛盾所必需的对应 affected-file/risk 引用，并新增本 artifact。当前 S1 partial implementation 原样保留；不修改任何生产代码、测试、README、oracle、scenario、registry 或 frozen evidence，不运行测试、pyright、coverage 或真实 evidence，不 commit、push 或创建 PR。

本 amendment 不改变 UF-FIX10 的 goal、语义 owner、其它 allowed production/test scope、S1 零 observable 行为要求、S1/S2 activation boundary、S2 exact changes、validation exclusions、README trigger 或 residual owner。特别是 S1 仍不得接通 filing typed disposition/shared publication route，不得改变 filing early-skip 或 SEC/CN/HK workflow 行为；S2 仍是唯一启用新 filing 语义的原子 slice。

## 2. Direct pyright evidence 与 root cause

S1 implementation artifact 保存了以下已执行命令的直接结果；本 gate 不重跑该命令：

```text
source .venv/bin/activate && python -m pyright \
  dayu/fins/pipelines/filing_upload_publication.py \
  dayu/fins/pipelines/docling_upload_service.py \
  dayu/fins/upload_failure.py \
  dayu/fins/storage/repository_protocols.py \
  dayu/fins/storage/_fs_company_meta_core.py \
  dayu/fins/storage/_fs_source_integrity.py \
  dayu/fins/storage/_fs_filing_upload_state_core.py \
  dayu/fins/storage/fs_filing_upload_state_repository.py \
  dayu/fins/storage/__init__.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_direct.py
```

结果为 1 个错误：

```text
tests/fins/test_fins_ingestion_runtime.py:10865:40
_FixedFilingUploadStateRepository is incompatible with
FilingUploadStateRepositoryProtocol: read_filing_upload_state_in_batch is not present
```

root cause 是 accepted plan 的 S1 census 只枚举了 `FilingUploadPublishedState(...)` direct constructors，没有枚举 `FilingUploadStateRepositoryProtocol` 的 structural implementers。S1 production contract 新增 required `read_filing_upload_state_in_batch(batch, document_id)` 后，直接注入的 `_FixedFilingUploadStateRepository` 被 pyright 正确拒绝；同文件 `_ForbiddenFilingUploadStateRepository` 也缺少该方法，只是 `_build_static_admission_guarded_runtime()` 的 cast 绕过了 structural check。

这不是 production protocol 过严，也不是 runtime 需要 fallback。两个 fake 分别拥有 runtime prevalidation 固定 state 与 static admission 禁止 state read 的测试语义；正确修复 owner 是让它们显式实现同一个 required protocol contract，并让注入点无 cast 地接受静态检查。用 protocol default、optional method、cast、`hasattr/getattr`、兼容 wrapper 或下游 fallback 都会掩盖真实 contract drift，禁止采用。

## 3. Plan amendment decision

`§10.1` 的唯一 scope amendment 如下：

1. `tests/fins/test_fins_ingestion_runtime.py` 除 direct constructors 机械补 `publication_identity=None` 外，允许且要求两个既有 structural fake 同步新 required method。
2. `_FixedFilingUploadStateRepository.read_filing_upload_state_in_batch(batch, document_id)` 记录独立 `batch_calls` 并返回构造时传入的固定 `state`；不得污染既有 published-state `calls`。
3. `_ForbiddenFilingUploadStateRepository` 的同签名方法记录独立 `batch_calls` 后明确抛出 `AssertionError`，固定 static admission 阶段禁止 published/batch 两类 state read。
4. `_build_static_admission_guarded_runtime()` 移除 fake 注入处 cast；两个 builder 都直接传入 structural fake，以 pyright 作为真实 conformance signal。不得以任何新 cast/default/getattr/兼容路径替代。
5. exact fake tests 使用显式 `BatchToken` 断言 fixed fake 返回同一 state、forbidden fake 明确失败、两者 `calls` 与 `batch_calls` 互不混淆；现有 static admission tests 增加 `batch_calls == []`，现有 unsafe runtime prevalidation 继续精确产生两个 published-state reads 且 `batch_calls == []`，其余零副作用与 terminal 语义不变。
6. S1 恢复后的 validation 增加 focused `python -m pyright tests/fins/test_fins_ingestion_runtime.py` signal，并仍须完成原计划 full pyright；当前 amendment gate 不执行二者。

除上述 amendment 外，所有 allowed scope、S1 零行为约束和 S2 边界保持不变。

## 4. 当前 partial diff 与提交禁令

当前 partial implementation 保留以下 production files：

- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_company_meta_core.py`
- `dayu/fins/storage/_fs_filing_upload_state_core.py`
- `dayu/fins/storage/_fs_source_integrity.py`
- `dayu/fins/storage/fs_filing_upload_state_repository.py`
- `dayu/fins/storage/__init__.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/filing_upload_publication.py`
- `dayu/fins/upload_failure.py`

并保留已发生 required-constructor 机械变化的 fixture files：

- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_service_runtime.py`
- `tests/cli/test_fins_commands.py`
- `tests/service/test_fins_direct.py`

该 partial diff 尚未完成 amended §10.1 fake conformance、owner tests、focused/full tests、coverage 或 full pyright closure，不构成 accepted S1，不得 stage 或 commit。plan re-review pass 之前不得继续修改 partial implementation，也不得把本 amendment 解释为 S1 resume authorization。

## 5. Validation 与 docs decision

本 gate 只运行并只记录 docs diff/结构检查，结果如下：

- amended plan 的 status、next entry、§10.1 allowed test/change/assertion/pyright signal 与 affected-file/risk 引用一致；结构关键字检查通过。
- 新 artifact 的 7 个 required sections 均精确存在，覆盖 gate、scope、direct evidence、root cause、decision、partial diff、validation、docs decision、residual risk、completion status 与 artifact path。
- tracked plan 的 `git diff --check` 零输出、exit 0；新 artifact 以 `git diff --no-index --check /dev/null <artifact>` 独立检查，零 whitespace 输出（exit 1 仅表示 `/dev/null` 与新增文件存在预期 diff）。
- 对照本 gate preflight 与最终 `git status --short`，本 gate 的实际写入范围仅为 amended plan 与本 artifact；既有 production/test partial diff 及 S1 implementation artifact 均原样保留。

未运行 pytest、pyright 或 coverage；不得把 S1 implementation artifact 中的失败 signal 冒充本 gate 新验证。README decision 为不更新：本 gate 只修订 plan contract，没有落地生产行为、测试工作流或用户可见变化。

## 6. Findings、residual risks 与 decision

- accepted blocker：S1 plan 漏列两个 required protocol structural fakes；状态为 `plan amended / re-review required`。
- 当前 partial implementation：未完成、未验证、不可提交；owner 为后续获授权的 S1 implementation gate。
- 未分类 residual risk：无。唯一 blocker 的修订路径已冻结，但尚未通过 plan re-review，因此不能恢复 S1。
- gate decision：`PLAN AMENDMENT / RE-REVIEW REQUIRED / S1 RESUME NOT AUTHORIZED`。
- 下一入口：对 amended plan 执行 plan re-review；只有 re-review pass 并由 Controller 明确重新授权后，才可从 S1 blocker 处恢复实现。
