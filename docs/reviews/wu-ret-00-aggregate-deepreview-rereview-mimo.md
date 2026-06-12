# WU-RET-00 Aggregate Deep Review Re-review — MiMo

## Scope

- **Mode**: fix re-review（复审 AgentCodex 对 DS aggregate deepreview Finding 001 与 Open Question Q1 的 docstring 修复）
- **Branch**: `work/wu-ret-00-retention`
- **Review date**: 2026-06-12
- **Reviewer**: AgentMiMo

### Review targets

- DS Finding 001: Protocol 和 async handle docstring 标注 "dry-run" 与实际破坏性行为不一致
- DS Open Question Q1: `Host` Protocol `run_storage_maintenance` raises 描述中"不支持的 destructive reclaim 请求"语义无对应实现分支

### Input artifacts

- `docs/reviews/wu-ret-00-aggregate-deepreview-ds.md`（DS aggregate deepreview）
- `docs/reviews/wu-ret-00-aggregate-deepreview-fix-codex.md`（Codex fix 说明）
- `git diff dayu/host/api.py dayu/host/open_host.py`（实际改动）

### Review method

1. 逐行比对 diff，确认修改范围严格限于 docstring
2. 将修复后 docstring 与设计真源（`storage_maintenance.py:237-253` facade docstring）交叉比对
3. 确认 Finding 001 和 Open Question Q1 的修复是否准确、完整
4. 确认无范围外改动（行为代码、类型签名、公共 API、测试断言）

## Findings

**无 blocking finding。**

逐项确认如下：

### 1. Finding 001 修复验证：行为空间描述

- **修复前**（两处相同）：`"""执行 Host storage maintenance dry-run。"""`
- **修复后**（两处相同）：`"""执行 Host storage maintenance。"""` + `:param request:` 中补充"默认 dry-run 不删除文件；当 ``request.reclaim_orphan_artifacts`` 为 ``True`` 时，会执行破坏性 orphan artifact 回收。"
- **判定**：✅ 通过。准确描述了完整行为空间（dry-run 默认 + opt-in destructive），与 facade docstring（`storage_maintenance.py:237-246`）语义一致。`:returns:` 从"dry-run maintenance 结果"改为"maintenance 结果"，消除了暗示唯一模式的措辞。

### 2. Open Question Q1 修复验证：raises 描述

- **修复前 `api.py`**：`:raises HostApiError: maintenance 读取、扫描、checkpoint 或不支持的 destructive reclaim 请求失败时抛出。`
- **修复后 `api.py`**：`:raises HostApiError: maintenance 读取、扫描、checkpoint 或 orphan artifact 回收失败时抛出。`
- **修复前 `open_host.py`**：`:raises HostApiError: maintenance 读取、扫描或 checkpoint 失败时抛出。`（注意：原始 async handle 的 raises 描述甚至没有提及 reclaim，与 facade 行为不一致）
- **修复后 `open_host.py`**：`:raises HostApiError: maintenance 读取、扫描、checkpoint 或 orphan artifact 回收失败时抛出。`
- **判定**：✅ 通过。移除了"不支持的 destructive reclaim 请求"这一无实现对应的误导措辞。修复后两处 raises 描述与 facade 的实际错误映射链（`OSError` → `HostApiError(INTERNAL_ERROR)`、`HostDurableError` → `HostApiError(INTERNAL_ERROR)`）语义对齐。async handle 的修复还额外补全了原始缺失的 reclaim 失败描述。

### 3. 范围外改动检查

- **行为代码**：✅ 无改动。diff 仅涉及 docstring 字符串，不触及任何可执行代码行。
- **类型签名**：✅ 无改动。方法签名、参数类型、返回值类型均未变更。
- **公共 API**：✅ 无改动。Protocol 方法签名、async handle 方法签名均未变更。
- **测试断言**：✅ 无改动。fix artifact 说明未运行测试，理由充分（docstring-only 变更无行为面）。
- **README / design**：✅ 未同步，理由充分（设计真源已准确描述完整行为空间，本次仅修正 Protocol/handle 层的 docstring 不一致）。

### 4. Fix artifact 自洽性

- fix artifact（`wu-ret-00-aggregate-deepreview-fix-codex.md`）准确记录了修改文件、修改内容、验证方法（pyright 通过）和未覆盖项（未运行 pytest）。
- pyright 验证结果（0 errors, 0 warnings）与 docstring-only 变更的预期一致。
- 未进入 re-review gate、未 stage/commit/push/PR/merge，符合 gate 约束。

### 5. 两处 docstring 一致性

- `api.py`（Protocol）和 `open_host.py`（async handle）的修复后 docstring 完全一致，包括标题行、`:param request:` 补充说明、`:returns:` 措辞和 `:raises HostApiError:` 描述。
- **判定**：✅ 通过。Protocol 与 async handle 语义对齐。

## Open Questions

无新增 open question。

DS 原始 Open Question Q2（`report_storage_usage` facade 缺少显式 `_raise_if_closed()` 入口检查）不在本次 fix scope 内，不影响本次 re-review 结论。

## Residual Risk

无新增 residual risk。

DS 原始 Residual Risks R1–R5 不在本次 fix scope 内，状态不变。

唯一值得注意的微小差异：facade docstring（`storage_maintenance.py:251-252`）的 raises 描述写"durable 读取、artifact 扫描、文件 stat 或 checkpoint 失败"，未显式提及"orphan artifact 回收失败"；而修复后的 Protocol/async handle docstring 显式提及了"orphan artifact 回收失败"。这属于 facade docstring 本身的已知粒度差异（DS Finding 002 已覆盖 facade 层的错误消息笼统问题），不构成本次 fix 的 blocking issue。

## Conclusion

**结论: PASS**

- **Blocking findings**: 0
- **Non-blocking findings**: 0
- **Open questions**: 0（无新增）
- **Residual risks**: 无新增

### 核心判断

Codex 的 docstring 修复准确、完整、范围受控：

1. **Finding 001 修复**：✅ 两处 docstring 均从"dry-run only"描述改为完整行为空间描述（dry-run 默认 + opt-in destructive），与设计真源一致。
2. **Open Question Q1 修复**：✅ 移除了"不支持的 destructive reclaim 请求"无实现对应的误导措辞，async handle 额外补全了原始缺失的 reclaim 失败描述。
3. **范围控制**：✅ 仅 docstring 改动，无行为代码、类型签名、公共 API 或测试断言变更。
4. **Fix artifact 自洽**：✅ 记录完整，pyright 验证通过，未覆盖项说明合理。
