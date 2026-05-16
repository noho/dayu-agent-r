# Code Review

## Scope

- Mode: current changes (uncommitted diff)
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- Output file: docs/reviews/host-phase7-code-review-s1-ds-20260516.md
- Included scope: P7-S1 Public Contracts And Durable Wait Record
  - dayu/host/api.py: typed outcome envelope, HostPayloadRef, WaitAdapterKey, WaitProviderStatusRef, length constants, ResolveWaitRequest reshape
  - dayu/host/__init__.py: public exports for new types and constants
  - dayu/host/tool_runtime.py: HostPayloadRef import migration, ToolFactKind.LOST
  - dayu/host/durable/schema.py: host_wait_records DDL, indexes, schema version bump
  - dayu/host/durable/state.py: WaitRecordStatus, WaitResumePolicy, WaitSnapshotRef, ExternalJobRef, WaitRecordRow, CAS helpers, RunStartReason.RESUME
  - tests/host/test_public_contracts.py: typed envelope validation
  - tests/host/test_package_exports.py: new export assertions
  - tests/host/test_durable_schema.py: wait record DDL/index verification
  - tests/host/test_state_schema.py: RunStartReason.RESUME codec test
  - tests/host/test_wait_record_state.py: wait record round-trip, DDL CHECK, unique active wait, CAS helpers
  - tests/host/test_public_run_api.py: request construction migration to typed envelope + UTC datetime
- Excluded scope:
  - P7-S2 (ToolAwaiting Accept Path), P7-S3 (resolve_wait Command), P7-S4 (WAITING Cancel/Adapter/EngineEvent), P7-S5 (Integration/Docs)
  - dayu/contracts/, dayu/engine/, dayu/fins/, dayu/service/, dayu/ui/
  - docs/host/design.md, docs/host/implementation-control.md (not in P7-S1 allowed files)
- Reference documents:
  - Approved plan: docs/host/phase7-tool-awaiting-resolve-wait-plan.md P7-S1
  - Implementation artifact: docs/reviews/host-phase7-implementation-s1-public-contracts-wait-record-20260516.md
  - Controller decision: docs/reviews/host-phase7-s1-controller-decision-test-ownership-20260516.md
- Parallel review coverage: 无

## Findings

### 001-未修复-中-长度常量在 api.py 与 schema.py 重复定义存在漂移风险

- **入口/函数**: 常量定义 `dayu/host/api.py:39-47` 与 `dayu/host/durable/schema.py:38-45`
- **文件(行号)**: dayu/host/api.py:39-47, dayu/host/durable/schema.py:38-45
- **输入场景**: 未来维护者修改 api.py 中的 `HOST_WAIT_ADAPTER_KEY_MAX_LENGTH` 等常量，但忘记同步更新 schema.py 中同名常量
- **实际分支**: N/A（当前两处值一致：均为 8 个相同的 max length 常量）
- **预期行为**: DDL CHECK 限制与 dataclass validation 使用同一真源常量，避免不一致导致的 schema 拒绝合法值或放行非法值
- **实际行为**: 两组常量独立定义，无编译期或测试期绑定验证它们一致
- **直接证据**: 
  - api.py:39-47 定义 `HOST_WAIT_ID_MAX_LENGTH=128` 等 9 个常量
  - schema.py:38-45 定义同样的 8 个常量（不含 `HOST_WAIT_PROVIDER_STATUS_REF_MAX_LENGTH`，该常量只用于 dataclass validation 不进入 DDL）
  - state.py:15-23 从 api.py 导入这些常量用于 `_validate_wait_record_for_insert` 等函数
  - schema.py DDL 使用本地定义的常量
- **影响**: 若常量被单独修改，DDL CHECK 与 dataclass validation 对同一字段使用不同长度上限，可能导致静默不一致——DDL 允许 dataclass 拒绝的值或反之
- **建议改法和验证点**: 
  方案 A（推荐）: 让 schema.py 从 api.py 导入这些常量（或抽取到共享常量模块），消除重复定义
  方案 B: 在 test_durable_schema.py 或 test_wait_record_state.py 增加常量一致性测试，断言 `schema.HOST_WAIT_ID_MAX_LENGTH == api.HOST_WAIT_ID_MAX_LENGTH` 等
  验证: `pytest tests/host/test_durable_schema.py -q -k constant` 通过
- **修复风险（低）**: 方案 A 可能改变模块导入方向（schema.py 当前不 import api.py），需确认不会引入循环依赖
- **严重程度（中）**: 当前值一致且 schema.py 是 DDL 单一真源，短期不构成功能缺陷；但缺乏自动漂移防护，长期维护风险为中

### 002-未修复-低-DDL CHECK 未强制 adapter_key 字符模式

- **入口/函数**: `_HOST_WAIT_RECORDS_DDL` 中 `adapter_key TEXT NOT NULL CHECK`
- **文件(行号)**: dayu/host/durable/schema.py:473-474
- **输入场景**: 绕过 dataclass 验证（例如直接执行 SQL INSERT）插入含非法字符的 adapter_key
- **实际分支**: DDL CHECK 仅执行 `length(adapter_key) BETWEEN 1 AND 128`，不检查字符集 `[A-Za-z0-9_.:-]`
- **预期行为**: DDL 防御层应尽可能与 dataclass 验证一致
- **实际行为**: DDL 不强制字符模式，仅 dataclass `WaitAdapterKey.__post_init__` 执行 `_WAIT_ADAPTER_KEY_PATTERN.fullmatch`
- **直接证据**: 
  - schema.py:473-474: `adapter_key TEXT NOT NULL CHECK (length(adapter_key) BETWEEN 1 AND {HOST_WAIT_ADAPTER_KEY_MAX_LENGTH})`
  - api.py:49: `_WAIT_ADAPTER_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")`
  - api.py:343: `if _WAIT_ADAPTER_KEY_PATTERN.fullmatch(self.value) is None: raise ValueError(...)`
- **影响**: 低——正常路径唯一通过 dataclass 构造，SQLite 不支持 regex CHECK 限制了 DDL 层能做的最强防御
- **建议改法和验证点**: SQLite 不支持 regex，当前 DDL 已是合理解的最大防御；可不修改，或使用 `GLOB` + 字符类限制（但 SQLite GLOB 不支持字符类集合与 `.` `:` `-` 的精确语义）。建议在 test_wait_record_state.py 中增加直接 SQL INSERT 后读取验证字符模式的测试
- **修复风险（低）**: 无需修改 DDL（SQLite 限制）
- **严重程度（低）**: DDL 防御层略弱但不构成安全漏洞；正常路径有 dataclass 防护

### 003-未修复-低-单条 wait record CAS_LOST 分支未被确定性测试覆盖

- **入口/函数**: `_wait_record_mutation_result` 的 `CAS_LOST` 返回分支
- **文件(行号)**: dayu/host/durable/state.py:4157-4168
- **输入场景**: 同一 transaction 内 UPDATE `WHERE status='waiting'` 返回 rowcount=0，但 re-read 发现该行状态仍为 `waiting`
- **实际分支**: 
  ```python
  if latest.status == WaitRecordStatus.WAITING:
      return WaitRecordMutationResult(status=StateMutationStatus.CAS_LOST, row=latest)
  ```
- **预期行为**: CAS_LOST 分支语义正确——在理论上并发事务竞态下需要区分 CAS 失败与状态已被其他事务变更
- **实际行为**: 单进程 SQLite transaction 内不可能发生此分支。实现 artifact 也承认："单条 wait record CAS helper 的 CAS_LOST 分支是并发事务竞态分支，当前单进程 deterministic 测试覆盖了 UPDATED、NOT_FOUND、INVALID_STATE"
- **直接证据**: 
  - test_wait_record_state.py:486-539 `test_wait_record_cas_helpers_update_waiting_only` 覆盖 UPDATED、INVALID_STATE、NOT_FOUND，不覆盖 CAS_LOST
  - state.py:4165-4168 的 CAS_LOST 分支
- **影响**: 低——分支逻辑正确，仅在多进程/多连接并发场景可触发；Plan §3.7 要求 `CAS_LOST` 为 CAS helper 返回状态之一
- **建议改法和验证点**: Plan §3.11 要求 "Tests must model race deterministically by invoking the two transactions in controlled order; do not use sleep-based race tests." P7-S4（WAITING Cancel, Late Result Diagnostic）的 race 测试可覆盖此分支。此处记录为已知未覆盖项，不阻塞 P7-S1
- **修复风险（低）**: 可在 P7-S4 通过独立连接的并发 transaction 确定性复现
- **严重程度（低）**: 分支逻辑正确，测试缺口在后继 slice 中有自然覆盖机会

## Open Questions

- 无。P7-S1 实现与 plan 一致，无需要 controller 裁决的阻塞问题。

## Residual Risk

- **常量漂移**: 如 Finding 001 所述，api.py 与 schema.py 重复定义 8 个长度常量，无自动同步机制。当前值一致，不阻塞 merge。
- **CAS_LOST 测试缺口**: 如 Finding 003 所述，单条 CAS helper 的竞态分支未被确定性测试覆盖。P7-S4 的 cancel-vs-resolve race 测试可自然覆盖。不阻塞 P7-S1。
- **DDL 字符模式**: 如 Finding 002 所述，adapter_key 字符模式仅在 dataclass 层验证。不阻塞 merge。
- **README 同步**: 按 plan P7-S5 文档切片处理，本 slice 未覆盖。不阻塞 P7-S1。
