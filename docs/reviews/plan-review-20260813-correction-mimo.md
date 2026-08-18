# UF-FIX01 Validation-Atomic-Boundary — Correction Delta Review (MiMo)

## 1. Reviewed Target

- **target**：`docs/gateflow/uf-fix01-validation-atomic-boundary-plan-correction-20260813.md`
- **scope**：对 accepted plan 的三个 factual correction 做独立 delta review
- **baseline**：`docs/gateflow/uf-fix01-validation-atomic-boundary-plan-20260813.md`
- **reviewer**：AgentMiMo（独立裁决，不依赖另一 reviewer 结论）
- **timestamp**：`20260813-104208`

## 2. Frozen Inputs Read

- `docs/gateflow/uf-fix01-validation-atomic-boundary-plan-20260813.md` (accepted plan)
- `docs/gateflow/uf-fix01-validation-atomic-boundary-plan-correction-20260813.md` (correction)
- `dayu/fins/storage/_fs_identity.py` (identity read helpers)
- `dayu/fins/storage/_fs_storage_infra.py` (ticker helpers, storage infra)
- `dayu/fins/storage/_fs_repository_factory.py` (build_fs_repository_set signature)
- `dayu/fins/pipelines/sec_pipeline.py` (SecPipeline constructor)
- `dayu/fins/pipelines/cn_pipeline.py` (CnPipeline constructor)
- `dayu/fins/service_runtime.py` (DefaultFinsRuntime assembly)

## 3. Assumptions Tested

1. Accepted plan 假设 `_identity_directory_for_read` 在 absent 时抛 `FileNotFoundError`。
2. Accepted plan 假设 SEC/CN pipeline constructor 不会在 caller 已注入 repositories 时创建 eager directories。
3. 测试 fixture source `files=[]` 满足 storage complete-source commit contract。

## 4. Evidence-Based Verification

### 4.1 Correction #1：`_identity_directory_for_read` 行为

**accepted plan 写法**（§6.3）：声称 `_ticker_dir_for_read` 的真实契约是 absent 时仍返回确定性 locator，不得把它误当 absent predicate。

**accepted plan 测试假设**：`test_filing_upload_state_fresh_absent_is_pure_and_lock_free` 假设 fresh absent 时 locator helper 会抛出，从而阻止 guard 建立。

**代码事实**（`_fs_identity.py:286-326`）：

```python
def _identity_directory_for_read(...) -> Path:
    """返回 lookup locator，并在目录存在时强制 descriptor 校验。
    ...
    Returns:
        对应 identity directory；目录不存在时仍返回确定性 locator。
    """
    ...
    directory = _identity_directory_path(root, namespace, identity)
    if directory.exists() or directory.is_symlink():
        _read_identity_descriptor(...)
    return directory
```

该 helper **明确返回** deterministic locator path，即使 directory 不存在。它只在 directory exists 时校验 descriptor。因此 fresh absent 路径上，caller 收到一个不存在的 `Path`，随后尝试 `_acquire_publication_guard` 会在 `.dayu` batch lock root 不存在时创建目录。

**裁决**：correction #1 的事实认定 **正确**。accepted plan 对 `_identity_directory_for_read` 行为的假设是错误的。新增 `_identity_directory_if_present_for_read -> Path | None` tri-state helper 是对事实的正确修正，而非架构变更。

### 4.2 Correction #2：SEC/CN pipeline constructor eager bootstrap

**代码事实**（`sec_pipeline.py:526`、`cn_pipeline.py:363`）：

```python
# SecPipeline.__init__
repository_set = build_fs_repository_set(workspace_root=self._workspace_root)

# CnPipeline.__init__
repository_set = build_fs_repository_set(workspace_root=self._workspace_root)
```

两者均未传 `create_directories`，使用默认值 `True`（`_fs_repository_factory.py:29`）。即使 caller 已注入全部具体 repositories，constructor 仍先创建一个未使用的 eager repository set，产生 `portfolio`、`.dayu`、batch/recovery/lock directories。

**裁决**：correction #2 的事实认定 **正确**。`build_fs_repository_set` 已有 `create_directories` 参数（line 29），correction 只需在 SEC/CN constructor fallback 调用处传 `False`，不修改 factory 文件本身。

### 4.3 Correction #3：测试 fixture `files=[]`

**代码事实**（`_fs_storage_infra.py:938-939`）：

```python
raw_files = meta.get("files")
if not isinstance(raw_files, list) or not raw_files:
    raise ValueError(f"complete source files 必须为非空数组: {document_id}")
```

storage commit contract 强制 `files` 非空。测试 fixture 使用 `files=[]` 会在 snapshot assertion 前被 commit validation 拒绝。

**裁决**：correction #3 的事实认定 **正确**。source fixture 必须包含至少一个真实业务文件。

## 5. Architecture Boundary Review

### 5.1 Private tri-state helper 保持 storage 唯一 owner

- `_identity_directory_if_present_for_read` 定义在 `_fs_identity.py`（identity owner），复用既有 `_identity_directory_path` + `_read_identity_descriptor` 校验逻辑。
- `_ticker_dir_if_present_for_read` 定义在 `_fs_storage_infra.py`（ticker infra owner），只委托 identity helper。
- 两者均为 `private`（`_` 前缀），不暴露到 `storage/__init__.py` 公共导出。
- `FsFilingUploadStateRepository.read_filing_upload_state` 是唯一 caller，通过 `None` 返回值短路 absent 路径，不调用 `_acquire_publication_guard`，不创建 `.dayu`、`portfolio`、lock。
- **裸 `Path.exists` 不泄漏**：`_identity_directory_if_present_for_read` 内部使用 `directory.exists()` / `directory.is_symlink()`，这些调用在 identity owner boundary 内，与既有 `_identity_directory_for_read` 行为一致。

### 5.2 Lazy fallback `create_directories=False` 最小且无需 public API

- `build_fs_repository_set` 已有 `create_directories: bool = True` 参数（`_fs_repository_factory.py:29`），correction 只在 SEC/CN constructor fallback 调用处传 `False`。
- 不新增 factory wrapper、overload 或 public parameter。
- `DefaultFinsRuntime.create` 已在 accepted plan 中修改为 `create_directories=False`，correction 只扩展到 SEC/CN pipeline 内部 fallback。
- 真实首次写仍由 `begin_batch` / repository write owner 创建目录。

### 5.3 真实非空 source fixture 符合 storage contract

- `_validate_complete_source_files`（`_fs_storage_infra.py:938`）强制 `files` 非空。
- correction 要求 fixture "发布至少一个真实业务文件并通过 complete-source commit validation"，与 storage contract 一致。
- 不使用空 `files` 假造 durable source。

### 5.4 保持 goal/non-goals/UF-FIX09

- correction 明确声明："目标、owner、public protocol 与 non-goals 不变"。
- 不改变 usage code/message、action/identity/date/year/format、company/source batch protocol。
- 不修改 Host/Engine、registry/frozen evidence。
- UF-FIX09 shared converter 不受影响（correction 只修改 storage identity/ticker helper 和 pipeline constructor fallback）。

## 6. Findings

**无 material findings。**

三个 correction 均基于直接代码事实，修正了 accepted plan 对 `_identity_directory_for_read` 行为、SEC/CN constructor eager bootstrap 和 storage commit `files` 非空约束的错误假设。修正范围最小化，不引入新架构、新 public API 或新 ownership 边界。

## 7. Open Questions

**无。**

## 8. Residual Risks

- **tri-state helper 测试覆盖**：correction 要求 S1 owner tests 覆盖 `_identity_directory_if_present_for_read` 和 `_ticker_dir_if_present_for_read` 的各种边界（symlink、broken symlink、descriptor mismatch、corruption），这些在 accepted plan S1 assertions 中已有覆盖要求，correction 不新增覆盖缺口。
- **SEC/CN constructor `create_directories=False` 后的写路径**：`begin_batch` 内部调用 `_ensure_batch_storage_dirs()`（`_fs_storage_infra.py:512`），确保首次写时创建目录。correction 不改变此路径。

## 9. Conclusion

**PASS**

correction 的三个 factual claim 均经代码事实独立验证成立。修正方案最小化，保持 storage owner 边界、public protocol、goal/non-goals 和 UF-FIX09 不变。无 blocking findings。
