# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S3 Code Re-Review (AgentDS)

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S3 — Fiscal And Normalization Owners, SEC Version Alignment, Docs And Aggregate Closure`
- Gate: code re-review (fix verification)
- Agent: `AgentDS`
- Scope: 仅复核 controller accepted finding `R3-D-S3-CR-F01` 的 fix
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-fix-codex.md`
- Original DS review: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-code-review-ds.md`
- Re-review artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-rereview-ds.md`

## Scope Confirmation

- 仅复核 `dayu/fins/processors/sec_xbrl_query.py` 中 `_to_optional_float(...)` 的 `except Exception` → `except (TypeError, ValueError)` fix。
- 不重新做全量 S3 review；不 review R3-E/tool-security。
- 本文件内其余 S3 实现变更（`_normalize_optional_string` → `normalize_optional_dataframe_string` 迁移）属于 accepted S3 scope 的语义所有权收束，不在本次复核范围内；仅检查其是否引入与 F01 相关的新 material issue。

## Finding Status

### R3-D-S3-CR-F01：已修复

- **入口/函数**: `_to_optional_float` (line 307)
- **文件(行号)**: `dayu/fins/processors/sec_xbrl_query.py:326`
- **修复内容**: `except Exception` → `except (TypeError, ValueError)`
- **直接证据**:
  - 当前代码 line 326: `except (TypeError, ValueError):`
  - `float(value)` 在内置转换中仅可能抛出 `TypeError`（不支持的类型，如 list/dict）和 `ValueError`（不可解析的字符串，如 `"abc"`）
  - 修复后：普通 `float(...)` 转换失败仍返回 `None`（行为不变）；其它异常（`MemoryError`、`KeyboardInterrupt`、`AttributeError` 等）不再被静默吞掉
- **调用方验证**:
  - `_build_statement_rows` (line 181): `_to_optional_float(row.get(period))` — 期望 `Optional[float]`，行为不变
  - `_extract_numeric_fact_value` (line 693, 696): `_to_optional_float(row.get("numeric_value"))` / `_to_optional_float(row.get("value"))` — 期望 `Optional[float]`，行为不变
  - 所有调用方仅消费 `Optional[float]` 返回值，不受异常捕获范围收窄影响
- **修复风险**: 低。仅收窄异常捕获范围，不改变返回值语义或调用契约。
- **状态**: **已修复**

## New Findings

### 无新 material issue

对本文件 fix diff 及 `_to_optional_float` 相关调用链做 adversarial failure pass 后，未发现新引入的 material issue。

**复核覆盖的检查项**（均通过）：

| 检查项 | 结果 |
| --- | --- |
| `float(value)` 可抛异常是否被完整覆盖 | 是。`TypeError` + `ValueError` 覆盖了 `float()` 所有文档化异常 |
| 返回值语义是否改变 | 否。仍为 `Optional[float]`，转换失败返回 `None` |
| 调用方是否受影响 | 否。三处调用方均只消费 `Optional[float]` |
| 是否引入新 `except Exception` | 否 |
| 是否引入 fallback / compat shim / loose parsing | 否 |
| 是否修改 R3-E / Host / Engine / tool-security 文件 | 否 |

**次要观察（不构成 finding）**：

- `_to_optional_float` 的 docstring（line 317）写 `Raises: ValueError: 转换失败时抛出。`，但函数实际不再 raise `ValueError`（已被捕获）。这是 **fix 之前即存在的 docstring 不准确问题**，非本次 fix 引入，严重度不足以单独列为 finding。建议在后续 docstring 清理工作中修正为 `Raises: 无。` 或删除该行。

## Open Questions

无。

## Residual Risk

- 本文件中其余 5 处 `except Exception` 模式（`_infer_xbrl_taxonomy:101`、`_query_facts_rows:494`、`_infer_units_from_xbrl_query:736`、`_infer_scale_from_xbrl_query:794`、`_infer_period_semantics_from_xbrl_query:834`）属于 XBRL query probe-and-fallback 语义（"尝试此 concept，任何失败则跳过"），与 `_to_optional_float` 的值转换语义不同。这些未被 controller 纳入本次 fix scope，其所有权判定留待后续 work unit。
- 其余 residual risk 与 controller adjudication 记录一致，无新增项。
