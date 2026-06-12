# WU-RET-00 Aggregate Deepreview Fix Re-Review — DS

## Scope

- **Re-review 对象**: AgentCodex 针对 DS aggregate deepreview Finding 001 与 Open Question Q1 的 docstring 修复
- **输入 artifact**:
  - `docs/reviews/wu-ret-00-aggregate-deepreview-ds.md`（原始 DS deepreview）
  - `docs/reviews/wu-ret-00-aggregate-deepreview-fix-codex.md`（Codex fix artifact）
- **被修复文件**: `dayu/host/api.py`、`dayu/host/open_host.py`
- **当前 gate**: re-review
- **Re-review 日期**: 2026-06-12
- **Re-reviewer**: AgentDS

### Re-review method

1. 逐行对比 DS Finding 001 + Q1 的修复要求与 git diff 实际改动
2. 验证 docstring 是否准确描述完整行为空间（dry-run + opt-in destructive）
3. 确认 raises 描述不再暗示存在"不支持的 destructive reclaim"分支
4. 确认无行为代码、类型签名、公共 API、测试断言的范围外改动
5. 验证 fix artifact 与 diff 实际内容自洽

## Findings

### 无 blocking finding

经过逐行对比 git diff 与 DS Finding 001 / Q1 的修复要求：

**Finding 001 修复验证（通过）**:

| 检查项 | 状态 | 证据 |
|---|---|---|
| 移除 "dry-run" 单一行为概括 | ✅ | `api.py:3323`: `执行 Host storage maintenance。`（原 `执行 Host storage maintenance dry-run。`） |
| 明确默认 dry-run 不删除文件 | ✅ | `api.py:3326-3328` 和 `open_host.py:529-531`: `默认 dry-run 不删除文件；当 request.reclaim_orphan_artifacts 为 True 时，会执行破坏性 orphan artifact 回收。` |
| 说明 opt-in destructive 行为 | ✅ | 同上——明确 `reclaim_orphan_artifacts=True` 触发破坏性回收 |
| :returns 移除 "dry-run" 前缀 | ✅ | 两处均改为 `maintenance 结果。` |
| open_host.py 同步修复 | ✅ | `open_host.py:528-536` 与 `api.py` 一致 |

**Open Question Q1 修复验证（通过）**:

| 检查项 | 状态 | 证据 |
|---|---|---|
| 移除 "不支持的 destructive reclaim 请求失败时抛出" | ✅ | `api.py:3332`: 原措辞完全移除 |
| 替换为准确的 raises 描述 | ✅ | `api.py:3332-3333`: `maintenance 读取、扫描、checkpoint 或 orphan artifact 回收失败时抛出。` |
| open_host.py raises 同步更新 | ✅ | `open_host.py:535-536`: 新增 "或 orphan artifact 回收"，与 api.py 对齐（原 open_host.py 缺少 reclaim 相关 raises 说明） |

**raises 语义准确性补充验证**:

`orphan artifact 回收失败时抛出` 的措辞与实现语义一致：
- `_reclaim_orphan_artifacts_if_requested`（`storage_maintenance.py`）中，单文件删除失败以 `HostStorageMaintenanceFileError` 收集在 result 中返回，不 raise
- 若 reclaim 过程中出现系统级错误（如写事务失败、OSError），由外层 `except OSError` 映射为 `HostApiError(INTERNAL_ERROR)`
- 因此 "回收失败" 正确指向 reclaim 流程的系统级失败，而非单文件删除错误

### 范围外改动检查（通过）

| 检查项 | 状态 | 证据 |
|---|---|---|
| 无行为代码改动 | ✅ | diff 仅包含 docstring 行变更，无函数体/条件/调用修改 |
| 无类型签名改动 | ✅ | `Host.run_storage_maintenance` 与 `_PublicHostHandle.run_storage_maintenance` 签名未变 |
| 无公共 API 改动 | ✅ | 参数、返回值、异常类型均未变 |
| 无测试断言改动 | ✅ | 未修改任何测试文件 |
| `_raise_if_closed()` 调用位置未变 | ✅ | `open_host.py:537` 仍在 docstring 之后，是原始代码位置 |

### Fix artifact 自洽性验证（通过）

| Codex fix artifact 声明 | diff 实际内容 | 自洽 |
|---|---|---|
| api.py docstring 改为完整 maintenance 描述 | ✅ 已改 | ✅ |
| 明确默认 dry-run + reclaim_orphan_artifacts=True 破坏性回收 | ✅ 已添加 | ✅ |
| raises 移除"不支持 destructive reclaim" | ✅ 已移除 | ✅ |
| open_host.py 同步 | ✅ 已同步 | ✅ |
| pyright 0 errors | ✅ 已声明并合理（docstring-only） | ✅ |
| 未运行测试（docstring-only，合理） | ✅ 行为代码未变 | ✅ |
| 未同步 README/design（已正确） | ✅ design.md 已描述正确语义 | ✅ |

## Open Questions

无新 open question。DS 原始 Q2（`report_storage_usage` 缺少显式 `_raise_if_closed()`）不在本次 fix scope 内，由原始 deepreview 追踪。

## Residual Risk

无新增 residual risk。本次为纯 docstring 修复，不引入行为面残余风险。

原始 DS deepreview 的 R1-R5 在此次 re-review scope 外，不因本次 docstring 修复而增加或减少。

## Conclusion

**结论: PASS**

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **Open questions**: 0（原始 Q1 已通过 docstring 修复关闭；原始 Q2 不在本次 fix scope）
- **Residual risk**: 无新增

### 核心判断

AgentCodex 的 docstring 修复准确、完整、最小化：

1. **Finding 001 修复完整**：两处 docstring（Protocol + async handle）均从单一 "dry-run" 描述改为完整双模行为描述（默认 dry-run / opt-in destructive），与 `storage_maintenance.py` facade docstring 的设计真源对齐。
2. **Q1 修复准确**：移除了"不支持的 destructive reclaim 请求失败时抛出"这一无实现对应的措辞，替换为准确的 "orphan artifact 回收失败时抛出"。
3. **边界守住了**：无行为代码、类型签名、公共 API、测试断言的 scope creep。diff 是纯 docstring 变更。
4. **自洽性好**：fix artifact 的描述与 git diff 实际内容完全一致。
