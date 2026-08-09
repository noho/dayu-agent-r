# Code Review — WU-CLI-CONFORMANCE-F01-F07 S4/F04

## Scope

- Mode: current changes (uncommitted working tree)
- Branch: `codex/interactive-oracle`
- Base: `25400fba` (HEAD, `fix(cli): preserve graceful input cancellation`)
- PR: 190 (未提交 S4/F04 slice)
- Output file: `docs/reviews/wu-cli-conformance-f01-f07-s4-code-review-ds.md`
- Included scope:
  - `dayu/cli/session_execution.py` (working tree diff, 生产代码)
  - `tests/cli/test_interactive_command.py` (working tree diff, CLI owner tests)
  - `tests/host/test_session_attachment_registry.py` (working tree diff, Host owner tests)
  - `docs/reviews/wu-cli-conformance-f01-f07-s4-implementation-codex.md` (implementation artifact, 只读参考)
  - `docs/reviews/wu-cli-conformance-f01-f07-plan-codex.md` §6 (accepted plan, 只读参考)
  - `docs/host/design.md` (Host 设计真源, 只读参考)
- Excluded scope: 无；三个 changed files 与相关 design/plan 文档全覆盖。
- Parallel review coverage: 无；本 review 由单 reviewer 沿真实代码路径逐行走读。

### 验证基线

| 检查项 | 结果 |
|---|---|
| Focused pytest (204 targeted) | `204 passed, 3 warnings in 10.10s` |
| Focused pyright (3 changed files) | `0 errors, 0 warnings, 0 informations` |
| Accepted plan §6 contract 逐条对照 | 见下方 Findings |
| Implementation artifact claims 验证 | 见下方 Findings |
| Frozen oracle/scenario hash | 未变（本 slice 不修改 oracle/scenario） |

## Findings

### 1-未修复-中-`attachment_for_mutation()` close 失败后状态不一致且缺少测试覆盖

- **入口/函数**: `_InteractiveSessionAttachmentController.attachment_for_mutation()`
- **文件(行号)**: `dayu/cli/session_execution.py:432-440`
- **输入场景**: `refresh_required=True` 且 `self.current` 指向需关闭的旧 attachment；`close_current(previous)` 抛出异常（例如 Host 底层 mutex 释放失败、SQLite I/O 错误或网络断开导致的 remote attachment close 失败）。
- **实际分支**:
  ```python
  # line 433-436
  previous = self.current
  if previous is not None:
      await asyncio.shield(self.close_current(previous))  # 抛出异常
      if self.current is previous:  # 永不执行
          self.current = None
  ```
  异常穿透 `asyncio.shield` 向上传播。`self.current` 仍指向可能已部分关闭的 `previous`，`self.refresh_required` 保持 `True`。
- **预期行为**: close 失败后 controller 应进入确定状态：要么保持 `current` 不变且 `refresh_required` 不变（允许重试），要么将 `current` 清空并保持 `refresh_required`（要求下次重新 attach），二选一并显式文档化。无论哪种选择，后续 `close()` 不应在不知情的情况下重试关闭一个可能已部分关闭的 attachment。
- **实际行为**: 异常直接向上传播到 TTY driver 的 SUBMIT 处理路径（line 1754/1782），最终被 `execute_interactive_on_session` 的外层 `except BaseException` 捕获（line 827）。随后 `attachment_controller.close()` 在 finally 块中再次尝试关闭 `self.current`（line 841），对同一 attachment 发起第二次 `aclose()` 调用。若 Host attachment 的 `aclose()` 非严格幂等（例如原生 mutex 已释放但 SQLite record 未更新），存在 double-close 或资源泄漏风险。
- **直接证据**:
  - `attachment_for_mutation()` line 434: `await asyncio.shield(self.close_current(previous))` — shield 只防取消不防异常
  - line 435-436: `if self.current is previous: self.current = None` — 异常时永不执行
  - `close()` line 450-456: 从 `self.current` 读取并再次 close，无 "已尝试关闭" 标记
  - 测试 `test_interactive_read_only_then_composer_error_closes_without_double_close` (line 2764) 覆盖了 RO 后 composer 异常路径，但 close 本身未失败；不存在 `close_current()` 抛异常的测试用例
- **影响**: 在 Host attachment 底层 close 可能失败的异常场景下，同一 attachment 的 `aclose()` 可能被调用两次，行为取决于 Host 实现的幂等性保证。当前 Host 实现基于 native mutex + SQLite，close 失败概率极低，但 controller 作为通用组件不应依赖下游实现的幂等性承诺。
- **建议改法和验证点**:
  1. 在 `attachment_for_mutation()` 中 catch `close_current()` 异常，将 `self.current = None` 并将 `self.refresh_required` 保持为 `True`（下次 mutation 将重新 open_fresh），然后重抛原始异常或包装后抛出。
  2. 或在 `close_current()` 失败后设置内部 `_close_failed: bool` 标记，`close()` 方法检测该标记后跳过重试。
  3. 补充测试：注入会抛出异常的 `close_current` callback，验证 controller 状态收敛且 attachment 的 `aclose()` 恰好被调用一次。
- **修复风险（低）**: 改动仅影响 controller 内部状态管理，不改变正常路径行为；现有 204 个测试全部通过可保证无回归。
- **严重程度（中）**: 异常场景触发概率低（Host close 高度可靠），但 controller 作为资源生命周期管理者，在失败路径上的状态不一致违反其 docstring 声明的幂等语义，且无测试覆盖。

### 2-未修复-低-`_is_read_only_mutation_rejection()` 使用 `is` 进行 enum 身份比较

- **入口/函数**: `_is_read_only_mutation_rejection()`
- **文件(行号)**: `dayu/cli/session_execution.py:1639-1640`
- **输入场景**: `HostApiError.detail` 是 `HostSessionMutationErrorDetail` 的实例，但其 `reason` 或 `actual_mode` 字段由反序列化路径构造（例如从 JSON/dict 反序列化、或从远程 Host 的 wire protocol 还原），此时 enum 字段值是字符串而非 enum 成员。
- **实际分支**:
  ```python
  detail.reason is HostSessionMutationRejectionReason.READ_ONLY  # False（字符串 != enum 成员）
  ```
  函数返回 `False`，CLI 将 READ_ONLY 拒绝视为未分类的 `HostApiError` 并走 fatal 路径。
- **预期行为**: 只要 `reason` 的值等于 `READ_ONLY`，无论其 Python 类型是 enum 成员还是等值字符串，都应被识别为 READ_ONLY 拒绝。
- **实际行为**: `is` 要求同一对象身份；反序列化产生的等值但不同对象的 enum 值会导致匹配失败。当前 Host 生产代码全部使用 enum 成员构造 error detail，因此实际不会触发。但该函数处于 CLI 防御性分派的关键路径——其职责就是精确判定 Host 错误是否应保留 REPL——使用身份比较而非值比较引入了对 Host 实现细节的隐式依赖。
- **直接证据**:
  - line 1639: `detail.reason is HostSessionMutationRejectionReason.READ_ONLY`
  - line 1640: `detail.actual_mode is HostSessionAccessMode.READ_ONLY`
  - 测试 `test_interactive_only_swallows_exact_typed_read_only_detail` (line 2794) 使用 `_ReadOnlyRetryHost` 以 enum 成员构造 error detail，未覆盖反序列化输入
- **影响**: 仅在 Host error detail 来自反序列化路径时触发；当前不存在该路径，但这是 CLI 防御性分派的隐式契约，而非显式文档化约束。
- **建议改法和验证点**:
  1. 将 `is` 改为 `==`（StrEnum 的 `==` 支持与字符串比较）。
  2. 或保持 `is` 但在函数 docstring 显式声明"要求 Host 使用 enum 成员构造 error detail"，并在 Host API contract 中明确此约束。
  3. 补充反例测试：构造 `reason` 为等值字符串的 `HostSessionMutationErrorDetail`，验证精确拒绝不被识别为 READ_ONLY（文档化当前行为）或改为被正确识别（行为变更）。
- **修复风险（低）**: `==` 替换 `is` 是向后兼容的（enum 成员 `==` 等值字符串返回 True）。
- **严重程度（低）**: 当前生产路径不会触发，但作为防御性分派的关键判断，隐式身份依赖不如显式值比较健壮。

### 3-未修复-低-`_InteractiveSessionAttachmentController.close()` docstring 与实际行为在失败路径上不一致

- **入口/函数**: `_InteractiveSessionAttachmentController.close()`
- **文件(行号)**: `dayu/cli/session_execution.py:442-457`
- **输入场景**: `close()` 被调用且 `self.current is not None`，但 `close_current(current)` 抛出异常。
- **实际分支**:
  ```python
  # line 453-456
  if current is not None:
      await asyncio.shield(self.close_current(current))  # 抛异常
      if self.current is current:  # 不执行
          self.current = None
  # self._closed = True  # 不执行
  ```
  异常传播后 `_closed` 仍为 `False`，`self.current` 保持不变。
- **预期行为**: docstring 声明"幂等关闭 controller 当前仍存活的 attachment 一次"。有两种合理解读：(a) "一次性"关闭——无论如何只尝试一次，失败也标记为已关闭；(b) "幂等"关闭——多次调用效果相同，失败不标记已关闭以允许重试。当前实现在失败时走 (b) 路径，但 docstring "一次" 暗示 (a)。
- **实际行为**: 失败时 `_closed` 保持 `False`，后续 `close()` 调用会重试。从 `execute_interactive_on_session` outer lifecycle 看，`close()` 只在 finally 块调用一次（line 841），因此重试行为不会触发。但如果未来代码在循环或重试逻辑中多次调用 `close()`，行为将与 docstring 暗示不一致。
- **直接证据**:
  - line 442-457: `_closed = True` 仅在方法末尾无异常时执行
  - line 841: outer lifecycle 仅调用一次 `attachment_controller.close()`
  - docstring line 442: "幂等关闭 controller 当前仍存活的 attachment 一次"
- **影响**: 当前调用模式不受影响。风险在于未来维护者根据 docstring 假设 close 后 controller 必然处于 closed 状态，而实际可能不是。
- **建议改法和验证点**:
  1. 更新 docstring 明确失败语义："幂等关闭；若底层 close 失败则允许重试，调用方应在最后一次尝试后不再使用 controller"。
  2. 或改变实现使 `_closed = True` 在 finally 块中设置（无论如何标记已尝试关闭），使 docstring 的 "一次" 语义成立。
- **修复风险（低）**: 仅为 docstring 或内部状态标记调整。
- **严重程度（低）**: 当前调用模式不受影响，仅 docstring 与实现间的语义不一致。

## Verified Correctness（逐项确认）

以下为 review 命令要求逐项验证的关键行为，均通过直接代码路径走读和测试证据确认正确：

### Attachment controller close/open 与 idempotent cleanup
- `close()` 方法通过 `_closed` 标志保证幂等：第二次调用直接返回（line 450-451）。✓
- `close()` 使用 `asyncio.shield` 防止取消中断 close 操作（line 454）。✓
- Outer lifecycle 在 finally 块中恰好调用一次 `close()`（line 841），且将 close 异常合并到 cleanup_error 链（line 842-846）。✓
- 测试 `test_interactive_repeated_read_only_keeps_identity_and_eof_closes_current` 断言 `[attachment.close_count for attachment in host.attachments] == [1, 1]`（line 2705），证明每个 attachment 恰好关闭一次。✓
- 测试 `test_interactive_read_only_then_composer_error_closes_without_double_close` 断言 composer 异常后 `close_count == [1]`（line 2790），证明异常路径无 double-close。✓

### Mode 绝不原地变化
- `_InteractiveSessionAttachmentController` 不持有 `access_mode` 字段，不修改 attachment mode。✓
- `require_refresh()` 仅设置 `refresh_required = True`（line 414）。✓
- `attachment_for_mutation()` 通过 close-before-open 获取 fresh attachment（lines 432-439），mode 由 Host fresh attach 返回。✓
- Host test `test_real_same_label_dual_attachment_rejects_read_only_without_durable_run` 断言 owner 退出后 observer mode 仍为 `READ_ONLY`（line 397），且旧 attachment mode 不可变（line 379）。✓

### READ_ONLY typed detail 精确匹配且不吞其它 Host 错误
- `_is_read_only_mutation_rejection()` 同时检查 `kind == "session_mutation_access"`、`reason is READ_ONLY`、`actual_mode is READ_ONLY`（lines 1636-1641）。✓
- 不使用 message 字符串匹配。测试 `test_interactive_only_swallows_exact_typed_read_only_detail` 构造 `reason=ATTACHMENT_REQUIRED` 的 error，断言该错误保持 fatal 而不被吞（lines 2811-2821），且 `_submit_index == 0`（line 2826）。✓
- RO rejection handler 在重抛前检查 `accepted_run_id is not None`（line 1882-1884），确保不会误吞已接受但后续失败的异常。✓

### Composer ack/history 严格在 accepted callback 后
- Composer `accept_submit(record_history=True)` 仅在 `current_acceptance_task` 完成时调用（line 1829）和 `queued_acceptance_task` 完成时调用（line 1838）。✓
- 两个 acceptance 处理块都先检查 `barrier.accepted.is_set()`（lines 1824, 1833），确保 Host acceptance callback 已触发。✓
- RO 拒绝路径从不调用 `composer.accept_submit()`；仅设置 `composer.set_phase(InteractiveComposerPhase.IDLE)`（line 1897）。✓
- 测试 `test_interactive_read_only_retry_preserves_composer_and_uses_fresh_rw` 断言首次 RO 后 `composer._history.get_strings() == []`（line 2628），第二次 accepted 后 `composer._history.get_strings() == ("abc",)`（line 2634）。✓

### Pending mutation 同 draft/revision 复用 request id，编辑后新 identity
- `_InteractivePendingMutation.same_semantic_submission()` 比较 `draft` 和 `draft_revision` 精确相等（lines 480-489）。✓
- `_new_interactive_pending_mutation()` 创建时冻结 `client_request_id`（line 1620-1623），后续复用不重新生成。✓
- TTY driver SUBMIT handler：若 pending 存在且 same_semantic → 复用；否则新建并递增 `next_turn_index`（lines 1742-1753, 1770-1781）。✓
- 测试 `test_interactive_read_only_retry_preserves_composer_and_uses_fresh_rw` 断言 `request_ids[0] == request_ids[1]`（line 2644）。✓
- 测试 `test_interactive_edit_after_read_only_allocates_new_turn_identity` 断言 `requests[0].client_request_id != requests[1].client_request_id`（line 2756），且分别以 `turn-1` 和 `turn-2` 结尾（lines 2757-2758）。✓

### Submit task acceptance/exception 竞态
- `_ActiveTurnCloseout.publish_accepted()` 处理首次发布（幂等）、同 id 重复（静默忽略）、不同 id（raise ValueError）（lines 191-206）。✓
- `_ActiveTurnCloseout.observe_terminal()` 检查 terminal run_id 与 accepted_run_id 冲突（lines 342-344），且重复 terminal 幂等（lines 348-350）。✓
- `wait_accepted_then_cancel()` 处理 terminal 先于 acceptance 到达的竞态（lines 322-323），不从迟到 cancel 覆盖真实 terminal。✓
- 测试 `test_interactive_read_only_retry_preserves_composer_and_uses_fresh_rw` 证明 accepted 后 `host._submit_index == 1`（line 2645），恰好一个 Run。✓
- 测试 `test_real_same_label_dual_attachment_rejects_read_only_without_durable_run` 证明 RW submit 后 `run_count_before + 1`（lines 412-418）。✓

### A 退出前后 fresh attach 真实单 writer
- Host test `test_real_same_label_dual_attachment_rejects_read_only_without_durable_run` 使用真实 `open_host`（line 347），非 fake/fixture。✓
- 测试证明：A 关闭后 B1 mode 不变（line 397），B1 关闭后 fresh B2 获得 RW（line 402），复用相同 `request` 提交后只有一个新 Run（lines 412-418）。✓
- 直接查询 SQLite `TABLE_HOST_RUNS` 和 `TABLE_EVENT_LOG`（lines 363-369, 380-393, 412-425），不使用 fake 计数器自证。✓

### Outer exception/EOF/terminal 无 leak/double-close
- `execute_interactive_on_session` cleanup 顺序：sigint_monitor → display → attachment_controller（lines 830-846）。✓
- Primary error 与 cleanup error 通过 `_raise_lifecycle_primary` 正确串接（line 848）。✓
- 测试 `test_interactive_read_only_retry_preserves_composer_and_uses_fresh_rw` 断言完整 timeline（lines 2646-2653），证明 B1 和 B2 各关闭一次，outer terminal cleanup 正确。✓
- 测试 `test_interactive_read_only_then_composer_error_closes_without_double_close` 断言异常传播且 close_count == [1]（lines 2777-2790）。✓
- 测试 `test_interactive_repeated_read_only_keeps_identity_and_eof_closes_current` 断言两次 RO 后 EOF 正常返回 EXIT_SUCCESS，attachment 各关闭一次（lines 2698-2705）。✓

### Run/EventLog count 使用真实 Host
- `test_real_same_label_dual_attachment_rejects_read_only_without_durable_run` 通过 SQLite 直接查询验证：RO 拒绝零 Run/EventLog 写入（lines 380-393），RW 接受后恰好 +1 Run 且 EventLog 增加（lines 412-425）。✓
- 不使用 fake counter、内存计数或 CLI 层面的 submit_index 自证。✓

### Acceptance barrier 的 duplicate acceptance
- `_AcceptedRunBarrier.publish_accepted()` 同 id 幂等（line 201-204），不同 id 冲突报错（lines 205-206）。✓
- `_ActiveTurnCloseout.publish_accepted()` 直接委托 barrier（line 272）。✓

### 未覆盖的理论竞态
- **Queued followup + RO 竞态**: 若 active turn 期间创建了 queued followup，且 active turn 被 RO 拒绝，queued 的 submit_task 使用旧 RO attachment 提交但不在 wait_tasks 中。queued_acceptance_task 会永远等待（Host 不 accept RO mutation）。然而，分析证明此路径当前不可达：`composer_task` 在 mutation 期间为 None（line 1947-1948 中 `mutation_waiting_acceptance=True` 阻止 composer 重建），用户无法在 active turn 等待期间提交新输入。queued 只有在 `current.submit_task` 完成且被处理后才能创建——但到那时要么已 accepted（current terminal 正常处理），要么已 RO 拒绝（current=None，走 `elif current is None` 分支创建新 current 而非 queued）。**结论**: 此竞态当前架构下不可达，但状态机未显式防御；若未来 driver 架构变化（如 composer 始终后台读取），需补充防御。

## Open Questions

1. `_is_read_only_mutation_rejection()` 使用 `is` 进行 enum 身份比较是否是显式设计决策（要求 Host 端必须使用 enum 成员构造 error detail）？若 Host API contract 已明确此约束则无需修改；否则建议改为 `==` 以提高健壮性。
2. `_InteractiveSessionAttachmentController.close()` 在 close 失败时不设置 `_closed=True` 的行为是否被 outer lifecycle 的"只调用一次"语义所依赖？若未来出现多次 close 调用场景，需明确失败语义。

## Residual Risk

- **Close 失败路径无测试覆盖**: 三次测试均验证正常 close 路径的 close_count，但不存在 `aclose()` 本身抛异常的测试。在 Host attachment close 高度可靠（native mutex + SQLite）的背景下实际风险低，但作为资源管理组件缺少异常路径覆盖。
- **Queued + RO 竞态**: 当前不可达但无显式断言或防御代码；若 driver 架构变化需重新评估。
- **Real concurrent CLI evidence (S8)**: 本 slice 的 Host test 覆盖了同进程双 opener 场景，但真实两独立 CLI 进程的 owner 退出时序、PTY screen 文本和完整 evidence bundle 由已批准 S8 覆盖。当前 slice 在 owner boundary 层面无遗漏。
- **`is` vs `==` enum 比较**: 当前 Host 实现保证安全，但若 Host error detail 构造方式变化，CLI 的 READ_ONLY 检测将静默失效（走 fatal 路径而非保留 REPL）。建议在 Host API contract 或本函数 docstring 中显式化该约束。

## Verdict

S4/F04 实现严格遵循 accepted plan §6 的 typed contract：attachment controller 不修改 mode、composer ack 严格在 Host acceptance callback 之后、pending mutation 正确复用/更新 request identity、typed READ_ONLY 精确匹配且不吞其它错误、Run/EventLog count 使用真实 Host durable store 验证、outer lifecycle 无 leak/double-close。

三个 findings 均为低-中严重程度，涉及异常路径状态一致性、防御性分派的隐式身份依赖和 docstring 语义对齐，均不阻塞 merge。204 个 targeted tests 全部通过，pyright 零错误。

**建议**: 修复 Finding 1（`attachment_for_mutation()` close 失败状态）以提高异常路径健壮性；Finding 2 和 Finding 3 可在后续维护中按优先级处理。
