# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S3 Code Review (AgentDS)

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S3 — Fiscal And Normalization Owners, SEC Version Alignment, Docs And Aggregate Closure`
- Gate: `code review (AgentDS)`
- Review date: 2026-07-13T10:46:27+08:00
- Artifact path: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-code-review-ds.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`, `docs/phaseflow-umbrella-optimization-control.md`
- Accepted plan: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`（S3 章节）
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-controller-validation.md`

## Scope

- Mode: current changes (S3 implementation diff only)
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Included scope: S3 allowed production files, S3 test files, `dayu/fins/README.md`, plan S3 章节, implementation artifact, controller validation artifact
- Excluded scope: S1/S2 committed diffs（除非 S3 回归触达）；R3-E/tool-security；Host/Engine；config prompt；upload/download security schema

## Review Method Summary

沿 S3 五个重点深挖方向逐条走读真源代码路径，对每条路径执行：入口 → 分支条件 → 下游调用 → 返回值/副作用。SEC version/skip 沿 fast skip（`_can_skip_fast`）→ remote fingerprint/files skip（`_can_skip`）→ not-modified terminal skip 三条路径完整追踪；upload alias 从 `upsert_company_meta_for_upload` 入口到 `_normalize_ticker_aliases` 内部每条 alias 的 canonical + dedupe + invalid 分支逐行走读；fiscal 变更从 domain owner 定义到 read runtime 消费者逐层验证删除/新增边界。

## Findings

### 1-未修复-低-`_safe_float` 过度宽泛的 Exception 捕获

- **入口/函数**: `_safe_float(value)` — 标量到 float 转换工具函数
- **文件(行号)**: `dayu/fins/processors/sec_xbrl_query.py:326`
- **输入场景**: 传入非标量值（如 dict、list）或触发非预期 Python 异常的值
- **实际分支**: `except Exception: return None`
- **预期行为**: 应仅捕获 `float()` 可能抛出的 `ValueError` 和 `TypeError`
- **实际行为**: 捕获全部 `Exception` 子类（含 `KeyboardInterrupt`、`MemoryError`），将非预期系统异常也静默吞为 `None`
- **直接证据**: `sec_xbrl_query.py:324-327` — `try: numeric = float(value)` → `except Exception: return None`
- **影响**: 极低。`float()` 在 CPython 上只抛 `ValueError`/`TypeError`，且该函数仅用于 fact value 转换的非关键路径。即使异常被过度捕获，下游 consumer 会把 `None` 视为缺失值继续处理
- **建议改法和验证点**: 将 `except Exception` 收窄为 `except (ValueError, TypeError)`；该函数不是 S3 新增，属于既有技术债
- **修复风险（低）**: `float()` 的异常集合在 CPython 定义明确，收窄不会改变当前行为
- **严重程度（低）**: 不影响 S3 正确性；属于既有代码味道，按 CLAUDE.md 的"禁止为旧实现保留兼容逻辑"原则记录，但不强制在 S3 修复

## Open Questions

无。

## Residual Risk

| 风险 | Owner/Destination | 说明 |
| --- | --- | --- |
| SEC downloader `errors="ignore"` 三处 | 后续独立 Fins downloader decode-policy WU | `sec_downloader.py:568,2342,2392`；不在 S3 allowed files，对 downloader HTML/index-header 启发式解析的 permissive decode 仍需收敛 |
| `_safe_float` 宽泛 Exception | 后续 code-quality WU | 既有代码，不在 S3 修改范围；不影响当前正确性 |
| broad `DocumentMeta` type migration | umbrella controller 后续裁决 | 已记录在 accepted plan residual，S3 未宣称修复 |
| 6-K BS-only routing | umbrella controller 后续裁决 | 已记录在 accepted plan residual，S3 未宣称修复 |
| edgartools deprecated import warnings | 依赖升级工作 | 不影响当前 contract correctness |

## Review Conclusion

S3 五个重点深挖方向均通过 review：

1. **SEC version/skip owner**：`has_current_download_version` 被 fast skip（`sec_pipeline.py:1388`）、remote fingerprint/files skip（`sec_pipeline.py:1419`）、not-modified terminal skip（`sec_download_filing_workflow.py:533`）三条路径正确消费。legacy/missing version 下 all-files-not-modified 不 skip，改为继续 commit current `SEC_PIPELINE_DOWNLOAD_VERSION`（test 参数化覆盖三类 version 并断言 committed meta 版本正确）。current version 的 not-modified skip 保持 rollback 不重写 meta 行为。

2. **Upload alias owner**：`_normalize_ticker_aliases` 对 canonical ticker 和每个非空 alias 全部走 `try_normalize_ticker`，取 `.canonical` 去重，canonical 始终首项。HK suffix（`700.HK → 0700`）、US suffix（`BRK.B → BRK-B`）、大小写变体（`aapl → AAPL`）均验证通过。无法识别的非空 alias 抛 `ValueError`，spy repository 证明零写入。CN upload 旧夹具中 company-name alias（`贵州茅台`）已迁移为真实 ticker suffix alias（`600519.SH`）。生产代码无 `strip().upper()` alias 持久化。

3. **Tests/fakes**：`_SpyCompanyMetaRepository` 仅记录写入列表，不复制生产逻辑。测试直接断言 owner contract 行为：fiscal rank 固定顺序、read runtime 消费 domain rank helper（monkeypatch 验证）、source meta 缺失 fiscal 字段不从 form/date 补偿、显式值 canonical 化、非法值 fail closed、dataframe optional string 矩阵覆盖 NaN/NaT/0/False/普通文本。无 fake 限制生产行为或弱断言。

4. **Propagation scans/residual**：`errors="ignore"` 三处均在 `sec_downloader.py`，正确分类为"后续 downloader decode-policy owner residual"。`except Exception: continue` 四处（行 101 taxonomy probe、行 736 units probe、行 794/834 scale/fiscal evidence probe）均在辅助 probe，不在 `_query_facts_rows` 主 concept execution 路径；probe 失败由 S1 financial contract 降级为 typed `partial`。无未归属 residual。`_safe_float` 的宽泛 catch（行 326）为既有代码，不属 S3 修改范围。

5. **AGENTS.md 约束**：新增/修改函数均有完整中文 docstring（Args/Returns/Raises）；类型签名无 `Any`/`object`/裸容器；`_FISCAL_PERIOD_RECENCY_ORDER`、`SEC_PIPELINE_DOWNLOAD_VERSION`、`RESOLVER_VERSION` 等作为模块级常量定义，无魔法字符串扩散；`dayu.fins` 到 `dayu.host`/`dayu.engine` 反向 import 扫描零匹配；S3 不涉及工具安全代码。

**Finding 1（`_safe_float` 宽泛 Exception）为低严重度既有代码味道，不影响 S3 正确性，不阻塞 merge。**

### Completion Report

- **Conclusion**: S3 implementation 正确完成 accepted plan 的所有变更，五个重点深挖方向无实质性问题
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s3-code-review-ds.md`
- **Findings count**: 1（低严重度）
- **Blocking question**: 无
