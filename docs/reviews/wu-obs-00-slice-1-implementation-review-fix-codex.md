# WU-OBS-00 Slice 1 Implementation Review Fix

```text
status=complete
work_unit=WU-OBS-00
slice=S1
gate=implementation review fix
branch=work/wu-obs-00
accepted_plan_commit=e1799abc3341872ba19ff609de15b236813a3533
artifact path=docs/reviews/wu-obs-00-slice-1-implementation-review-fix-codex.md
next=AgentMiMo / AgentDS dual implementation re-review
```

## Finding closure

### CTRL-S1-IMPL-01 — 已修复

`dayu.host.__all__` 已按 accepted Slice 1 public contract 导出
`ToolTraceAnalysisPolicy`、`ToolTraceAnalysisSource`、`ToolTraceInputMode`，但
`tests/host/test_package_exports.py` 的 owner-level expected set 尚未同步，导致完整 Host suite
出现确定性失败。

本 fix 在测试中新增独立的 `EXPECTED_TOOL_TRACE_ANALYSIS_EXPORTS`，并将其纳入
`EXPECTED_HOST_EXPORTS`。测试现在直接断言当前 public owner contract；未通过 production
兼容导出、fallback、loose parsing 或其它下游补偿绕过差异。

### CTRL-S1-IMPL-02 — rejected，未处理

Controller 已拒绝修改 `_read_exact_prefix` 防御分支。本 fix 未修改任何 production 文件，也未
删除、改写或绕过该 exact-prefix fail-closed invariant。

## Changed files

- `tests/host/test_package_exports.py`
  - 同步三个 accepted Slice 1 `dayu.host` public exports。
- `docs/reviews/wu-obs-00-slice-1-implementation-review-fix-codex.md`
  - 记录本 fix 的 finding closure、验证、docs decision、blocker 与 next entry point。

除此之外，本 gate 未修改 production、真实 workspace、schema、control/plan/design、README 或
其它测试。

## Validation

所有 Python 命令均先执行 `source .venv/bin/activate`。

### Package export test

```text
pytest -q tests/host/test_package_exports.py::test_host_all_matches_current_public_contracts
1 passed in 0.30s
```

### Slice 1 focused tests

```text
pytest -q \
  tests/host/test_durable_connection.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_tool_trace_queries.py \
  tests/host/test_tool_trace_analysis_input.py
111 passed in 1.09s
```

### Complete Host tests

```text
pytest -q tests/host
2296 passed, 2 skipped, 6 deselected in 63.35s (0:01:03)
```

### Targeted pyright

```text
python -m pyright \
  dayu/host/tool_trace_analysis_contracts.py \
  dayu/host/tool_trace_analysis_input.py \
  dayu/host/tool_trace.py \
  dayu/host/open_host.py \
  dayu/host/durable/connection.py \
  dayu/host/durable/transaction.py \
  dayu/host/durable/tool_trace.py \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_package_exports.py
0 errors, 0 warnings, 0 informations
```

### Full pyright

```text
python -m pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations
```

### Repository checks

```text
git diff --check
PASS（无输出）
```

Scope audit：相对本 gate preflight，新增修改仅为
`tests/host/test_package_exports.py` 与本 artifact，均在 Controller allowlist 内。当前 worktree
其余 dirty paths 均为进入本 gate 前已存在的 Slice 1 implementation、review 与 Controller
artifacts；本 fix 未改动它们。

## Docs decision

`not-updated`。Controller 明确禁止修改 README、control、plan、design；本 fix 只同步测试中的
public export expected set，不改变用户可见工作流或 production contract。WU-OBS-00 的 README
更新仍按 accepted plan 留在 Slice 4。

## Residual risks / blocker

- Live schema blocker 保持不变：真实 workspace DB schema=`20`，current fresh schema=`24`。
  Slice 1 acceptance、保护提交与 Slice 2 继续冻结；本 fix 未读取或修改真实 workspace，未增加
  schema 兼容、raw SQLite、fallback、跳过 schema validation 或 cold-only 降级。
- 当前 workspace descriptor 的 live resolver smoke 仍因上述 schema gate 未执行；owner-level
  fixture resolver contract 已由 Slice 1 focused tests 覆盖。
- 跨平台 same-handle exact-prefix 行为仍是原 review 记录的 residual；本 fix 不改变该行为。

不存在由 CTRL-S1-IMPL-01 留下的未分类风险或 blocking open question。

## Stop condition / next entry point

`stop condition=none`。Fix gate 已完成，但不自我裁决 acceptance，不 commit、push、创建 PR、
修改 Issue 或进入 Slice 2。

`next entry point=AgentMiMo / AgentDS dual implementation re-review`。本 Agent 显式停在 re-review
前。
