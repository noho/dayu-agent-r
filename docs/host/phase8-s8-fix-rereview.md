# Host P8-S8 Fix Re-Review：Durable Conversation Memory Store

- **Branch**: `migration/host-p8-attempt-lease-recovery`
- **Baseline**: `90f5c5d host: add p8 multiprocessing stress tests`
- **Re-review date**: 2026-05-09
- **Reviewer**: Host P8-S8 Fix Re-Review Agent (Claude)
- **Re-review scope**: 两份并行 code review (`phase8-s8-code-review.md` / `phase8-s8-code-review-2.md`) 的 accepted findings 修复验证

## 结论：PASSED — 四项 accepted findings 全部 fixed，无新 blocker

P8-S8 两份并行 code review 的四项 accepted findings 已全部修复到位，两份 review artifact 状态一致、无 pending-controller-decision、无互相矛盾。允许进入 user confirmation + commit gate。

---

## 验证结果

| 检查项 | 命令 | 结果 |
|--------|------|------|
| P8 durable memory recovery 测试 | `pytest tests/host/test_phase8_durable_memory_recovery.py -q` | 7 passed |
| P3/P6 memory + boundary + harness 回归 | `pytest tests/host/test_phase3_conversation_memory_projection.py tests/host/test_phase6_memory_rebuild.py tests/host/test_phase3_boundary.py tests/host/test_phase6_durable_harness_integration.py tests/host/test_phase6_review_fixes.py -q` | 52 passed |
| 类型检查 | `python -m pyright dayu/host tests/host utils` | 0 errors / 0 warnings / 0 informations |
| 空白错误 | `git diff --check` | clean |
| alias 残留扫描 | `rg -n "FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore\|InMemoryConversationMemoryStore(" tests/host` | 无命中（仅 `test_phase3_boundary.py:448` 在 forbidden set 断言中引用字符串，非 alias/构造调用） |
| 文档表名扫描 | `grep -n "session_memory\|session_memory_events" docs/host/migration-plan.md` | 无命中 |
| lazy import 残留扫描 | `grep -n "noqa: E402\|循环友好惰性" dayu/host/_conversation_memory_durable.py` | 无命中 |
| utils → tests 反向依赖扫描 | `grep -n "from tests.host._memory_store_fake" utils/ -r` | 无命中 |
| production InMemory 残留扫描 | `grep -n "InMemoryConversationMemoryStore" dayu/host/ -r` | 仅 `_run_harness.py` 中的 RuntimeError 消息和 docstring 说明，无 class/import/call 残留 |

---

## Accepted Findings 逐项复审

### F1 — 表名文档错误 → fixed

**原 finding**: `migration-plan.md:73-74` 写 `session_memory + session_memory_events`，但代码只用 `host_conversation_memory_snapshots` 单表。

**复审证据**:
- `migration-plan.md:74` 当前文本：`（单表 host_conversation_memory_snapshots 保存 JSON snapshot）`
- `grep "session_memory\|session_memory_events" docs/host/migration-plan.md` → 无命中
- `_conversation_memory_durable.py:77` 定义 `_TABLE_NAME: str = "host_conversation_memory_snapshots"`，与文档一致

**结论**: **fixed**。文档已改为真实表名，无残留。

---

### F2 — `_conversation_memory_durable.py` lazy import → fixed

**原 finding**: 模块中部 `_project_canonical_events` 使用 `# noqa: E402` lazy import，注释称"循环友好惰性"，但无循环依赖。

**复审证据**:
- `_conversation_memory_durable.py:56`：`_project_canonical_events` 已在模块顶部批量导入中（与 `_project_canonical_events` 同源的 18 个符号一起导入）
- `grep "noqa: E402\|循环友好惰性" _conversation_memory_durable.py` → 无命中
- `_conversation_memory.py` 不 import `_conversation_memory_durable.py`，无循环依赖
- pyright 0 errors，import 顺序合法

**结论**: **fixed**。`_project_canonical_events` 已移至顶部批量导入，mid-file lazy import 和 `# noqa: E402` 已删除。

---

### F3 — `utils` smoke 依赖 `tests.host` fake → fixed

**原 finding**: 4 个 `utils/smoke_host_*.py` import `tests.host._memory_store_fake`。

**复审证据**:
- `utils/smoke_host_conversation_memory.py:64`：`from utils._smoke_memory_store import SmokeInMemoryConversationMemoryStore`
- `utils/smoke_host_eventlog.py:61`：同上
- `utils/smoke_host_multiturn_no_governance.py:116-117`：同上
- `utils/smoke_host_tool_runtime.py:56`：同上
- `grep "from tests.host._memory_store_fake" utils/ -r` → 无命中
- `utils/_smoke_memory_store.py` 定义 `SmokeInMemoryConversationMemoryStore`，明确 smoke-only 命名
- `dayu/host/` production 包未重新出现 `InMemoryConversationMemoryStore` 实现或导出
- `tests/host/_memory_store_fake.py:8` docstring 已更新为"``utils/`` smoke 不得 import 本模块；smoke 私有 fake 见 ``utils/_smoke_memory_store.py``"

**结论**: **fixed**。smoke 已迁移到 `utils/_smoke_memory_store.SmokeInMemoryConversationMemoryStore`，不再 import `tests.host._memory_store_fake`，production `dayu/host` 无 InMemory 残留。

---

### F4 — 测试 alias 误导 → fixed

**原 finding**: 测试中 `FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore` alias 与裸 `InMemoryConversationMemoryStore()` 构造残留。

**复审证据**:
- `rg -n "FakeInMemoryConversationMemoryStore as InMemoryConversationMemoryStore" tests/host` → 无命中
- `rg -n "InMemoryConversationMemoryStore\(" tests/host` → 无命中（所有构造调用已改为 `FakeInMemoryConversationMemoryStore()`）
- `test_phase3_boundary.py:448` 中 `InMemoryConversationMemoryStore` 出现在 forbidden set 字符串断言中（验证 production 导出已移除），非 alias/构造调用，符合期望
- `test_phase8_durable_memory_recovery.py:444` 的残留扫描测试验证 production `dayu/` 不再导出该类

**结论**: **fixed**。alias 已删除，所有测试直接使用 `FakeInMemoryConversationMemoryStore` 原名。

---

## Review Artifacts 状态一致性

| 检查项 | `phase8-s8-code-review.md` | `phase8-s8-code-review-2.md` | 一致性 |
|--------|---------------------------|------------------------------|--------|
| F1 表名 | accepted — fixed | accepted — fixed | ✅ |
| F2 lazy import | accepted — fixed | accepted — fixed | ✅ |
| F3 utils→tests | accepted — fixed | accepted — fixed | ✅ |
| F4 test alias | accepted — fixed | accepted — fixed | ✅ |
| F5 deferred | deferred-with-owner: P9 | deferred-with-owner: P9 | ✅ |
| pending-controller-decision | 无 | 无 | ✅ |
| 互相矛盾 | — | — | 无 |

两份 artifact 的 F1-F4 修复状态标注一致，F5 均为 `deferred-with-owner: P9`。Review #2 的 F3 说明（controller 采用 utils 私有 helper 方案）与 Review #1 的 F4 说明（controller 决策）互相补充、不矛盾。

---

## 新 Blocker

无。

---

## Residual Risks 与 Owner

| Risk | Owner | 备注 |
|------|-------|------|
| partial drain + crash recovery 测试补强 | P9 advisory | F5 deferred：drain 已部分完成后崩溃 + reconcile 补齐路径未直接覆盖 |
| non-empty turns/facts JSON roundtrip 测试补强 | P9 advisory | F5 deferred：当前 roundtrip 测试 `recent_raw_turns` / `tool_facts` 为空元组 |
| `startup_reconcile` 自动 wire 进生产 Host 启动路径 | P9 / Session lifecycle | 显式入口已存在，P9 需自动装配 |
| `AttemptSupervisor.recover_stale_attempts` 自动 wire | P9 / Session lifecycle | 不阻塞 S8 |
| 慢硬盘 + Docker Linux 重压版多进程 stress | issue #38 | 不阻塞 S8 |
| 两个进程并发 `startup_reconcile` 安全 | P8-S7 review F2 advisory | 不阻塞 S8 |
| `_build_default_harness()` 的 `:memory:` HostStorage 无 close 路径 | P9 | `:memory:` 连接进程退出自动清理，长期建议增加 close 语义 |

---

## 建议

1. **F1-F4 全部 fixed**，修复干净、无残留。
2. **F5 deferred-with-owner: P9**：partial drain + crash recovery 与 non-empty turns/facts roundtrip 测试补强不阻塞 S8。
3. 修复后验证全量通过：`pytest tests/host -q` 291 passed + `pyright 0 errors` + `git diff --check clean`。
4. **允许进入 user confirmation + commit gate**。
