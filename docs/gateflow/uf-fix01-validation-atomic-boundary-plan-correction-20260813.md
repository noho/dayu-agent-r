# UF-FIX01 validation-atomic-boundary — Implementation Blocker Plan Correction

## 1. Metadata

- **gate**：implementation S1 → plan factual correction
- **baseline plan commit**：`5031ec6b7b7d53a41fe9fb1fc41b5b393260dfbd`
- **trigger**：S1 owner tests 首轮 `5 failed, 389 passed`
- **decision**：目标、owner、public protocol 与 non-goals 不变；修正 accepted plan 的两个错误代码事实与一个测试 fixture
- **implementation state**：AgentCodex 已停止 S2–S5；失败的局部 S1 改动已用非破坏补丁恢复，工作树 clean

## 2. Direct evidence

1. `dayu/fins/storage/_fs_identity.py::_identity_directory_for_read` 的 docstring 与实现明确规定：identity
   directory absent 时仍返回 deterministic locator，只在目录存在或为 symlink 时读取/校验 descriptor。
   Accepted plan 错误地假设该 helper 会在 absent 时抛 `FileNotFoundError`。
2. `DefaultFinsRuntime.get_ingestion_runtime` 构造 SEC/CN/HK download adapters 与 SEC/CN upload pipelines；
   `SecPipeline`、`CnPipeline` constructors 各自无条件调用默认
   `build_fs_repository_set(create_directories=True)`。即使调用方已注入全部具体 repositories，也先创建一个
   未使用的 eager set，因而产生 `portfolio`、batch/recovery/lock directories。
3. 两条新增 snapshot tests 使用空 `files` source fixture；storage complete-source commit contract 要求
   `files` 非空，因此 fixture 在 snapshot assertion 前失败。

## 3. Five failed tests and adjudication

| Test | Root cause | Correction |
| --- | --- | --- |
| `test_filing_upload_state_fresh_absent_is_pure_and_lock_free` | locator absent 仍返回 Path，随后 guard 建 lock | private tri-state identity/ticker helper |
| `test_filing_upload_state_reads_company_and_source_under_one_guard` | source fixture `files=[]`，commit validation 先失败 | 发布至少一个真实 source file |
| `test_filing_upload_state_preserves_independent_member_absence` | source-only fixture 同样 `files=[]` | 发布至少一个真实 source file |
| `test_filing_upload_state_repository_is_public_non_mutating_storage_contract` | 与 fresh absent locator 同源 | private tri-state helper |
| `test_default_runtime_create_and_ingestion_assembly_are_lazy` | SEC/CN constructors 构造默认 eager repository set | fallback set `create_directories=False` |

## 4. Corrected owner design

- `_fs_identity.py` 新增 private `_identity_directory_if_present_for_read(...) -> Path | None`，仍由 identity
  storage owner 负责 locator、symlink 与 descriptor 语义；不让 CLI/service/pipeline 使用裸路径。
- `_fs_storage_infra.py` 新增 private `_ticker_dir_if_present_for_read(...) -> Path | None`，只委托 identity
  helper；snapshot absent 分支在任何 guard/mkdir 前返回。
- 公开 `FilingUploadStateRepositoryProtocol`、typed state、事务与调用分层均不变。
- SEC/CN pipeline 内部 fallback repository set 改为 lazy；真实 write owner 继续在 begin/write 时建目录。
  不新增 public repository-set 参数、factory wrapper 或 compatibility seam。

## 5. Scope delta

- 新增允许修改：`dayu/fins/storage/_fs_identity.py`、`dayu/fins/storage/_fs_storage_infra.py`。
- `sec_pipeline.py`、`cn_pipeline.py` 已在 accepted plan 的修改范围，本 correction 只补充 lazy fallback symbols。
- 测试仍限 accepted S1 owner files，并使用真实 durable source fixture。
- 不改变 usage code/message、action/identity/date/year/format、company/source batch protocol、UF-FIX09、
  Host/Engine、registry/frozen evidence 或 external-operation constraints。

## 6. Gate decision

这是 accepted plan 的 factual correction，不是 goal/owner/architecture change。经 AgentMiMo、AgentDS 双路
delta `/planreview` 通过并创建本地 correction checkpoint 后，可从 S1 重新实现；否则继续保持 implementation blocked。
