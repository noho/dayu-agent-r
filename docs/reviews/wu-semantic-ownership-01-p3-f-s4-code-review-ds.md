# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-F S4

## Scope

- Mode: current changes (unstaged + uncommitted, since `edf303a4`)
- Branch: `phaseflow/host-issues-control`
- Base commit: `edf303a4` (P3-F S3 completion)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-s4-code-review-ds.md`
- Included scope: 5 files (+303/-4)
- Excluded scope: untracked files per handoff
- Parallel review coverage: 无

## Verdict

**PASS** — S4 正确将 upload company meta freshness 从"文件存在即是 fresh"改为 `resolver_version` 真源。无 material defect，无 owner boundary 违规，无 TTL 冒充 freshness。

---

## Findings

未发现实质性问题。

---

## Review Focus 逐项核实

### 1. Upload company meta freshness must be resolver-version based

`_existing_company_meta_is_fresh`（`upload_company_meta.py:178-192`）的判定逻辑仅比较 `resolver_version`：

```python
return existing_meta.resolver_version == resolver_version
```

- 不检查 `updated_at`、不检查 ticker alias 相似度、不检查文件存在性
- `RESOLVER_VERSION = "market_resolver_v1.0.0"` 是模块级 `Final` 常量（行 17），ownership 明确

### 2. Same-version existing meta preserves existing repository values

`upsert_company_meta_for_upload`（行 53-62）在 `existing_meta` 存在且 fresh 时：
- 调用 `_warn_ignored_company_meta_args` 记录忽略告警
- 直接 `return`，不调用 `repository.upsert_company_meta`

测试 `test_upload_filing_stream_preserves_same_version_company_meta` 验证：
- 预种 `company_name="Existing Apple"` + `resolver_version=RESOLVER_VERSION` + `ticker_aliases=["AAPL", "OLD"]`
- 上传传入 `company_name="Ignored Apple"` + `ticker_aliases=["AAPL", "NEW"]`
- 结果：仓储中仍为 `"Existing Apple"` + `["AAPL", "OLD"]`

### 3. Stale version refreshes from current upload fields

当 `_existing_company_meta_is_fresh` 返回 `False`（版本不匹配），代码落入 normalization + upsert 路径（行 64-84）：
- `normalize_ticker(ticker)` → 重新推导 company_id / market
- `_require_company_meta_field(company_name, ...)` → 校验非空
- `repository.upsert_company_meta(CompanyMeta(resolver_version=RESOLVER_VERSION, ...))` → 写入当前版本

测试覆盖：
- SEC: `test_upload_filing_stream_refreshes_stale_company_meta` — 旧版本 `"market_resolver_v0.9.0"` + `"Stale Apple"` → 刷新为 `"Apple Refreshed"` + `RESOLVER_VERSION`
- CN: `test_upload_filing_stream_refreshes_stale_company_meta` — 旧版本 `"market_resolver_v0.9.0"` + `"旧贵州茅台"` → 刷新为 `"贵州茅台"` + `RESOLVER_VERSION`

### 4. Stale version without company name fails closed

当旧版本 meta 存在但上传未提供 `company_name` 时：
- `_existing_company_meta_is_fresh` → `False`（版本不匹配）
- `_require_company_meta_field(value=None, option_name="--company-name")` → `ValueError`
- 异常在 `repository.upsert_company_meta` 调用之前抛出
- 仓储中旧 meta 不被改写

测试 `test_upload_filing_stream_stale_company_meta_requires_company_name` 验证：
- 上传事件序列：`[UPLOAD_STARTED, UPLOAD_FAILED]`
- `failed_result["status"] == "failed"`，消息包含 `"--company-name"`
- 仓储中 `company_name` 仍为 `"Stale Apple"`，`resolver_version` 仍为旧版本

### 5. `updated_at` does not become freshness TTL

- `updated_at` 仅在 upsert 路径中设为 `now_iso8601()`（行 81），作为审计时间
- `_existing_company_meta_is_fresh` 不读取 `updated_at`
- 无任何路径基于 `updated_at` 年龄判定 staleness

### 6. SEC/CN download producer paths not routed through upload freshness

- `upsert_company_meta_for_upload` 仅被 upload filing/material stream 调用（SEC `upload_filing_stream`、CN `upload_filing_stream`、upload material stream）
- SEC download 路径（`sec_download_filing_workflow` → `upsert_downloaded_filing_source_document`）写入自己的 company meta，不经过 `upsert_company_meta_for_upload`
- CN download 路径同理

### 7. Read runtime does not infer/refresh company metadata

- `FinsReadRuntime._read_company_info`（`read_runtime.py:1859-1876`）仅调用 `self._company_repository.get_company_meta(ticker)`
- 无 `resolver_version` 检查、无 `updated_at` 年龄判定、无 refresh 逻辑
- `FileNotFoundError` 时返回 `(ticker, "unknown")` fallback — 不做推断

---

## Owner Boundary Assessment

| 边界 | Owner | S4 实现 | 证据 |
| --- | --- | --- | --- |
| Freshness truth | `upload_company_meta.py` → `RESOLVER_VERSION` | `_existing_company_meta_is_fresh` 仅比较 resolver 版本 | `upload_company_meta.py:178-192` |
| 同版本保留 | upload company meta helper | `existing_meta is not None and fresh` → early return | `upload_company_meta.py:53-62` |
| 旧版本刷新 | upload company meta helper | fresh=False → normalization + upsert | `upload_company_meta.py:64-84` |
| 缺失必填字段 fail-closed | upload company meta helper | `_require_company_meta_field` 在 upsert 前 | `upload_company_meta.py:66-69` |
| 持久化 | `CompanyMetaRepositoryProtocol` | `repository.upsert_company_meta(CompanyMeta(...))` | `upload_company_meta.py:74-84` |
| `updated_at` 仅为审计时间 | upload company meta helper | 仅写入 `now_iso8601()`，不读取 | `upload_company_meta.py:81` |
| Download producer | 各自 producer（不在 S4 scope） | SEC/CN download 路径不经过 `upsert_company_meta_for_upload` | 代码路径独立 |
| Read runtime | 只读 repository | `_read_company_info` → `get_company_meta` only | `read_runtime.py:1873` |

## Propagation Audit

1. **Producer**: upload entry → `upsert_company_meta_for_upload(repository, ticker, action, company_name, ...)`
2. **Freshness judgment**: `_load_existing_company_meta` → `_existing_company_meta_is_fresh(existing_meta, RESOLVER_VERSION)`
3. **Fresh path**: warn + return（保留仓储值）
4. **Stale/missing path**: `normalize_ticker` → `ticker_to_company_id` → `_require_company_meta_field` → `repository.upsert_company_meta(CompanyMeta(resolver_version=RESOLVER_VERSION, ...))`
5. **Persistence**: `CompanyMeta` 写入 repository，`resolver_version=RESOLVER_VERSION`
6. **Read projection**: `FinsReadRuntime._read_company_info` 读取 repository → `company_name` / `market` → LLM-facing output

结论：freshness 从 upload owner 单源派生，一条链路到底，无分支、无 fallback、无下游推断。

## Adversarial Failure Pass

- **`existing_meta.resolver_version` 缺失**: `CompanyMeta` dataclass 字段为 `str`（非 Optional），`from_dict` 对缺失字段抛 `KeyError`。不可能进入 comparison。✅
- **`RESOLVER_VERSION` 被外部改写**: `Final[str]` 类型标注 + 模块级常量，改写需要修改源码（属于 planned version bump）。✅
- **CN 路径 `ticker_aliases` 非空但未提供 `company_name`**: 同 SEC 路径——`_require_company_meta_field` 抛 `ValueError`。✅
- **Upload 路径同时提供 `company_id` 参数**: `company_id` 不被用作 freshness 判定（仅 `resolver_version` 参与）；upsert 路径中 `company_id` 由 `ticker_to_company_id(profile)` 重新推导，传入的 `company_id` 仅在 warn 消息中使用。✅
- **`_warn_ignored_company_meta_args` 在 `company_id` 和 `company_name` 均为空时不记录告警**: `normalized_company_id` 和 `normalized_company_name` 均为空字符串时 early return（行 217）。合理——无参数被忽略时不产生噪音日志。✅

## Test Coverage

| 测试 | 场景 | 断言 |
| --- | --- | --- |
| `test_upload_filing_stream_preserves_same_version_company_meta` | 同版本保留 | company_name/ticker_aliases/resolver_version 不变 |
| `test_upload_filing_stream_refreshes_stale_company_meta` (SEC) | 旧版本刷新 | company_name/ticker_aliases/resolver_version 均更新 |
| `test_upload_filing_stream_stale_company_meta_requires_company_name` | 旧版本缺 company_name fail-closed | 上传失败 + 仓储旧值保留 |
| `test_upload_filing_stream_refreshes_stale_company_meta` (CN) | CN upload facade 刷新旧版本 | company_id/company_name/resolver_version/ticker_aliases 均更新 |

## Open Questions

无。

## Residual Risk

- **Read runtime 无专项 freshness 测试**: 当前代码证据显示 `_read_company_info` 仅读取 repository，不做刷新或推断。S4 未新增 read runtime 测试，依赖既有 read 测试覆盖和直接代码审查确认。
- **Download producer freshness 仍在 S4 scope 外**: SEC/CN/HK 下载路径各自写入 company meta，不经过 upload freshness。Plan 将其标记为 producer-owned refresh，不属于 P3-F scope。
- **`RESOLVER_VERSION` 变更规则**: 当前 plan 定义 `RESOLVER_VERSION` 只在 upload company identity normalization 或 required-field 语义变更时修改。版本号 bump 是人工决策，无自动化触发机制。
