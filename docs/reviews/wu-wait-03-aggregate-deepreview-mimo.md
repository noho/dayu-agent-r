# Code Review

## Scope

- Mode: current changes
- Branch: phase/wu-wait-03-issue-92
- Base: main
- Output file: docs/reviews/wu-wait-03-aggregate-deepreview-mimo.md
- Included scope: 从 main 到当前分支的完整 work-unit diff（36 个文件，+3749/-39 行），包括未提交的 docs/host/issues-implementation-control.md 状态更新。
- Excluded scope: 无
- Parallel review coverage: 使用 5 个 subagents 并行审查：
  1. Host lifecycle contract / durable schema / poller diagnostics
  2. Fins adapter lifecycle mapping
  3. Tests coverage
  4. 分层反向依赖、runtime 越界、schema/README/doc sync 缺口
  5. overdesign 或未归属 residual risk

## Verdict

**pass** — 未发现 blocking findings。

## Findings

### 01-未修复-低-`tests/README.md` 未反映 WU-WAIT-03 测试变更

- **入口/函数**: N/A（文档 sync）
- **文件(行号)**: `tests/README.md`
- **输入场景**: WU-WAIT-03 修改了 6 个测试文件，新增大量测试覆盖
- **实际分支**: `tests/README.md` 未更新
- **预期行为**: 根据 AGENTS.md README 更新触发规则，`tests/` 修改应检查并按需更新 `tests/README.md`
- **实际行为**: `tests/README.md` 未提及 WU-WAIT-03 新增的测试覆盖范围
- **直接证据**: WU-WAIT-03 新增/修改的测试文件：
  - `tests/fins/test_fins_ingestion_runtime.py` (+151 行)
  - `tests/fins/test_fins_ingestion_tools.py` (+136 行)
  - `tests/host/test_durable_schema.py` (+6 行)
  - `tests/host/test_open_host_runtime.py` (+7 行)
  - `tests/host/test_wait_adapter_polling.py` (+345 行)
  - `tests/host/test_wait_poller_runtime.py` (+17 行)
  - `tests/host/test_wait_record_state.py` (+38 行)
- **影响**: 开发者查阅 README 时无法了解 WU-WAIT-03 的测试覆盖范围
- **建议改法和验证点**: 在 `tests/README.md` 的 Fins 和 Host 测试覆盖描述中补充 WU-WAIT-03 新增的测试内容
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-`dayu/host/README.md` 新增公共类型未同步

- **入口/函数**: N/A（文档 sync）
- **文件(行号)**: `dayu/host/README.md`
- **输入场景**: WU-WAIT-03 新增了多个公共类型
- **实际分支**: `dayu/host/README.md` 未更新公共契约列表
- **预期行为**: 根据 AGENTS.md README 更新触发规则，`dayu/host/` 修改应检查并按需更新 `dayu/host/README.md`
- **实际行为**: `dayu/host/README.md` 的公共契约列表未包含新增的 `WaitExternalJobLifecycleAction`、`WaitExternalJobLifecycleApplied`、`WaitExternalJobLifecycleNoop`、`WaitExternalJobLifecycleResult`、`WaitExternalJobRefSource` 等类型
- **直接证据**: `dayu/host/wait_adapter.py` 的 `__all__` 导出了这些新类型
- **影响**: 开发者查阅 README 时无法了解新增的公共类型
- **建议改法和验证点**: 在 `dayu/host/README.md` 的公共契约列表中补充新增类型
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Rejected Findings

### Subagent 4 Finding 1: `dayu.fins` 向上 import `dayu.host`（rejected-with-reason）

- **问题描述**: `dayu/fins/ingestion/wait_adapter.py` 向上 import `dayu.host`，声称违反架构约束
- **裁决**: `rejected-with-reason`
- **理由**: 代码直接证据显示，`dayu/fins/ingestion/wait_adapter.py` 在 main 分支就已经 import `dayu.host`（包括 `dayu.host.api`、`dayu.host.durable.state`、`dayu.host.wait_adapter`）。这不是 WU-WAIT-03 新引入的反向依赖，而是已有的架构设计——fins 层实现 host 的 adapter protocol。WU-WAIT-03 只是在已有的 import 基础上新增了 4 个符号（`WaitExternalJobLifecycleAction`、`WaitExternalJobLifecycleApplied`、`WaitExternalJobLifecycleNoop`、`WaitExternalJobLifecycleResult`）。这属于 fins 实现 host adapter protocol 的正常依赖方向，不是本次 review scope 内的缺陷。

## Open Questions

无。

## Residual Risk

- **tests/README.md sync**: WU-WAIT-03 修改了 7 个测试文件，新增大量测试覆盖，但 `tests/README.md` 未同步更新。Owner: WU-WAIT-03 merge 后的 README sync。
- **dayu/host/README.md sync**: WU-WAIT-03 新增了多个公共类型，但 `dayu/host/README.md` 的公共契约列表未同步更新。Owner: WU-WAIT-03 merge 后的 README sync。
- **Some real providers may not support physical cancel**: Owner/destination: provider-specific Fins/source adapter owners under GitHub issue #92 / #87。
- **Poller disabled deployments will not perform external lifecycle action**: Owner/destination: Service/composition deployment and WU-WAIT-04 production-grade E2E smoke。
- **Running Fins operations may only observe cooperative cancellation at checkpoints**: Owner/destination: Fins provider/runtime owners。
- **Tool trace projection may later want richer lifecycle diagnostics**: Owner/destination: future tool trace / diagnostic projection work。

## Review Evidence Summary

### 1. Host lifecycle contract / durable schema / poller diagnostics

**结论**: 未发现实质性问题。

- Durable schema 变更为 additive enum（`HOST_SCHEMA_VERSION` 18 -> 19），CHECK 约束新增 `'abandon_unsupported'` 和 `'abandon_noop'`，无新增 column/table/index
- Host lifecycle contract 完整引入封闭联合类型（`WaitExternalJobLifecycleAction`、`WaitExternalJobLifecycleApplied`、`WaitExternalJobLifecycleUnsupported`、`WaitExternalJobLifecycleNoop`、`WaitExternalJobLifecycleResult`）
- Poller diagnostics 完整覆盖 applied/unsupported/noop/error/missing-adapter/shutdown 六条路径
- `cancel_waiting_run_in_transaction` 未被修改，无 state machine regression
- 35 个 Host focused tests 全部通过

### 2. Fins adapter lifecycle mapping

**结论**: 未发现实质性问题。

- Fins adapter lifecycle mapping 完全符合 plan：valid handle -> ABANDON, corrupt token -> NOOP, missing observation -> NOOP, non-transient error -> NOOP, TRANSIENT_UNAVAILABLE -> re-raise
- Best-effort cancel/abandon 不泄漏 Host/Fins internal ids 到 LLM-facing/user diagnostics
- Fins adapter 正确调用 `cancel_observation` 和 `abandon_observation`
- 126 个 Fins focused tests 全部通过

### 3. Tests coverage

**结论**: 未发现实质性问题。

- Tests 完整覆盖 supported/unsupported/noop/error/retry/late-result/schema/Fins runtime paths
- Host 测试覆盖 cancelled wait lifecycle applied/unsupported/noop/exception paths、CAS conflict tests、late result diagnostic
- Fins 测试覆盖 valid handle、corrupt token、missing observation、non-transient error、TRANSIENT_UNAVAILABLE、prepared observation cancel+abandon
- Schema 测试覆盖 `WaitPollLastOutcome` 新枚举值 `ABANDON_UNSUPPORTED` 和 `ABANDON_NOOP` 的 serialize/deserialize roundtrip

### 4. 分层反向依赖、runtime 越界、schema/README/doc sync 缺口

**结论**: 未发现 blocking findings。

- `dayu/runtime` 边界合规，未发现越界问题
- `dayu/host` 不依赖 `dayu/fins`
- `docs/host/issues-implementation-control.md` 未提交变更正确记录了 WU-WAIT-03 的状态
- `tests/README.md` 和 `dayu/host/README.md` 有 minor sync gap，但非阻塞

### 5. Overdesign 或未归属 residual risk

**结论**: 未发现实质性问题。

- 未引入新的 runtime、service、queue、durable table、provider registry 或第二套 watchdog
- `external_job_id` 未变成 Host durable primary key
- 未绕过 `resolve_wait(...)` 或 late-result rejection
- 未在 Host cancel transaction 或 command path 内执行 provider I/O
- Plan residual risks 已正确归属

## Validation Evidence

Controller 已验证：
- Slice 1 focused tests passed
- Slice 2 Fins 126 passed
- Host 35 passed
- pyright 0 errors
- git diff --check passed
