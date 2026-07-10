# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-F S4

## Scope

- Mode: current changes (unstaged workspace diff since `edf303a4`)
- Branch: `phaseflow/host-issues-control`
- Base: `edf303a4` (S3 accepted commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-s4-code-review-mimo.md`
- Included scope: 5 files (+303/-4) — S4 company metadata freshness semantics
- Excluded scope: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`, `docs/host/issues-implementation-control.md`
- Parallel review coverage: 无

## Findings

未发现实质性问题。

逐项检查：

### Resolver-version freshness 判定

`_existing_company_meta_is_fresh(...)` (`upload_company_meta.py:178-192`) 仅比较 `existing_meta.resolver_version == resolver_version`。`RESOLVER_VERSION` 是模块级 `Final[str]` 常量（line 17: `"market_resolver_v1.0.0"`），由 `upload_company_meta` 模块拥有。不读取 `updated_at`、wall-clock time、外部 market-data recency 或 release metadata。

### 同版本既有 meta 保留

`upsert_company_meta_for_upload(...)` line 53-62：当 `existing_meta is not None` 且 `_existing_company_meta_is_fresh(...)` 返回 `True` 时，调用 `_warn_ignored_company_meta_args(...)` 记录忽略告警后 `return`。不重写仓储，保留既有 `CompanyMeta` 值。

### 旧版本既有 meta 刷新

当 `_existing_company_meta_is_fresh(...)` 返回 `False` 时，代码 fall through 到 line 64-84：`normalize_ticker` → `ticker_to_company_id` → `_require_company_meta_field(company_name)` → `_normalize_ticker_aliases` → `repository.upsert_company_meta(...)`。使用当前上传字段重新校验并写入，`resolver_version=RESOLVER_VERSION`。

### 旧版本缺少 company_name 时 fail closed

`_require_company_meta_field(value=company_name, option_name="--company-name")` (line 66-69) 在 `company_name` 为空时抛出 `ValueError("create/update 时必须提供 --company-name")`。不复用 stale 数据，不改写旧仓储值。测试 `test_upload_filing_stream_stale_company_meta_requires_company_name` 验证：失败事件包含 `"--company-name"`，旧 meta 的 `company_name` 和 `resolver_version` 保持不变。

### `updated_at` 不是 freshness TTL

`upsert_company_meta_for_upload` 在写入新 meta 时使用 `updated_at=now_iso8601()` (line 81)，这是审计时间。freshness 判定只看 `resolver_version`，不看 `updated_at`。

### SEC/CN download 路径不受影响

diff 只修改 `upload_company_meta.py` 和 upload 测试。SEC/CN/HK 下载路径的 company meta 写入仍由各自 producer-owned 路径处理，不经过 upload freshness helper。

### Read runtime 不推断 freshness

`FinsReadRuntime._read_company_info(...)` 只读取 repository meta 的 `company_name` 和 `market`，不执行 refresh 或 freshness 推断。implementation report 和 controller validation 均确认此点。

### 测试覆盖

| 测试 | 场景 | 断言 |
|---|---|---|
| `test_upload_filing_stream_preserves_same_version_company_meta` | 同版本既有 meta | `company_name == "Existing Apple"`, `ticker_aliases == ["AAPL", "OLD"]` |
| `test_upload_filing_stream_refreshes_stale_company_meta` | 旧版本既有 meta | `company_name == "Apple Refreshed"`, `resolver_version == RESOLVER_VERSION` |
| `test_upload_filing_stream_stale_company_meta_requires_company_name` | 旧版本 + 缺 company_name | `UPLOAD_FAILED`, `"--company-name"` in message, 旧 meta 不变 |
| `test_upload_filing_stream_refreshes_stale_company_meta` (CN) | CN 旧版本刷新 | `company_name == "贵州茅台"`, `resolver_version == RESOLVER_VERSION` |

### README 更新

`dayu/fins/README.md` 增加一段：upload company meta freshness owner、`updated_at` 非 TTL、下载路径和 read runtime 边界。内容在 `dayu/fins/` Agent update constraints 范围内。

## Owner Boundary 评估

| 检查项 | 状态 | 证据 |
|---|---|---|
| Upload freshness 由 resolver version 决定 | ✅ | `_existing_company_meta_is_fresh` 比较 `resolver_version` |
| 同版本保留既有值 | ✅ | line 53-62 early return |
| 旧版本用当前字段刷新 | ✅ | line 64-84 normalize + upsert |
| 旧版本缺 company_name fail closed | ✅ | `_require_company_meta_field` 抛 `ValueError` |
| `updated_at` 不是 TTL | ✅ | freshness 判定不读 `updated_at` |
| SEC/CN download 不经 upload freshness | ✅ | diff 未修改下载路径 |
| Read runtime 不推断 freshness | ✅ | `_read_company_info` 只读 repository |
| `RESOLVER_VERSION` 由 upload meta 模块拥有 | ✅ | `Final[str]` 常量，不从外部读取 |

## Validation

- `pytest tests/fins/test_upload_batch.py tests/fins/test_sec_pipeline_upload_filing_stream.py tests/fins/test_sec_pipeline_upload_material_stream.py tests/fins/test_cn_pipeline.py -q`: **24 passed, 3 warnings**
- `pyright dayu/fins/pipelines/upload_company_meta.py`: **0 errors**
- `git diff --check`: passed

## Residual Risk

- **无 read runtime 专项测试**: 代码证据确认 `_read_company_info(...)` 只读 repository meta，不执行 refresh。本次测试覆盖 upload owner 写入边界。
- **SEC/CN/HK download producer freshness 不在 S4 scope**: 下载路径的 company meta 写入仍由各自 producer 处理。
- **Coverage 未测量**: pytest-cov 本地 numpy/pandas import 问题仍存在。

## Verdict

**PASS** — S4 实现正确执行了 plan 中的 company metadata freshness semantics。resolver-version freshness 判定、同版本保留、旧版本刷新、缺字段 fail closed、`updated_at` 非 TTL、下载路径隔离和 read runtime 边界均符合 owner boundary 设计。未发现 material defects。
