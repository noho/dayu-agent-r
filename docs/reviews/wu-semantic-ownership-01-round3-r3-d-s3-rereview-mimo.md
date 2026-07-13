# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S3 Code Re-Review (MiMo)

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S3 — Fiscal And Normalization Owners, SEC Version Alignment, Docs And Aggregate Closure`
- Gate: code re-review (post-fix)
- Reviewer: AgentMiMo
- Review date: 2026-07-13
- Scope: only `R3-D-S3-CR-F01` fix verification; not a full S3 re-review
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-code-review-controller-adjudication.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-fix-codex.md`

## Finding Re-Review

### R3-D-S3-CR-F01：`_to_optional_float(...)` 宽泛 `except Exception`

**Controller decision:** accepted / low severity
**Required fix:** Narrow `except Exception` to `except (TypeError, ValueError)` in `_to_optional_float(...)`.

#### Fix Verification

- **函数名确认:** controller 和 DS review 使用 `_safe_float(...)` 描述该函数；代码中实际函数名为 `_to_optional_float(...)`（`sec_xbrl_query.py:307`）。定位正确，对应唯一函数。
- **diff 证据:** unstaged diff 显示 `sec_xbrl_query.py:323` 行从 `except Exception:` 改为 `except (TypeError, ValueError):`。变更精确、单一、无附带改动。
- **行为保持:** `float(value)` 在 Python 中对不可转换类型抛 `TypeError`，对无法解析字符串抛 `ValueError`。这两种异常覆盖了所有"正常转换失败"场景，返回 `None` 行为不变。
- **异常泄漏正确性:** `OverflowError`、`RuntimeError`、`MemoryError` 等非转换异常不再被静默吞掉，会正常向上传播。这正是 finding 的 root cause 修复目标。
- **无新 material issue:** fix 不改变函数签名、返回值语义、调用方契约或错误传播路径（除收窄的异常外）。

**Finding status: 已修复 ✅**

#### 其它 `except Exception` 观察

文件中仍有 5 处 `except Exception`（行 101、494、736、794、834），分布在 `_infer_xbrl_taxonomy`、`_query_facts_rows`、`_infer_units_from_xbrl_query`、`_infer_scale_from_xbrl_query`、`_infer_period_semantics_from_xbrl_query`。这些函数的 `except Exception` 均用于探测式 XBRL 查询的容错（probe-and-skip 模式），语义不同于 `_to_optional_float` 的"转换失败返回 None"。controller adjudication 仅 accepted F01（限定 `_to_optional_float`），其余不在本次 fix scope 内。不作为 new finding 报告，因其语义上下文不同且属于 probe 容错的合理设计。

#### Docstring 一致性

`_to_optional_float` 的 docstring（行 317）声明 `Raises: ValueError: 转换失败时抛出`，但函数实际在转换失败时返回 `None`。这是 pre-existing docstring 不准确，不是 fix 引入的问题，且不影响 correctness。不作为本次 re-review 的 finding。

## New Findings

未发现新 material issue。

## Blocking Questions

无。

## Conclusion

`R3-D-S3-CR-F01` fix 已正确实施。`_to_optional_float(...)` 的异常捕获从 `except Exception` 收窄为 `except (TypeError, ValueError)`，变更精确、行为保持、无新风险。fix gate 通过。
