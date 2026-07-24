# WU-OBS-00 Slice 3 Implementation Completion

status=complete

work_unit=WU-OBS-00

slice=S3

artifact path=docs/reviews/wu-obs-00-slice-3-implementation-codex.md

## Changed files

changed files=

- `dayu/host/tool_trace_analysis_rules.py`
- `dayu/host/tool_trace_analysis.py`
- `tests/host/test_tool_trace_analysis_rules.py`
- `tests/host/test_tool_trace_analysis.py`
- `docs/reviews/wu-obs-00-slice-3-implementation-codex.md`

Controller 持有且预先存在的
`docs/host/issues-implementation-control.md` dirty change 仅做只读检查、未回写，也不计入本
Slice implementation files。

## Semantic owner / interface decisions

semantic owner/interface decisions=

- Engine/provider/protocol finding、vendor debugging block、partial signal 分类由 analyzer rules
  owner 产生；Markdown 只投影同一 structured report，不另行推断。
- provider request id 与 client correlation id 保持独立字段和独立身份；client id 不充当
  provider id。
- vendor block 仅按直接 provider request id 分组；provider id 缺失时，仅存在直接 client id
  才按 client id 分组；两者都缺失时按直接 event identity 分块。未使用 run、attempt、
  iteration、sequence 或时间做身份补偿。
- vendor attempt/execution/iteration 只读取 producer/source 已提供的直接字段。其中
  `iteration_id` 只从 resolver 已验证的 source event payload（或既有 typed trace summary）
  读取；不可证明时写 limitation。
- usage event 不参与 vendor debugging trigger 或 grouping。
- partial signal 严格区分字段 absent、显式 `summary_status=none` 与
  `summary_status=present`；absent 只产生 unverifiable/limited 语义。
- 同一 provider request id 下 client/session/run/attempt/execution/iteration ref 冲突时，
  产生 `engine.vendor_correlation_conflict` finding，并在 block limitation 中保留冲突证据。
- Issue #64 缺少 provider request id 时，只说明“无法验证 native Anthropic/Claude Code
  gateway-specific signal”；不据此推断 adapter/provider family。
- 未改 frozen report contract、schema、finding order/id、既有 Host/Tool rules 或 producer
  contract；未引入兼容 fallback、loose parsing、顺序/时间补偿。

## Tests

tests=

1. Slice 3 targeted：

   ```bash
   source .venv/bin/activate
   pytest -q \
     tests/host/test_tool_trace_analysis_rules.py \
     tests/host/test_tool_trace_analysis.py
   ```

   结果：`28 passed in 0.33s`（最终最小化 patch 后复跑）。

2. Plan focused Host：

   ```bash
   source .venv/bin/activate
   pytest -q \
     tests/host/test_durable_connection.py \
     tests/host/test_tool_trace_projection.py \
     tests/host/test_tool_trace_queries.py \
     tests/host/test_tool_trace_analysis_input.py \
     tests/host/test_tool_trace_analysis_rules.py \
     tests/host/test_tool_trace_analysis.py
   ```

   结果：`139 passed in 1.13s`。

3. Clean full Host：

   ```bash
   source .venv/bin/activate
   pytest -q tests/host
   ```

   结果：`2325 passed, 1 skipped, 6 deselected in 61.79s`。

新增 owner-level tests 覆盖 provider/client/per-event 三种 block identity、完整 local refs、
provider identity 冲突、absent/none/present partial signal、file-only limitation、usage 零参与、
runner observation mismatch，以及 Markdown 对 structured vendor block 的单向投影。

## Pyright

pyright=

1. Targeted（plan files + Slice 3 files）：

   ```bash
   source .venv/bin/activate
   python -m pyright \
     dayu/host/tool_trace_analysis_contracts.py \
     dayu/host/tool_trace_analysis_input.py \
     dayu/host/tool_trace_analysis_rules.py \
     dayu/host/tool_trace_analysis.py \
     dayu/host/tool_trace.py \
     dayu/host/open_host.py \
     dayu/host/durable/connection.py \
     dayu/host/durable/transaction.py \
     dayu/host/durable/tool_trace.py \
     tests/host/test_tool_trace_analysis_input.py \
     tests/host/test_tool_trace_analysis_rules.py \
     tests/host/test_tool_trace_analysis.py
   ```

   结果：`0 errors, 0 warnings, 0 informations`。

2. Full：

   ```bash
   source .venv/bin/activate
   python -m pyright dayu/ tests/ utils/
   ```

   结果：`0 errors, 0 warnings, 0 informations`。

最终最小化 patch 后另对两个 production files 与两个 Slice 3 test files 复跑 targeted
pyright，结果仍为 `0 errors, 0 warnings, 0 informations`。

## Coverage

coverage=

```bash
source .venv/bin/activate
coverage erase
pytest -q \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py \
  --cov=dayu.host.tool_trace_analysis_rules \
  --cov=dayu.host.tool_trace_analysis \
  --cov-branch \
  --cov-report=term-missing
```

结果：`55 passed in 0.83s`。

- `dayu/host/tool_trace_analysis.py`：124 statements，0 miss；40 branches，0 partial；
  coverage `100%`。
- `dayu/host/tool_trace_analysis_rules.py`：572 statements，33 miss；208 branches，
  32 partial；coverage `92%`。

两个变更 production files 的逐文件 branch coverage 均达到 `>=80%` gate。

## Documentation and audit

docs decision=not-yet-due

- 已按触发规则检查 `dayu/host/README.md` 与 `tests/README.md` 的 Agent 更新约束。
- 本 Slice 未新增用户入口、稳定 public contract/schema 或测试层/测试命令；完整 analyzer
  用户工作流与 README 同步属于计划中的 Slice 4，因此本 Slice 不机械修改 README。
- `git diff --check` 通过。
- `dayu/host/tool_trace_analysis_contracts.py` 相对 accepted Slice 2
  `c3934caf4680804c4917f887b94ae9abff2a4b9f` 无 diff。
- frozen `_report_json` shape/schema version、既有 finding ordering/id helper、既有 Host/Tool
  rule ids 均无改动；新增 rule ids 仅为 `engine.*`。
- allowlist 审计只发现本 artifact、四个 Slice 3 allowed implementation/test files，以及
  Controller 预先持有的 dirty control doc；未改其他文件。

## Findings / residual risks

findings/residual risks=

- limitation / accepted：当前事件没有可证明 provider request id 时，vendor identity 维持
  limited；Issue #64 gateway-specific signal 只能 unverifiable，不能由顺序、时间或 client
  id 补偿。
- limitation / accepted：file-only 或 payload resolution 不可用时，source-only local refs
  保持 limited；不修改 producer/contract 来补足。
- deferred validation / Slice 4：完整 CLI/action 入口、真实 workspace smoke 与最终 README
  由 Slice 4 装配后验证；本 Slice 的 analyzer owner contract 已由 unit、focused 与 full Host
  tests 覆盖。
- blocker：无。没有发现必须修改 contract、producer 或 schema 才能实现 Slice 3 的直接证据。

stop condition=none

next entry point=code review; never self-advance
