# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-G S3

## Scope

- Mode: current changes (unstaged)
- Branch: `phaseflow/host-issues-control`
- Slice: P3-G S3 — Typed SEC download rejection registry
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-s3-code-review-ds.md`
- Included scope: 15 files (+338/-74)
- Validation: `pytest` 87 passed (storage/pipeline) + 1 passed (ingestion), `pyright` 0 errors

## Verdict

**PASS** — 无 material finding。S3 正确将 SEC 下载拒绝注册表从 `dict[str, dict[str, str]]` 隐藏 shape 改为 typed `DownloadRejectionEntry` / `DownloadRejectionRegistry` contract。Repository、pipeline、SC13 过滤、诊断和 ingestion runtime 全部消费同一 typed registry。旧 dict shape 仅在 filesystem 写 JSON 前的局部序列化变量中残留，非 public contract。

---

## Findings

未发现实质性问题。

---

## Review Focus 逐项核实

### 1. Owner Boundary: 产生 → 校验 → 持久化 → 消费

| 阶段 | Owner | 实现 | 证据 |
| --- | --- | --- | --- |
| 产生 | `sec_download_state._record_rejection` / `ingestion_runtime` | 构造 `DownloadRejectionEntry(...)`（`@dataclass(frozen=True)` → `__post_init__` 校验必填字段 + canonical SEC form） | `sec_download_state.py:148`, `ingestion_runtime.py:3908` |
| 校验 | `DownloadRejectionEntry.__post_init__` + `from_dict` | 6 个必填字段非空校验 + `parse_sec_form_type` canonical form + `expected_document_id` 与 registry key 一致性 | `document_models.py:201-226`, `:229-260` |
| 持久化 | `FilingMaintenanceRepositoryProtocol` → `_fs_maintenance_core` | load: 坏条目 fail closed（`ValueError`）；save: key/document_id 一致性 + `entry.to_dict()` | `_fs_maintenance_core.py:34-65`, `:91-113` |
| 消费 | SC13 filtering, SEC pipeline, diagnostics, download workflow | 全部通过 `DownloadRejectionRegistry` typed 映射 | `sec_sc13_filtering.py` (7 处), `sec_pipeline.py` (5 处), `sec_download_diagnostics.py`, `sec_download_state.py` |

### 2. 无旧 `dict[str, dict[str, str]]` public contract 残留

```bash
rg -n "dict\[str, dict\[str, str\]\]" dayu/fins/pipelines/... dayu/fins/storage/
```

**唯一命中**: `_fs_maintenance_core.py:111` — `payload: dict[str, dict[str, str]] = {}`

分类：这是 `_save_download_rejection_registry_impl` 内部的局部序列化变量，在 `entry.to_dict()` 循环后传给 `_write_json(path, payload)`。不是 public contract、不是 protocol signature、不是 pipeline 参数。保存入口参数已是 `DownloadRejectionRegistry`，且在写入前校验 key/document_id 一致性。✅

**SC13 filtering 全部 7 处签名**已从 `Optional[dict[str, dict[str, str]]]` 改为 `Optional[DownloadRejectionRegistry]`。✅

### 3. Repository load 对坏 registry 失败关闭

旧行为（已删除）：
```python
try:
    data = _read_json_object(path)
except (ValueError, OSError):
    return {}  # 静默吞错
...
if not isinstance(document_id, str) or not isinstance(payload, dict):
    continue  # 跳过坏条目
normalized_payload[key] = str(value)  # 静默 coercion
```

新行为：
- JSON 解析失败 → `_read_json_object` 抛异常直接传播（不再被吞）
- 条目非 `(str, dict)` 映射 → `ValueError("download rejection registry 条目必须是...")`
- 条目字段缺失/类型非法/空值 → `_required_json_string` / `parse_sec_form_type` 抛 `KeyError` / `ValueError`
- registry key 与 `document_id` 不一致 → `ValueError("download rejection document_id 与 registry key 不一致")`

**Fail closed 正确**：坏 durable state 不再被静默吞掉。✅

### 4. `ingestion_runtime.py` rejected artifact 路径语义完整

Ingestion runtime 的 `test_start_download_persists_rejected_filing_artifact` 测试验证：rejected artifact 路径构造 `DownloadRejectionEntry` 并写入 typed registry。该路径使用自己的 `rejection_classification_version` 作为 `download_version`（非 SEC pipeline version），保持 producer-owned version 语义。✅

### 5. SC13、SEC skip、诊断全部从同一 typed registry 派生

| Consumer | 读取方式 | 证据 |
| --- | --- | --- |
| `_is_rejected` (skip 判断) | `entry.download_version` 与当前 version 比较 | `sec_download_state.py:91` |
| `_record_rejection` (写入) | 构造 `DownloadRejectionEntry(...)` | `sec_download_state.py:148` |
| `warn_insufficient_filings` (诊断) | `entry.form_type` 统计 6-K filtered | `sec_download_diagnostics.py:45` |
| SC13 filtering | 传递 `DownloadRejectionRegistry` 不做 dict 解析 | `sec_sc13_filtering.py` 全部 7 处签名 |
| SEC pipeline facade | 传递 typed registry 不做 dict 解析 | `sec_pipeline.py` 全部 5 处签名 |

无 "显示正确但持久化错误" 或 "trace/summary 使用 dict 字段猜测" 的情况。✅

### 6. `DownloadRejectionEntry` 设计审查

| 检查项 | 状态 |
| --- | --- |
| `@dataclass(frozen=True)` — 不可变 | ✅ |
| `__post_init__` 校验 6 个必填字段非空 + canonical SEC form | ✅ 行 201-226 |
| `from_dict` + `expected_document_id` 一致性校验 | ✅ 行 229-260 |
| `to_dict` 返回 `dict[str, str]` — 类型窄化 | ✅ 行 262-282 |
| 字段命名与旧 dict key 兼容 | ✅ `document_id`, `reason`, `category`, `form_type`, `filing_date`, `download_version` |
| `DownloadRejectionRegistry = dict[str, DownloadRejectionEntry]` — TypeAlias | ✅ 行 285 |

### 7. S3 未越界到其他 Slice

| Slice | 行为 | S3 状态 |
| --- | --- | --- |
| S1 SEC form parser | `parse_sec_form_type` 复用（在 `from_dict` 和 `__post_init__` 中） | ✅ 复用 domain truth |
| S2 CN/HK report selection | — | ❌ 未触碰 |
| S4 XBRL total | — | ❌ 未实现 |
| LLM-facing schema/prompt | — | ❌ 未修改 |

---

## Adversarial Failure Pass

- **registry JSON 文件不存在**: 返回空 `DownloadRejectionRegistry` — ✅ (路径: `path.exists() → return {}`)
- **registry JSON 非法（非 object/array）**: `_read_json_object` 抛异常传播 — ✅ fail closed
- **registry 条目非 `(str, dict)` 映射**: `ValueError` 抛出 — ✅ fail closed
- **条目 `document_id` 与 registry key 不一致**: `ValueError` 在 load 和 save 时均校验 — ✅
- **条目字段类型非法（如 `form_type` 为 `int`）**: `_required_json_string` 抛 `ValueError` — ✅
- **条目 `form_type` 不是 canonical SEC form**: `parse_sec_form_type` 抛 `ValueError` — ✅
- **直接构造 `DownloadRejectionEntry` 绕过 `from_dict`**: `__post_init__` 仍触发校验（`@dataclass` 自动调用）— ✅
- **save 时 `payload` 局部变量仍是 `dict[str, dict[str, str]]`**: 这是序列化边界——`entry.to_dict()` 产生的 typed 值装入 `payload`。如果 `to_dict` 返回的 dict shape 变化，pyright 会在 `_write_json(path, payload)` 处报类型错误。✅

---

## Test Coverage

| 测试 | 覆盖 |
| --- | --- |
| `test_fins_storage_provider.py` | typed registry roundtrip、坏字段 fail closed、key/document_id 冲突保存失败 |
| `test_sec_pipeline_download.py` | `_record_rejection` / `_is_rejected` typed 写入/读取、版本匹配、overwrite、6-K filter 场景 |
| `test_fins_ingestion_runtime.py::test_start_download_persists_rejected_filing_artifact` | ingestion runtime rejected artifact → typed registry 写入 |

---

## Residual Risk

- **旧 workspace `_download_rejections.json` 兼容**: 缺少 `document_id` 或字段类型不合法的旧 registry 现在会 fail closed。S3 未做迁移兼容——按项目编码约束和 plan non-goal 接受。
- **`ingestion_runtime.py` 使用自有 `rejection_classification_version`**: 该路径的 `download_version` 不是 SEC pipeline version。语义正确——version 由 producer 拥有。
- **无 coverage 百分比**: `DownloadRejectionEntry` 放在 `document_models.py`（既有宽模块），未单独对宽文件测 coverage。changed-boundary tests 覆盖了新增 model、repository decode/encode、pipeline helper 和 ingestion runtime 路径。
