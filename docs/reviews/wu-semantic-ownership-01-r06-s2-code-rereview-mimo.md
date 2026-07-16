# WU-SEMANTIC-OWNERSHIP-01 / R06-S2 Cumulative S1+S2 Code Re-Review（AgentMiMo）

## 1. Gate 身份与结论

- work unit：继续同一 umbrella `WU-SEMANTIC-OWNERSHIP-01 / R06-S2`，不是新 WU，不进入 S3。
- gate：code re-review，验证 `R06-S2-CR-F01` 修复后 S1+S2 累计 working tree 无回归。
- base：`d048adf7ec1135aaf575384432ebf1137f8a34f2`（Controller transition base）到当前 working tree。
- scope：accepted R06-S1+S2 owner scope；S3 producer/test propagation、full pyright 108、ack residual、README final contract 均为 accepted R06-S3 residual，不在本 gate 裁决范围。
- artifact：`docs/reviews/wu-semantic-ownership-01-r06-s2-code-rereview-mimo.md`。

**最终裁决：PASS / 0 material findings / 0 blocking questions**

## 2. 必须显式核验的四项

### 2.1 R06-S2-CR-F01：`_resolve_primary_uri` 唯一 owner 关闭

**结论：CLOSED**

直接代码证据（`_fs_storage_utils.py:396-416`）：

```python
def _resolve_primary_uri(file_payloads, primary_name):
    if not primary_name:
        return None
    for item in file_payloads:
        name = str(item.get("name") or _infer_filename_from_uri(item.get("uri", ""))).strip()
        if name == primary_name:
            return str(item.get("uri"))
    return None
```

- `primary_name` 缺失 → `None`（入口 guard）；
- `primary_name` 非空且精确命中 entry canonical name → 保留该 entry URI；
- `primary_name` 非空但未精确命中 → `None`（迭代结束自然返回）；
- 无 first-file fallback（`file_payloads[0]` 扫描为 0）；
- 两个 production caller（`_upsert_source_document` line 1340、`_toggle_source_deleted` line 1416）均未增加补偿分支；
- commit validator（`_validate_complete_source_directory` line 648）独立要求 `primary_document` 精确命中 files，不放宽。

精确扫描确认：`grep -n 'file_payloads\[0\]' dayu/fins/storage/_fs_storage_utils.py` → 0 命中。

### 2.2 R06-S1-CR-F01..03 与所有 S1 validation findings 保持关闭

**结论：全部 CLOSED，未回归**

| Finding | 关闭证据 |
|---------|---------|
| CR-F01（maintenance public read → private unguarded helper） | `_fs_maintenance_core.py` 保持 outer guard + private unguarded graph，无 public-to-public self-call |
| CR-F02（processed meta docstring 删除虚构 fallback） | `_fs_processed_core.py` 只承诺和读取 published `tool_snapshot_meta.json`，无 fallback |
| CR-F03（mark_processed_reprocess_required 统一 `-> None`） | protocol/wrapper/impl 返回语义统一为 `None`，`required=False` 为 no-op |

S2 implementation 未修改以上三个 owner 边界的任何文件路径（`_fs_maintenance_core.py`、`_fs_processed_core.py` processed meta 读取、`mark_processed_reprocess_required`）。S2-CR-F01 的 fix 只修改 `_fs_storage_utils.py` 一个文件，不涉及 S1 findings。

### 2.3 S2 六项核心能力无回归

| 能力 | 状态 | 直接证据 |
|------|------|---------|
| blob-first staging | PASS | `_FsBlobMixin.store_file` 对 `SourceHandle` 只校验 active batch + ticker + containment，不要求 meta 存在 |
| final complete source | PASS | `_prepare_complete_source_meta` 强制 `ingest_complete=True`，显式 false 当场 `ValueError` |
| prepublication validator | PASS | `_validate_complete_source_tree` 在 publication guard 前遍历完整 staged ticker tree，22-case failure grid 全通过 |
| failure token consumption | PASS | validator failure → precommit rollback → token 消费；22-case grid 每格都验证二次 rollback 被拒绝 |
| old preservation | PASS | old-absent/new-source 格断言 published source IDs 为空、meta/blob 不可见；old-present 格断言旧 source ID/bytes 不变 |
| reader barrier | PASS | `commit_batch` publication guard 与 writer mutex 严格分离；validator barrier reader test 在 1 秒 deadline 内读到 old |

### 2.4 无越界实现

| 扫描项 | 结果 | 说明 |
|--------|------|------|
| ambient authority | 0 | storage/tests 无 ContextVar、task/thread identity、auto-batch 第二 authority |
| first-file fallback | 0 | `_resolve_primary_uri` 与 `_get_primary_file_unguarded` 均无 `file_payloads[0]` 猜测 |
| compat shim | 0 | 无 `hasattr`/`getattr`、无兼容 wrapper、无 consumer 反推 |
| 统一 authorization | 0 | 未实施 Issue 142/151/175/177/178 的统一 tool authorization framework |
| storage ack residual | 0 | `dayu/fins/storage` 中 `stage_source_document`、stable fields、ack、false completion 残留清零 |
| `setdefault(primary/completion)` | 0 | source mutation owner 未增加默认 primary 或 completion 补偿 |

## 3. Observations（非 findings）

### O-01 — commit_batch publication guard release unreachable `else` 分支

- 文件：`_fs_storage_infra.py:379-380`
- 严重程度：信息级（dead code，不影响运行时行为）
- S2 初始 review 已记录，本次确认未改变

### O-02 — `_prepare_complete_source_meta` 对缺失 `ingest_complete` 默认 `True`

- 文件：`_fs_source_document_core.py:1447`
- 严重程度：信息级（owner contract 内的合理默认，commit validator 双层校验）
- S2 初始 review 已记录，本次确认未改变

### O-03 — S3 producer 仍调用 `stage_source_document` / 设置 `ingest_complete=False`

- 严重程度：信息级（accepted S3 residual，不在 S2 边界）
- full pyright 108 errors 精确归属 S3 propagation

### O-04 — validator 6 个独立失败分支未被 22-case grid 覆盖

- 严重程度：信息级（test gap，可在 S2/S3 间补充）
- S2 初始 review 已记录，本次确认未改变

### O-05 — 测试通过 `_active_batches` private 字段获取物理路径

- 严重程度：信息级（tech debt，S1 O-03/O-04 同类模式）
- S2 初始 review 已记录，本次确认未改变

## 4. 测试与验证

所有命令均在 `source .venv/bin/activate` 后执行。

### 4.1 四文件累计 S1/S2 allowlist tests

```
235 passed, 3 warnings in 9.46s
```

三条 warning 均为既有 `edgar` deprecation warning。

### 4.2 Scoped pyright（9 production files）

```
0 errors, 0 warnings, 0 informations
```

### 4.3 Scoped Ruff（9 production + 4 test files）

```
All checks passed!
```

### 4.4 `git diff --check`

通过，exit=0。

### 4.5 Exact scans 汇总

| Scan | Result | Attribution |
| --- | ---: | --- |
| `file_payloads[0]` primary fallback | 0 | 唯一 owner 已删除 first-file 猜测 |
| `stage_source_document` in storage | 0 | S2 已从 protocol/wrapper/core 删除 |
| `hasattr`/`getattr` in storage | 0 | 无兼容分支 |
| `setdefault(primary/completion)` in source core | 0 | 无默认 primary 或 completion 补偿 |
| ambient authority | 0 | 无 ContextVar/task/thread/auto-batch authority |
| `git diff --check` | pass | 无 whitespace error |

## 5. Residual risks（不阻塞当前 gate）

1. **S3 propagation residual**：full pyright 108 errors、`stage_source_document` 调用残留、`ingest_complete=False` 设置残留精确归属 accepted S3 producer propagation，不在 S2 边界。
2. **README 旧叙述**：仍描述 pre-cutover acknowledgement，有意保留到 S3/final cumulative tree。
3. **validator 6 个未覆盖分支**：代码逻辑正确但测试未直接覆盖，可在后续补充。
4. **R07 snapshot/revision**：跨多个 repository call 或长生命周期 processor 的同版本 snapshot 仍由 R07 独占。

## 6. Verdict

**PASS / 0 material findings / 0 blocking questions**

### Finding 状态

| Finding | 状态 |
|---------|------|
| R06-S2-CR-F01 | **CLOSED**（fix 已在唯一 owner 生效，无回归） |
| R06-S1-CR-F01 | **CLOSED**（未回退） |
| R06-S1-CR-F02 | **CLOSED**（未回退） |
| R06-S1-CR-F03 | **CLOSED**（未回退） |

### 逐维度裁决

| 审查维度 | 结果 |
|---------|------|
| `_resolve_primary_uri` 唯一 owner 关闭 | PASS：missing/mismatch → None、exact hit 保留、无 caller/validator 补偿 |
| S1 findings 保持关闭 | PASS：CR-F01..03 全部 CLOSED，未被 S2/S2-fix 回退 |
| blob-first / final-source / prepublication validator | PASS：无回归 |
| failure token consumption / old preservation / reader barrier | PASS：无回归 |
| ambient authority / first-file fallback / compat shim | PASS：扫描全部为 0 |
| 统一 authorization / Issue 142/151/175/177/178 | PASS：未越界实施 |
| S3/R07 residual 越界 | PASS：108 pyright errors 精确归属 S3；未实施 R07 |
| 测试覆盖 owner contract | PASS：235 passed；有 observations 但无 material gap |
