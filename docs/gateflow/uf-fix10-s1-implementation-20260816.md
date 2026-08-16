# UF-FIX10 S1 implementation artifact

## Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- slice：`S1 — behavior-preserving owner contracts`
- gate：`implementation`
- 日期：2026-08-17（accepted plan 文件日期为 2026-08-16）
- completion status：`BLOCKED / PLAN REVIEW REQUIRED`
- artifact path：`docs/gateflow/uf-fix10-s1-implementation-20260816.md`
- accepted commit：无；用户明确禁止 commit
- 下一入口：plan review，裁决 S1 fixture/protocol implementer 边界

## 动机与 owner 判断

动机成立。直接代码证据确认：现有 per-ticker writer 会在 `begin_batch()` 返回前克隆最新 published tree，但现有 filing workflow 在 preparation 后没有 writer-owned staging fresh arbitration；storage inspector 已拥有 durable source provenance、files、roles、primary 与 physical digest，适合作为 durable publication identity producer；Docling preparation 已拥有 prepared bytes、roles、fingerprint/version 与 staging meta 构造事实。

本轮按 accepted plan 将以下语义放在唯一 owner：

- publication identity/asset source/state/protocol：`dayu.fins.storage.repository_protocols`；
- strict published/staging company parser：`_fs_company_meta_core.py`；
- durable identity：`_fs_source_integrity.py` 同次 trusted inspection；
- published/batch state projection：`_fs_filing_upload_state_core.py`；
- prepared filing subtype/disposition/helpers与九字段 staging meta：`docling_upload_service.py`；
- batch-time pure arbitration：`filing_upload_publication.py`；
- typed path-free conflict：`upload_failure.py`。

未接入 `prepare_upload()` typed disposition，未删除 filing early skip，未新增 shared lifecycle route，未修改 SEC/CN/HK workflow、workflow tests、README、oracle、scenario 或 evidence。

## 当前 partial diff

### Production

- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_company_meta_core.py`
- `dayu/fins/storage/_fs_filing_upload_state_core.py`
- `dayu/fins/storage/_fs_source_integrity.py`
- `dayu/fins/storage/fs_filing_upload_state_repository.py`
- `dayu/fins/storage/__init__.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/filing_upload_publication.py`
- `dayu/fins/upload_failure.py`

### Mechanical fixture changes

- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_service_runtime.py`
- `tests/cli/test_fins_commands.py`
- `tests/service/test_fins_direct.py`

四个 fixture 文件目前只给既有 `FilingUploadPublishedState(...)` direct constructors 机械补了 required `publication_identity=None`，未改 assertion 或 fake 行为。

## Blocking evidence

执行：

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

结果：1 个错误，直接证据如下：

```text
tests/fins/test_fins_ingestion_runtime.py:10865:40
_FixedFilingUploadStateRepository is incompatible with
FilingUploadStateRepositoryProtocol: read_filing_upload_state_in_batch is not present
```

根因是 accepted plan 的 constructor census 只覆盖 `FilingUploadPublishedState(...)` direct constructors，但漏掉了 `FilingUploadStateRepositoryProtocol` 的 structural implementer。新增 required batch method 后，该 fake 必须同步实现新协议，或注入点必须改变类型；两者都超出 §10.1 对该 fixture 文件“只能机械补 required field，不得改 fake 语义”的冻结边界。不能通过 default、optional protocol、cast、兼容 wrapper 或 fallback 规避。

## Validation 状态

- focused tests：未运行；发现 scope blocker 后按 stop condition 立即停止。
- 完整 `tests/fins`：未运行。
- coverage：未运行，不能声称达到 80%。
- 全仓 pyright：未运行；局部 touched-scope pyright 已失败，错误如上。
- `git diff --check`：未运行。
- expected red：不接受；当前 partial diff 不构成可验收 S1。

## README decision

S1 frozen scope 明确禁止修改 README，且当前 implementation 未完成，因此所有 README 均未修改。

## Findings 与 residual risks

- blocking finding：accepted plan 的 protocol implementer census 与 strict fixture boundary 冲突；状态为 `未修复`，owner 为 plan review/controller。
- partial implementation 尚未补 owner tests、未完成 focused/full/coverage/全仓 pyright 验证，不得接受或提交。
- 未运行 UF-PF10、UF-PF12，未修改 material、UF-FIX11、SEC/CN/HK workflow、oracle、scenario、registry 或 frozen evidence。
- 无新增通用 OCC、global lock、retry、sleep、directory fallback 或兼容分支。
- remaining risk 已分类为 `requiring explicit user decision`：允许对 `_FixedFilingUploadStateRepository` 做最小 required protocol method fixture 更新，或回到 plan review 重划 protocol/fixture allowed scope。
