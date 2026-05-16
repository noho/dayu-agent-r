# Code Re-Review — P7-S1 Fix Pass

## Scope

- Mode: current changes (uncommitted diff) — fix pass for P7-S1 code review findings
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- Output file: docs/reviews/host-phase7-code-re-review-s1-ds-20260516.md
- Prior review: docs/reviews/host-phase7-code-review-s1-ds-20260516.md
- Adjudication: docs/reviews/host-phase7-code-review-s1-controller-adjudication-20260516.md
- Fix artifact: docs/reviews/host-phase7-fix-s1-public-contracts-wait-record-20260516.md
- Included scope:
  - dayu/host/durable/schema.py: import wait length constants from api.py, updated snapshot group DDL CHECK
  - tests/host/test_wait_record_state.py: orphan snapshot_digest DDL rejection test
- Excluded scope:
  - public API (api.py), state helpers (state.py), ToolRuntime, plan, design/control docs, commits, branches, PRs
- Parallel review coverage: 无

## Findings

### S1-F1 — 已修复 — 长度常量从 api.py 统一导入

- **原始 finding**: DS-001 / MiMo-1，`dayu/host/api.py` 与 `dayu/host/durable/schema.py` 重复定义 8 个 wait length constants
- **修复**: `schema.py:12-21` 从 `dayu.host.api` 导入全部 8 个 wait length constants，删除本地重复定义
- **验证证据**:
  - schema.py:12-21：`from dayu.host.api import (HOST_WAIT_ADAPTER_KEY_MAX_LENGTH, ...)`
  - schema.py 中不再出现 `HOST_WAIT_*_MAX_LENGTH = ...` 本地赋值
  - 导入方向正确：api.py 是公共常量层，不依赖 schema.py，无循环依赖
  - DDL CHECK 中 `${HOST_WAIT_ID_MAX_LENGTH}` 等引用现在直接来自 api 常量
- **状态**: 已关闭

### S1-F2 — 已修复 — snapshot_digest 孤儿值 DDL 防御

- **原始 finding**: MiMo-2，DDL CHECK 允许 `snapshot_digest` 在 `snapshot_ref` 和 `snapshot_captured_at` 均为 NULL 时非空（orphan digest 未被拒绝）
- **修复**: DDL CHECK 改为三列全 NULL 或 `snapshot_ref` + `snapshot_captured_at` 均非 NULL（`snapshot_digest` 可为 NULL）
- **验证证据**:
  - schema.py 中 DDL CHECK（源自 `_HOST_WAIT_RECORDS_DDL`）：
    ```sql
    CHECK (
        (snapshot_ref IS NULL
          AND snapshot_captured_at IS NULL
          AND snapshot_digest IS NULL)
        OR
        (snapshot_ref IS NOT NULL AND snapshot_captured_at IS NOT NULL)
    )
    ```
  - `test_wait_record_ddl_rejects_orphan_snapshot_digest`（test_wait_record_state.py:486-571）：直接 SQL INSERT `snapshot_ref=NULL, snapshot_captured_at=NULL, snapshot_digest=_SNAPSHOT_DIGEST`，断言 `HostDurableError` 匹配 "CHECK constraint"
- **状态**: 已关闭

### S1-F3 未误修 — adapter_key regex DDL 未被添加

- **原始 finding**: DS-002，DDL 强制 adapter_key 字符模式
- **裁决**: rejected
- **验证**: schema.py DDL 中 `adapter_key TEXT NOT NULL CHECK` 仍仅包含 `length(adapter_key) BETWEEN 1 AND ...`，无字符模式 regex / GLOB 约束
- **状态**: 确认未误修

### S1-F4 未误修 — CAS_LOST race test 未被添加

- **原始 finding**: DS-003，单条 CAS_LOST 分支未被确定性测试覆盖
- **裁决**: deferred to P7-S4
- **验证**: test_wait_record_state.py 中 `test_wait_record_cas_helpers_update_waiting_only` 仍仅覆盖 UPDATED / INVALID_STATE / NOT_FOUND，无新增 CAS_LOST 相关测试函数或断言
- **状态**: 确认未误修

## Open Questions

无。

## Residual Risk

- S1-F3（adapter_key 字符模式 DDL）: rejected，无变化。正常写入路径仍有 dataclass 防护。
- S1-F4（CAS_LOST deterministic coverage）: deferred to P7-S4，无变化。当前 slice 已覆盖 UPDATED / NOT_FOUND / INVALID_STATE。
- 修复 pass 未引入新风险；仅修改 schema.py 的常量来源与一个 DDL CHECK 约束，以及一个针对该 CHECK 的测试。

## Conclusion

PASS。两项 accepted findings（S1-F1、S1-F2）已正确关闭；两项 rejected/deferred findings（S1-F3、S1-F4）未被误修；未引入新缺陷。
