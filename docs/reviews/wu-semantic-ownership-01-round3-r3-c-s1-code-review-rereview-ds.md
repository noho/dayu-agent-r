# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-C S1 Code Review Re-Review

## Artifact Metadata

- Review type: adversarial code re-review (post code-review fix verification)
- Target slice: `S1 Storage Identity, Commit Point, And Local Durability`
- Branch: `phaseflow/host-issues-control`
- Output file: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-rereview-ds.md`
- Timestamp: 2026-07-13T00:16:58+08:00
- Status: pass

## Review Scope

验证 controller adjudication 接受的 2 个 code-review findings（`R3-C-S1-CR-F01`、`R3-C-S1-CR-F02`）的修复是否正确落地，以及 fix 是否引入新的 material blocker、是否越界到 S2/S3 或工具安全。

### Sources consulted

- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-fix-codex.md`
- Current working tree diff（uncommitted changes）

### Fix scope

| File | Change |
| --- | --- |
| `dayu/fins/storage/_fs_storage_infra.py` | `_replace_directory` 新增 target-exists guard（2 行） |
| `tests/fins/test_fins_storage_atomicity.py` | 新增 `_normalize_object_key` import + 3 个 owner-level 测试函数 |

无 S2/S3、upload/download workflow、Host/Service wait adapter、README、design docs 或 tool-schema 修改。

---

## Finding Verification

### R3-C-S1-CR-F01 — `_replace_directory` target-exists guard

**Controller required fix**: 在 `os.replace(source, target)` 前拒绝已存在的 target（含 broken symlink），并添加 owner-level 测试证明 source/target 不变。

**Production fix** (`_fs_storage_infra.py:308-309`):

```python
if target.exists() or target.is_symlink():
    raise OSError(f"directory replace target 已存在: {target}")
```

逐项验证：

1. **`target.exists()`** — 覆盖普通已存在目录。`Path.exists()` 对存在的目录返回 `True`。✅
2. **`target.is_symlink()`** — 覆盖 broken symlink。`Path.is_symlink()` 在 Python 3.11 中不跟随链接，仅检查路径自身是否为符号链接；broken symlink（指向不存在目标）返回 `True`。✅
3. **检查位置在 `os.replace()` 之前** — 在执行任何文件系统变更前 fail closed。`target.parent.mkdir()` 在前（创建父目录是幂等操作，无副作用），`os.replace()` 在后。✅

**已有 caller 兼容性**：扫描所有 `_replace_directory` 调用点：

| Caller | 调用 | target 前提 |
| --- | --- | --- |
| `commit_batch` (:262) | `_replace_directory(target_dir, backup_dir)` | backup_dir 此前不存在（由 `BatchToken` 构造且从未创建） |
| `commit_batch` (:264) | `_replace_directory(staging_dir, target_dir)` | target_dir 刚被 rename 到 backup_dir 或原本不存在 |
| `_rollback_precommit_batch` (:350) | `_replace_directory(target_dir, staging_dir)` | staging_dir 在 swap 阶段已被 rename 走 |
| `_rollback_precommit_batch` (:354) | `_replace_directory(backup_dir, target_dir)` | target_dir 刚被上一步移回 staging |
| orphan recovery `_recover_orphan_token_dirs` (:834, 840) | `_replace_directory(target_dir, staging_dir)` / `_replace_directory(backup_dir, target_dir)` | staging_dir 在 orphan 状态中不存在；target_dir 已在上一步被移除 |
| orphan backup recovery (:900) | `_replace_directory(backup_dir, target_dir)` | 仅当 `not target_dir.exists()` 时调用 |

所有 caller 在调用前确保 target 不存在。guard 为纯防御性，不会在正常运行中触发。✅

**Test fix** (`test_fins_storage_atomicity.py:799-838`):

```python
@pytest.mark.parametrize("target_kind", ("directory", "broken_symlink"))
def test_replace_directory_rejects_existing_or_broken_symlink_target(
    tmp_path: Path, target_kind: _ReplaceTargetKind,
) -> None:
```

- 参数化 `target_kind`: `"directory"` 和 `"broken_symlink"`，两种都覆盖。✅
- `"directory"` case: 构造真实 target 目录含 `state.txt`，断言 `OSError` + match `"target 已存在"`，然后断言 `source/state.txt == "source"`、`target/state.txt == "target"`。✅
- `"broken_symlink"` case: `target.symlink_to(missing_target, target_is_directory=True)` 构造 broken symlink，断言 `OSError`，然后断言 `source/state.txt == "source"`、`target.is_symlink()` 为 `True`、`os.readlink(target)` 等于原 link target。✅

**Verdict**: ✅ **已修复** — 生产 guard 覆盖 existing directory 和 broken symlink，测试证明 source/target 均不变。

### R3-C-S1-CR-F02 — direct `_normalize_object_key` test coverage

**Controller required fix**: 在测试中显式导入 `_normalize_object_key`，添加直接 parameterized 合法/非法测试。

**Test fix** (`test_fins_storage_atomicity.py:45, 86-128`):

1. **Import** (:45): `_normalize_object_key` 已在 import 列表中。✅

2. **Valid normalization test** (`test_object_key_owner_normalizes_valid_values`, :86-107):
   - `("AAPL/filings/report.md", "AAPL/filings/report.md")` — identity round-trip ✅
   - `(" BRK.B / reports-2024 / annual.report.pdf ", "BRK.B/reports-2024/annual.report.pdf")` — 逐组件 trim + dot/hyphen 合法内容保留 ✅

3. **Invalid rejection test** (`test_object_key_owner_rejects_invalid_values`, :110-128):
   - 参数化: `""`, `"   "`, `"/absolute"`, `"a//b"`, `"a/../b"`, `"a/./b"`, `"a\\b"`, `"C:/b"` — 覆盖空 key、空白、leading slash、空 segment、`..`/`.` segment、反斜杠、Windows drive 表达。✅
   - 每个都断言 `pytest.raises(ValueError)`。✅

**Verification**: 既有 `LocalFileStore` 间接测试继续保留（`test_local_file_store_rejects_invalid_object_keys_without_external_writes`），owner helper 和 consumer 两层 contract 均有覆盖。✅

**Verdict**: ✅ **已修复** — owner-level 合法/非法参数化测试直接覆�� `_normalize_object_key` 契约。

---

## Scope Boundary Verification

### No new material blocker

fix 仅新增 2 行 guard + 3 个测试函数。未改变任何既有 contract、状态机转换或 caller 行为。guard 在所有既有 caller 路径上均为 no-op（target 不存在时通过）。

### No S2/S3 implementation

- 未修改 S2 allowed files（`docling_upload_service.py`、`ingestion_runtime.py`、`cn_download_*`、`cninfo_downloader.py`、`hkexnews_downloader.py`）
- 未修改 S3 allowed files（`wait_adapter.py`、`host_assembly.py`、`fins_wait_adapter.py`）
- 未修改 Host/Service/Engine 任何文件

### No tool-security implementation

生产代码和测试中无以下关键词命中（通过上一轮 DS review 已确认的 scan）：
- upload allowlist / file authority / symlink-safe upload source policy
- URL / TLS / redirect / SSRF provenance
- remote byte budget
- LLM-facing security schema / prompt / tool schema

broken symlink guard 只保护 storage owner 内部 `os.replace()` 前置条件，不是 upload source authority 或远端 egress policy。该 guard 的 TOCTOU 风险已由 fix artifact 正确分类：仅在持有 ticker batch/recovery lock 的 storage owner 内部调用，不构成外部安全授权边界。

### No regression

fix artifact 报告 `130 passed, 3 warnings`（从上一轮的 118 passed 增加 12 个新测试）。pyright `0 errors, 0 warnings, 0 informations`。

---

## Open Questions

无。

---

## Residual Risk

| Risk | Classification | Owner / destination |
| --- | --- | --- |
| `target.exists() or target.is_symlink()` 与 `os.replace()` 之间 TOCTOU | accepted — `_replace_directory` 仅在持有 ticker batch/recovery lock 的 storage owner 内部调用，不存在并发 caller | 当前实现；fix artifact 已记录 |
| S2/S3 未实施 | covered by later approved slices | mandatory R3-C S2 / R3-C S3 |
| 四类 tool-security | assigned to later work unit | dedicated tool-security / remote-egress WU |

---

## Re-Review Conclusion

**Status: pass**

**Findings count: 0**（全部 2 个 accepted findings 已正确修复）

**Completion report:**

- **status**: pass
- **artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-c-s1-code-review-rereview-ds.md`
- **fixed findings count**: 2
- **remaining findings count**: 0
- **new findings count**: 0
- **blocking questions count**: 0
