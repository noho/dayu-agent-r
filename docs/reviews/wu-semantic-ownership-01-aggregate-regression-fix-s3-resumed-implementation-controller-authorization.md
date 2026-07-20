# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Resumed Implementation Controller Authorization

## 1. Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` continuation；不是新 WU。
- Gate：accepted corrected plan后的Slice 3 resumed implementation。
- Implementation base：`48c6cc5ef74f273b1b592682ae9ab3e14cb48cbe`。
- Final corrected plan SHA-256：`e870921ec608247a666d03ca7845c1d8a6453409392201a95eb16933ec53ef56`。
- Plan accepted-commit validation：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-corrected-plan-accepted-commit-controller-validation.md`。

## 2. Mutable allowlists

唯一production path：

```text
M dayu/documents/processors/docling_processor.py
```

Test paths：

```text
M tests/documents/test_processors.py
M tests/fins/test_sec_pipeline_download.py
M tests/fins/test_processor_read_consistency.py
M tests/fins/test_fins_ingestion_tools.py
M tests/host/test_effective_execution_config.py
A tests/runtime/test_argparse_exit.py
```

其它production/tests/README/utility/design/control/review artifacts零diff。当前四路径existing test delta必须从上述accepted hashes增量继续，不得删除或重写已通过cases。

## 3. Mandatory implementation order

1. 先按final plan精确修复`S3-STOP-F01`：同一document、typed root sentinel、current captions refs、typed TextItem、ordered normalized exact dedup、no fallback、精确dangling边界。
2. 完成caption public matrix；现有失败node必须先变绿。
3. 再继续其余九owner public-contract coverage；如再发现production correctness/type/security defect或需要第二production path，立即STOP。
4. 完整运行plan §4.3/§6全部门禁，不得沿用stop前未运行结果。

## 4. Required evidence

- Focused tests与caption matrix。
- Canonical full suite 0 failed；AR-F06 node真实运行。
- 每次coverage前exact collect-only唯一收集AR-F06 node；coverage只deselect该node；changed production集合精确219且219/219 line coverage>=80%，九owner逐项ledger。
- Full pyright zero、Ruff immutable set无增量且mutable paths零finding、wheel+sdist。
- Diff/allowlist/staged、README trigger、six scans、Slice2 stale-owner scans、AAPL download/process、R03 public Host、current live browser cleanup、upload跨平台nodes、security matrices与configured-secret owner scan。
- Gemini quota固定`EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，不追加真实provider调用。
- Config/Host internal SQLite/EventLog=`ACCEPTED_TRUSTED_INTERNAL`；Tool Trace/audit/public/LLM/log/output/diff/review=`ZERO_REQUIRED`。
- 不实施统一tool authorization framework、Topic8/9、Issues142/151/175/177/178或其它deferred功能。

## 5. Handoff

AgentCodex完成后写：

```text
docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s3-implementation-continuation-codex.md
```

不得覆盖已提交的stop artifact，不得stage/commit或进入code review/aggregate。下一gate必须是Controller独立验证。
