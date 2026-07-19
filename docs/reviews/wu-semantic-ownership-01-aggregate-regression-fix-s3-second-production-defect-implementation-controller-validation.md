# WU-SEMANTIC-OWNERSHIP-01 Slice 3 第二个 Production Defect Implementation Controller Validation

## Verdict

`PASS / S3-STOP-F01 PROTECTED / S3-STOP-F02 IMPLEMENTED / AR-F05 CLOSED / READY_FOR_DUAL_COMPLETE_CODE_REVIEW`。

本 validation 独立核对 accepted base
`9ad5711e20dd35d5a0cdc0cf79067333ff3b3daf`、fixed plan SHA-256
`552df22871f3eb07465b971ca3fdf182032f3b2087e27442b0d78a1b7d8acc04` 与 AgentCodex artifact
`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-second-production-defect-implementation-codex.md`
（SHA-256 `32419e2193b285c4543f838d31f321f6272d200fee7061cd1178343494242fbf`）。

## Scope and owner validation

- 相对 accepted base 的 production Python 只有受保护的
  `dayu/documents/processors/docling_processor.py` 与本次唯一新增 production path
  `dayu/fins/processors/sec_form_section_common.py`。
- Docling final SHA-256 仍为
  `e2ab00fd984a4c27c30254d62ce038fafb91b9bc88d03eb786ad29f27acfd649`；本次未改写其已完成caption语义。
- Fins owner final SHA-256 为
  `9f66893b6c3c2af2427f02967c16ba1557fb1c5070c58978c9c8de70902c45a2`。
- `DocumentProcessor`、`SecProcessor`、10-K/10-Q与BS同族processors相对锁定基线零diff；没有第二个新增
  production path、公共schema、兼容分支、deferred Issue能力或统一authorization framework。
- `_VirtualSectionPublicationMode`唯一表示`BUILDING`、`VIRTUAL_PUBLISHED`、
  `BASE_FALLBACK_PUBLISHED`；refresh先构建并验证owner-local candidate，再通过单一publication helper
  提交完整virtual或完整base fallback状态。
- raw marker先验证dangling/duplicate，随后验证tree与同一candidate双向mapping；缺失/不完整且无矛盾
  才whole-base fallback。zero-table可发布virtual；首次与二次refresh消费同一terminal。
- `_remap_tables_to_deepest_virtual_sections()`只修改同一candidate mapping；silent filter、position guess、
  `fallback_ref`、`last_known_ref`均为零。五个public consumers统一由typed mode选择owner contract。

## Independent verification

Controller fresh运行：

```text
six authorized test files: 252 passed, 3 warnings
full pyright: 0 errors, 0 warnings, 0 informations
scoped Ruff: All checks passed
git diff --check: pass
staged tree: empty
```

Controller直接读取最终coverage JSON并重新从aggregate base枚举changed production：

```text
changed=219
measured=219
qualified=219
minimum=dayu/fins/storage/_fs_identity.py 80.00%
```

AgentCodex记录的fresh canonical为`5260 passed / 10 skipped / 5 deselected`；fresh coverage run为
`5259 passed / 10 skipped / 6 deselected`，额外deselect仅为先完成唯一collect preflight并单独通过的
AR-F06 scheduler node。Docling为`82.2804%`，本次Fins publication owner为`80.0889%`。

Full Ruff current集合相对锁定集合`ADDED=0 / REMOVED=1`；移除项是本owner删除已无用途的历史
`SecProcessor` F401。Wheel/sdist build成功。README触发裁决正确：只同步
`dayu/fins/README.md`的稳定processor publication语义。

## Smoke, security and residual disposition

- AAPL 2025 10-K public download/process分别成功，`failed=0`。
- current live-browser owner `1 passed`；HKEX deterministic `77 passed`且immutable raw evidence未变；CLI
  POSIX/containment/process fence `8 passed`，5个Darwin Windows skip继续属于`AR-F07` release evidence。
- Doc/Web security矩阵`346 passed, 1 skipped`；Host/Engine`495 passed`；Fins`998 passed, 1 skipped`。
- configured-value scan符合用户裁决：Config与Host internal SQLite/EventLog是trusted local domain；Tool
  Trace、audit、public、LLM-facing、logs/outputs/diff/reviews的plaintext match均为0。没有新增secret infra。
- R03 fresh workspace的六个round均运行，但canonical EventLog证明real provider在Web round未发出
  `search_web`（count=0）。这不是本次production path、ToolRuntime丢失或workspace污染。按用户已裁决的
  测试账号低budget边界，状态为
  `EXPECTED_TEST_ACCOUNT_QUOTA / PROVIDER_ADHERENCE_RESIDUAL / NO_CODE_ACTION / NON_BLOCKING`；禁止追加
  provider调用或改config/model/key/retry/quota/budget，不阻塞code review。
- `AR-F06`继续`RETAINED / UNFIXED / UNWAIVED / CURRENT_NO_FIX`；`AR-F07`继续
  `PENDING_RELEASE_BLOCKER / REAL_REMOTE_WINDOWS_EVIDENCE`。二者均未被本实现偷改或豁免。

## Immutable code-review target

完整review target是以下9个product/test/README paths，不得只审第二缺陷hunk：

```text
dayu/documents/processors/docling_processor.py
dayu/fins/README.md
dayu/fins/processors/sec_form_section_common.py
tests/documents/test_processors.py
tests/fins/test_sec_pipeline_download.py
tests/fins/test_processor_read_consistency.py
tests/fins/test_fins_ingestion_tools.py
tests/host/test_effective_execution_config.py
tests/runtime/test_argparse_exit.py
```

Locks：

```text
tracked binary diff SHA-256 = de39190c66121255ddd69fdb3418b9ad8bca74e455a98ff94f3fe2e9e08fb206
9-path content-manifest SHA-256 = 83cddc11fc114531972ad43db8f55080c0f53803d3eed76ddeb93afacf3f8b28
9-path status-manifest SHA-256 = 2c7b84432af3b37521b1618a4058bee851f02300adf11df75be1634cf7d21573
```

下一gate仅为AgentMiMo/AgentDS并发完整code review。不得stage/commit、开始aggregate或把任一路PASS
直接当作Slice接受。
