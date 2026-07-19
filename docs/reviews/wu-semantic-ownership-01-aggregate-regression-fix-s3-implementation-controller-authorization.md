# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Slice 3 Implementation Controller Authorization

## 1. Gate identity

- 日期：`2026-07-19`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU。
- Gate：Aggregate regression fix Slice 3 test-only coverage closure implementation。
- Immutable slice base：`9e7a4e9d4796b9c382d44494bb10efa64787b199`。
- Accepted plan：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，SHA-256 `afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252`。
- Slice 2 accepted commit validation：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s2-accepted-commit-controller-validation.md`。

## 2. Goal and owner boundary

只通过 public/owner-contract tests 为九个现存 production owners补足真实业务分支，关闭 `AR-F05`。Production allowlist严格为空；测试只能验证 owner 对外可观察行为，不得复制 production算法、构造不可能状态、增加 mock-only hook、耦合不稳定 private implementation、修改 coverage config或降低阈值。

## 3. Exact mutable allowlist

```text
M tests/documents/test_processors.py
M tests/fins/test_sec_pipeline_download.py
M tests/fins/test_processor_read_consistency.py
M tests/fins/test_fins_ingestion_tools.py
M tests/host/test_effective_execution_config.py
A tests/runtime/test_argparse_exit.py
```

九个 production owners 必须零 diff：

```text
dayu/documents/processors/docling_processor.py
dayu/fins/pipelines/sec_6k_rules.py
dayu/fins/processors/sec_form_section_common.py
dayu/fins/processors/sec_report_form_common.py
dayu/fins/processors/sec_section_build.py
dayu/fins/processors/sec_table_extraction.py
dayu/fins/tools/preprocess_tools.py
dayu/host/_execution_config_projection.py
dayu/runtime/argparse_exit.py
```

全部其它 production、test、utility、README、design/control/review artifacts也不可修改。读取 `tests/README.md` 更新约束并在 artifact 中裁决 `NO_UPDATE`；若确实需要 README 或 production 变更，立即停止交 Controller，不得自行扩域。

## 4. Required behavior families

- Docling processor：payload sniff/support、section/table/page/search/full-text、records/markdown fallback、caption/header/context、noise/default/dedup header、malformed/missing metadata fail-safe。
- SEC 6-K rules：candidate filename/type/rank、quarter/half-year/XBRL signals，以及 current 与未来/会议/管理变化/资本动作/演示/运营更新正负分类。
- SEC section/report/build/table owners：通过 public read/search/report/table结果覆盖 structured/fallback heading、TOC抑制、section boundaries、line-preserving HTML、edgartools/dataframe/table sources、duplicate occurrence、fingerprint、normalization等真实分支。
- Fins preprocess：`source_kind` missing/invalid/valid、optional tuple/bool、start/cancel/failure/awaiting outcomes与schema contract。
- Host effective config projection：optional/required JSON scalar、RunnerSpec/options/provider request/AgentPolicy round-trip、missing/wrong/unknown/tampered fields fail closed。
- Runtime argparse exit：int（含0/2/负数）原样返回，`None`/字符串/其它非int统一为usage error 2。

## 5. Stop conditions

任一测试暴露真实 production correctness/type/security defect，或只有改 production/直接耦合 private implementation才能达到80%，立即停止，保存最小复现、预期/实际、stack与coverage missing-line证据并交 Controller。不得顺手修 production、加兼容shim、fallback、`pragma: no cover`、omit、skip、xfail、retry或额外deselect。

## 6. Mandatory validation

AgentCodex必须完整执行 accepted plan §4.3 与 §6：

1. 六文件 focused tests；必要的 focused coverage只作反馈。
2. Canonical full suite，0 failed，AR-F06 node不得deselect/skip/retry。
3. Exact single-node exclusion coverage；最终 changed production集合恰好219，且 `219/219 >=80.00%`，九owner逐项列statements/covered/missing/line percent。
4. Full pyright zero；full Ruff immutable set无增量、六个mutable paths零finding。
5. Build wheel + sdist；diff/allowlist/staged checks；README `NO_UPDATE`；六组canonical scans；direct-stream/awaiting stale-owner scans。
6. AAPL download/process、R03 public Host smoke、current live-browser cleanup owner、upload POSIX/Windows节点、security matrices、configured-secret owner scan与必要真实smoke。
7. Gemini测试账号quota只记 `EXPECTED_TEST_ACCOUNT_QUOTA / NO_CODE_ACTION / NON_BLOCKING`，不追加真实provider调用或修改任何配置。

Internal Config/Host SQLite/EventLog继续按用户裁决归类为 `ACCEPTED_TRUSTED_INTERNAL`；Tool Trace、audit、public、LLM-facing、logs、其它outputs、diff/reviews继续 `ZERO_REQUIRED`。不得引入secret infrastructure或统一tool authorization framework。

## 7. Authorized handoff

只授权 AgentCodex 在上述六个test paths实施 Slice 3并形成完整 implementation/validation artifact。不得 stage、commit、开始code review、aggregate、push、PR或closeout；这些必须由 Controller验证后另行进入下一gate。
