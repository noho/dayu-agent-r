# WU-OBS-00 Slice 2 Implementation Review Fix — AgentCodex

## 状态

- `status=complete`
- Work Unit：`WU-OBS-00`
- Gate：Slice 2 implementation review fix
- Controller 真源：
  `docs/reviews/wu-obs-00-slice-2-implementation-review-controller-adjudication.md`
- 本 gate 只处理 `CTRL-S2-IMPL-01/02/03`；没有进入 re-review、commit、push、PR 或 Issue 操作。
- Blocking open questions：None。

## 第一性原理与 owner 判断

三个 accepted finding 均由直接代码证据证明成立，严重性边界也与 Controller 裁决一致：

1. module public surface 的唯一 owner 是 `dayu.host.tool_trace_analysis`。package root 已有精确
   exports，但 module 自身缺少 `__all__`，确实留下第二套隐式 public surface。
2. verified payload measure 的 ref/digest/size owner 是 hot snapshot resolver；cold JSONL record
   只拥有自己的 record bytes 与 path/line identity。旧 projection 先按同一 `event_id` 取 cold
   evidence，再只替换 `kind`，使 resolved measure 借用了 cold path/line。修复必须发生在
   Analyzer payload measure projection，而不是 renderer。
3. `cold_lock_path` 的派生 owner 仍是 Host Tool Trace projection owner。冻结 schema 要求字段
   非空；hot-only 不获取 cold lock 的事实由 `capabilities.cold=false` 表达。缺陷只在 contract
   与 LLM-readable Markdown 把 expected path 误写成了必然实际使用的 path。

没有证据要求修改 producer、schema、CLI、provider/vendor；也没有理由实现被拒绝的 Markdown
索引重构或公开/移动 `_tool_trace_cold_lock_path`。

## CTRL-S2-IMPL-01

- 最终状态：`已修复`
- Root cause：`dayu.host.tool_trace_analysis` 未显式声明 module-level public contract，Python
  wildcard import 会把内部 builder、loader 与 imported types 当作公共符号。
- Owner：`dayu.host.tool_trace_analysis`
- Changed files：
  - `dayu/host/tool_trace_analysis.py`
  - `tests/host/test_tool_trace_analysis.py`
- Closing evidence：
  - 新增静态 `__all__`，exact set 只有
    `analyze_tool_trace`、`render_tool_trace_analysis_markdown`、
    `tool_trace_analysis_report_to_json`。
  - owner-level test 精确断言 set，并明确断言
    `build_tool_trace_analysis_report`、`load_tool_trace_analysis_input` 不在 `__all__`。
  - 未增加 wrapper、alias、动态 export 或 package-root 新表面。

## CTRL-S2-IMPL-02

- 最终状态：`已修复`
- Root cause：`_public_payload_measure` 用 `event_id` 命中 cold record 后先创建 cold evidence；
  non-`COLD_LINE` 分支仅替换 `kind`，没有替换 `source_path`/`line_number`，混合了 cold record
  identity 与 hot resolver measure identity。
- Owner：`dayu.host.tool_trace_analysis_rules` 的 payload measure projection；上游 verified
  bytes 继续由 hot snapshot resolver 拥有。
- Changed files：
  - `dayu/host/tool_trace_analysis_rules.py`
  - `tests/host/test_tool_trace_analysis_rules.py`
- Closing evidence：
  - `COLD_LINE` 只接受同 `event_id/event_sequence` 的 cold record owner，保持
    `kind=cold_line`、cold JSONL path、1-based line 与
    `measurement_source=cold_jsonl_record_bytes`。
  - 所有其它 category 只接受 available hot snapshot、非空 expected hot DB path 和同
    `event_id/event_sequence` 的 hot row owner；evidence 固定
    `kind=resolved_payload`、`source_path=hot_db_path`、`line_number=None`。
  - resolved evidence 保留 verified measure 的 `event_id`、`event_sequence`、
    `payload_ref`、`category`、`size_bytes`，measurement source 固定为
    `resolved_payload_bytes`。
  - 删除 `requested_path`/cold path fallback；synthetic resolved measure 缺 hot
    capability/path 或缺少匹配 hot row 时直接 `ValueError` fail closed。
  - fixture 改为显式 workspace hot owner facts；新增同一 event 同时具有 cold-line measure 与
    tool-result resolved measure 的反例，逐字段断言 kind/path/line/measurement source 分离。

## CTRL-S2-IMPL-03

- 最终状态：`已修复`
- Root cause：`ToolTraceAnalysisInputSummary` docstring 把冻结非空字段描述为“实际使用的 lock
  path”，但 hot-only loader 不创建 marker、不获取 lock、不读取 cold snapshot。
- Owner：`ToolTraceAnalysisInputSummary` contract documentation 与 structured report 的
  Markdown projection。
- Changed files：
  - `dayu/host/tool_trace_analysis_contracts.py`
  - `dayu/host/tool_trace_analysis.py`
  - `tests/host/test_tool_trace_analysis_rules.py`
- Closing evidence：
  - frozen `Path` 字段、JSON key/shape 与 `_input_summary` owner-derived path 行为保持不变。
  - contract docstring 明确该字段是 Host owner 从 expected `cold_jsonl_path` 唯一派生的
    expected lock path；只有 `capabilities.cold=true` 才证明本次实际获取锁并读取 cold
    snapshot。
  - Markdown 同时显示 expected owner-derived path 与 cold capability 的判读规则。
  - hot-only 反例断言 path 稳定非空、`capabilities.cold=false`，并断言 Markdown 不允许由非空
    path 推断实际取锁。

## 实际修改文件

- `dayu/host/tool_trace_analysis.py`
- `dayu/host/tool_trace_analysis_rules.py`
- `dayu/host/tool_trace_analysis_contracts.py`
- `tests/host/test_tool_trace_analysis.py`
- `tests/host/test_tool_trace_analysis_rules.py`
- `docs/reviews/wu-obs-00-slice-2-implementation-review-fix-codex.md`

Controller control doc、Controller adjudication 与两路 review artifacts 未修改；既有 dirty
Slice 2 implementation changes 原样保留。

## Validation

### Focused

```bash
source .venv/bin/activate
pytest -q \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py \
  tests/host/test_package_exports.py
```

结果：`64 passed in 0.62s`。

### Clean full Host

```bash
source .venv/bin/activate
coverage erase
pytest -q tests/host
```

结果：`2318 passed, 2 skipped, 6 deselected in 60.58s`。运行前清除 coverage data，未受前序
coverage 残留污染。

### Targeted pyright

```bash
source .venv/bin/activate
python -m pyright \
  dayu/host/tool_trace_analysis.py \
  dayu/host/tool_trace_analysis_rules.py \
  dayu/host/tool_trace_analysis_contracts.py \
  tests/host/test_tool_trace_analysis.py \
  tests/host/test_tool_trace_analysis_rules.py
```

结果：`0 errors, 0 warnings, 0 informations`。

### Full pyright

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

### 逐 production 文件 branch coverage

```bash
source .venv/bin/activate
coverage erase
coverage run --branch -m pytest -q \
  tests/host/test_tool_trace_analysis_input.py \
  tests/host/test_tool_trace_analysis_rules.py \
  tests/host/test_tool_trace_analysis.py \
  tests/host/test_package_exports.py
coverage report -m \
  dayu/host/__init__.py \
  dayu/host/tool_trace_analysis_contracts.py \
  dayu/host/tool_trace_analysis_rules.py \
  dayu/host/tool_trace_analysis.py
```

测试结果：`64 passed in 0.80s`。

| Production file | Branch | BrPart | Cover |
|---|---:|---:|---:|
| `dayu/host/__init__.py` | 0 | 0 | 100% |
| `dayu/host/tool_trace_analysis.py` | 34 | 0 | 100% |
| `dayu/host/tool_trace_analysis_contracts.py` | 168 | 42 | 85% |
| `dayu/host/tool_trace_analysis_rules.py` | 142 | 26 | 91% |

所有 Slice 2 production diff 文件均达到逐文件 `>=80%`，未用 aggregate 掩盖。

### 额外静态检查

```bash
source .venv/bin/activate
python -m ruff check \
  dayu/host/tool_trace_analysis.py \
  dayu/host/tool_trace_analysis_rules.py \
  dayu/host/tool_trace_analysis_contracts.py \
  tests/host/test_tool_trace_analysis.py \
  tests/host/test_tool_trace_analysis_rules.py
```

结果：`All checks passed!`。

### Repository checks

```bash
git diff --check
git status --short
```

结果：`git diff --check` 通过。`git status --short` 仅保留本 WU 既有 Slice 2
production/tests、Controller control/review artifacts、本 fix 的允许文件与本 artifact；没有
workspace trace、SQLite sidecar、临时报告或其它越界文件。

## README audit

- 已读取 `dayu/host/README.md` 的 `Agent更新约束【必须遵守】`。本 fix 没有新增稳定 Host public
  API、状态机、装配或执行路径；module `__all__` 收紧、owner evidence 修正及 frozen schema 文案
  澄清属于同一未完成 Slice 的 contract correctness，不应把 review 过程或尚未交付的 operator
  command 写入开发手册。因此不修改。
- 已读取 `tests/README.md` 的职责与现有分层。新增测试仍属于已有 Host analyzer owner-level
  测试层，没有新增测试目录、运行入口或维护约定。因此不修改。
- 不触发根 README、`dayu/README.md` 或其它 README：没有用户可见 CLI/workflow、跨层装配、
  provider/vendor、Fins、Engine 或 config 变化。

## Diff scope / 非目标核对

- 未实现 DS Finding 4 的 Markdown 索引重构。
- 未公开、移动或重命名 `_tool_trace_cold_lock_path`，未增加 helper public surface。
- 未修改 producer、schema、CLI、provider/vendor。
- 未修改 `docs/host/issues-implementation-control.md`、Controller adjudication 或两路 review
  artifacts。
- 未 commit、push、创建/修改 PR 或 Issue。

## Residual risks / uncovered areas

- 本 gate 接受的三项 finding 均已关闭，无当前 scope residual risk。
- Engine/provider/vendor rules 仍按 accepted plan 属于 Slice 3；不是本 fix 未覆盖缺陷。
- native Anthropic / Claude Code gateway-specific signal 仍由 Issue #64 跟踪；本 fix 未扩大。
- branch coverage 未覆盖的 contracts 防御性类型错误分支不影响本次三项 root-cause closure，且
  owner 文件覆盖率为 85%。

## Stop condition / 下一入口

- Stop condition：`none`。没有证据要求扩大到 schema/producer/CLI/provider/vendor，也没有 full
  validation scope blocker。
- `next entry point=Controller adjudication then AgentMiMo/AgentDS dual re-review`
- 本 Agent 不自行进入 re-review 或 acceptance。
