# Code Review

## Scope

- Mode: PR
- PR: 58
- PR URL: https://github.com/noho/dayu-agent-r/pull/58
- Title: Host Phase 8 Projection Core and Event Stream
- Author: noho
- Base: main
- Head: feat/host-phase8-projection-core-event-stream
- Output file: docs/reviews/pr-58-review-mimo-20260516.md
- Included scope: PR 58 相对 main 的完整 diff，覆盖 Phase 8 projection core、Host event stream cursor truth、minimal read model/repair、runtime filelock、public API event_class 变更、durable schema 变更与全部测试
- Excluded scope: Engine 代码、UI/Service 层、业务工具实现
- Parallel review coverage: 无（主线程直接 review）

## Findings

### 1-未修复-低-`RuntimeFileLockToken.release()` 后 marker restore 吞掉全部异常

- **入口/函数**: `RuntimeFileLockToken.release()` -> `_ensure_lock_file_marker_exists()`
- **文件(行号)**: `dayu/runtime/filelock.py:105-108`
- **输入场景**: 任何 acquire-release 正常路径；release 成功后尝试 `lock_path.touch(exist_ok=True)` 恢复 marker 文件
- **实际分支**: `_ensure_lock_file_marker_exists` 内 `lock_path.touch()` 抛出 `OSError`（如权限不足、磁盘满、路径被删除）
- **预期行为**: release 已成功完成，marker restore 是防御性 best-effort；异常应被吞掉或记录 diagnostic，不阻断调用方
- **实际行为**: `except Exception: pass` 吞掉全部异常，包括 `PermissionError`、`OSError` 等真实错误。调用方无法感知 marker 恢复失败。同时，如果 lock file 在 release 和 touch 之间被删除，touch 会重新创建空文件，可能误导后续锁使用者
- **直接证据**: `dayu/runtime/filelock.py:105-108` — `try: _ensure_lock_file_marker_exists(self.lock_path) except Exception: pass`
- **影响**: 低。marker 文件仅用于第三方 `filelock` 可见性，不影响 Host durable truth 或 EventLog ordering。但静默吞异常可能在生产环境掩盖磁盘/权限问题
- **建议改法和验证点**: 将 `except Exception: pass` 改为 `except OSError: pass`（只吞文件系统错误），或保留 `except Exception: pass` 但添加 logging。当前行为不阻塞 merge
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-`_ensure_lock_file_marker_exists` 是冗余操作

- **入口/函数**: `RuntimeFileLockToken.release()` -> `_ensure_lock_file_marker_exists()`
- **文件(行号)**: `dayu/runtime/filelock.py:285-296`
- **输入场景**: 正常 release 路径，第三方 `FileLock.release()` 已成功执行
- **实际分支**: `lock_path.touch(exist_ok=True)` 尝试确保 marker 文件存在
- **预期行为**: 第三方 `filelock` 的 `release()` 不删除 lock marker 文件；marker 应该已经存在
- **实际行为**: `touch(exist_ok=True)` 对已存在的文件是 no-op。如果文件不存在（被外部删除），touch 会创建空文件，但这不是 lock marker 的正确语义——空文件不等于被第三方 lock 库持有的 marker
- **直接证据**: `dayu/runtime/filelock.py:105-108` 与 `dayu/runtime/filelock.py:285-296`
- **影响**: 低。代码意图是防御性保护，但实际效果有限。不影响正确性
- **建议改法和验证点**: 如果这是 Phase 8 full-repo deepreview fix 的一部分，可以确认是否有明确理由保留；否则可移除以简化代码
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无。

## Residual Risk

1. **Projection runner 并发**: 当前实现每次 `run_once` 对每个 EventLog row 使用独立 write transaction。如果未来有多个 projection runner 进程同时处理同一个 consumer，`advance_projection_checkpoint` 的 "cannot move backwards" 检查会阻止第二个 runner 推进，但第二个 runner 的 consumer write 已在同一事务中提交，导致 checkpoint 和 consumer write 不一致。当前 Phase 8 只有单进程单 runner 场景，此风险不阻塞 merge。
2. **Schema version 升级**: `HOST_SCHEMA_VERSION` 从 4 升至 5，bootstrap 只做 fresh DB 创建。已有 DB 需要用户手动重建。这是设计约束（全新 schema 起库），不是缺陷。
3. **Repair `batch_size` 无上限**: `repair_minimal_read_models` 接受任意正整数 `batch_size`，如果传入极大值会导致单次 replay 扫描过多 EventLog rows。当前只由测试和内部代码调用，不暴露为 public API，风险低。
4. **`HostEventClass` 与 `EventClass` 映射**: `_event_view_from_row` 通过 `HostEventClass(row.event_class.value)` 做 enum 值映射。如果未来 `EventClass` 新增成员但 `HostEventClass` 未同步，会抛出 `ValueError`。当前两组 enum 成员完全一致，风险低。
5. **Tests 覆盖**: projection runner 测试覆盖了过滤、排序、checkpoint 提交、failure rollback、payload 解析错误、duplicate 和 failure 清除。event stream 测试覆盖了 run 过滤、event class 暴露、projection checkpoint lag 不影响 stream、projection failure 不影响 stream、cursor 推进和 limit 校验。read model 测试覆盖了 terminal event identity 冲突、rebuild 一致性和 repair 循环。filelock 测试覆盖了 parent directory、context manager、幂等 release 和 timeout 包装。未发现重大测试缺口。
