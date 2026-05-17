# P9.5 S17 Documentation Review — Documentation And Control Tracking

## Review Context

- Reviewer: AgentMiMo
- Scope: S17 Documentation And Control Tracking
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Plan: `docs/host/p9-5-pre-p10-hardening-plan.md` S17
- Diff: uncommitted changes on `p9.5-pre-p10-hardening`

## Verdict: CONDITIONAL PASS — 一处精度问题

S17 文档更新准确反映当前代码事实，未写未来承诺或实现细节。README 职责未越界。唯一 finding 是 `tests/README.md` 中 Engine import boundary 的 "memory" 表述精度略高于实际测试粒度。

---

## Findings

### F1 — `tests/README.md` Engine import boundary "memory" 精度问题

**Severity: LOW (文档精度)**

`tests/README.md:104` 写道：

> import boundary：阻止 Engine 反向依赖 Host、Service、UI、Fins、**memory**、工具声明 owner、工具执行实现、处理器或 trace 私有模块

实际测试覆盖：
- `tests/engine/test_import_boundary.py:24-31`：`ENGINE_CORE_FORBIDDEN_PREFIXES` 包含 `"dayu.host"`，不包含独立的 memory 前缀
- memory 模块位于 `dayu/host/memory.py`、`dayu/host/memory_repair.py`、`dayu/host/durable/memory.py`
- Engine 不导入 memory 的约束通过 `"dayu.host"` 前缀禁令间接覆盖

**问题**：文档将 "memory" 列为独立禁止项，但测试中无独立 memory 断言。概念上正确（Engine 不应依赖 memory），但文档精度略高于测试粒度。

**建议修法**：将 "memory" 改为括号说明，如 "Host（含 memory）" 或删除独立 "memory" 项，因为 `dayu.host` 前缀禁令已覆盖。

**判定**：不阻塞。概念正确，只是粒度表述问题。

---

### F2 — `dayu/README.md` `fetch_more` 描述更新

**Severity: PASS**

`dayu/README.md:221` 更新为：

> `fetch_more` 不由外部业务 `ToolBundle` 提供；ToolRuntime factory 根据 TruncationManager 注入 framework tool，生成 attempt-local effective `ToolBundle`。RunInputBuilder 投影给 Engine 的 `tool_schemas` 与 ToolRuntime 执行使用的 `tool_executor` 必须来自同一个 effective ToolBundle。

**验证**：
- `dayu/host/tool_runtime.py:2939-2961`：`ToolRuntimeHandle` 包含 `effective_bundle`、`tool_schemas`、`tool_executor` 三个字段
- `__post_init__` 强制 `tool_schemas` 必须来自 `effective_bundle`
- `create_tool_runtime` 返回的 handle 中 `tool_schemas` 和 `tool_executor` 来自同一 `effective_bundle`

**判定**：准确反映代码事实。

---

### F3 — `dayu/engine/README.md` Runner 扩展描述更新

**Severity: PASS**

`dayu/engine/README.md:421` 更新为：

> 当前函数式入口通过私有默认装配点创建内置 OpenAI-compatible Runner；该私有装配点不是公共 factory、registry 或 runner 选择扩展点。

**验证**：
- `dayu/engine/agent.py:111`：从 `dayu.engine._default_runner`（私有模块）导入 `build_default_runner`
- `agent.py:250-261`：`_build_runner(request)` 是私有函数，docstring 明确说明"不是 factory、registry 或扩展点"
- `agent.py:2505`：`run_agent_messages` 调用 `_build_runner(request)`

**判定**：准确反映代码事实。

---

### F4 — `dayu/host/README.md` projection catch-up 失败描述更新

**Severity: PASS**

`dayu/host/README.md:121` 更新为：

> 失败时只记录 projection-local `WARNING` 与 `error_type`，并保留已提交的 durable command / accept 结果。

**验证**：
- `dayu/host/projection.py:292-295`：`_LOGGER.warning("projection catch-up failed; continuing error_type=%s", type(exc).__name__)`
- 使用 `WARNING` 级别，记录 `error_type`，不记录 traceback

**判定**：准确反映代码事实。

---

### F5 — `docs/design.md` `fetch_more` 描述更新

**Severity: PASS**

`docs/design.md:74-76` 更新与 `dayu/README.md` 一致，增加 `tool_executor` 来自同一 effective ToolBundle 的说明。

**判定**：准确反映代码事实，与 `dayu/README.md` 保持同步。

---

### F6 — `tests/README.md` runtime import boundary 更新

**Severity: PASS**

`tests/README.md:65` 更新为：

> import boundary：阻止 runtime 反向依赖 Engine、Host、Service、UI、Fins 或引入运行期 HTTP 客户端。

**验证**：
- `tests/runtime/test_import_boundary.py:16-22`：`RUNTIME_PERMANENT_FORBIDDEN_PREFIXES` 包含 `"dayu.host"`

**判定**：准确反映测试覆盖。

---

### F7 — `tests/README.md` contracts import boundary 更新

**Severity: PASS**

`tests/README.md:79` 更新为：

> import boundary：阻止公共契约层反向依赖 Engine、Host、runtime implementation、Service、UI、Fins 或运行期 HTTP 客户端。

**验证**：
- `tests/contracts/test_import_boundary.py:22-29`：`CONTRACTS_PERMANENT_FORBIDDEN_PREFIXES` 包含 `"dayu.host"` 和 `"dayu.runtime"`

**判定**：准确反映测试覆盖。

---

### F8 — `tests/README.md` host import boundary 更新

**Severity: PASS**

`tests/README.md:96` 更新为：

> import boundary：允许 Host 在 LocalProxy 边界沿依赖方向调用 Engine public entry，阻止 Host 导入 Config、Fins、Service 或 UI，阻止 Host 使用动态模块扫描能力扫描业务工具模块，确认 business `ToolBundle` 不进入 per-run request dataclass 字段，并确认 `fetch_more` 只留在 ToolRuntime / tooling owner。

**验证**：
- `tests/host/test_import_boundary.py:191-203`：`test_host_does_not_import_business_tool_scanners` 禁止 `importlib` / `pkgutil`
- `tests/host/test_import_boundary.py:206-222`：`test_fetch_more_token_stays_inside_toolruntime_owner_modules` 限制 `fetch_more` 到 `tool_runtime.py` 和 `tooling.py`

**判定**：准确反映测试覆盖。

---

### F9 — `docs/host/implementation-control.md` 更新

**Severity: INFO (未在本次 diff 中)**

S17 plan 要求：

> `docs/host/implementation-control.md`：record P9.5 slice status, residual risk disposition, validation evidence, and clear P9.5 tracking items.

当前 diff 未包含 `implementation-control.md` 更新。此更新可能属于 S18（Aggregate Validation And Readiness Evidence）scope。

**判定**：不阻塞。可在 S18 中完成。

---

### F10 — 是否写了未来承诺、过程流水或实现细节

**Severity: PASS**

逐项检查所有文档变更：

| 文件 | 变更内容 | 未来承诺 | 过程流水 | 实现细节 |
|------|----------|----------|----------|----------|
| `dayu/README.md` | `fetch_more` 描述增加 `tool_executor` | 否 | 否 | 否（接口契约） |
| `dayu/engine/README.md` | Runner 扩展措辞收紧 | 否 | 否 | 否（边界说明） |
| `dayu/host/README.md` | projection catch-up 失败日志级别 | 否 | 否 | 否（行为描述） |
| `docs/design.md` | `fetch_more` 描述增加 `tool_executor` | 否 | 否 | 否（接口契约） |
| `tests/README.md` | import boundary 描述更新 | 否 | 否 | 否（测试覆盖说明） |

所有变更只描述当前代码事实，不承诺未来行为，不记录过程状态，不暴露实现细节。

**判定**：符合 S17 Non-goals 约束。

---

### F11 — README 职责是否越界

**Severity: PASS**

逐项检查 README 职责：

| README | 职责 | 变更是否属于职责范围 |
|--------|------|---------------------|
| `dayu/README.md` | 项目级术语真源、跨层约束 | ✓ `fetch_more` 是跨层工具契约 |
| `dayu/engine/README.md` | Engine 开发手册 | ✓ Runner 扩展点是 Engine 边界 |
| `dayu/host/README.md` | Host 开发手册 | ✓ projection catch-up 是 Host 机制 |
| `docs/design.md` | 架构真源 | ✓ `fetch_more` 是架构契约 |
| `tests/README.md` | 测试手册 | ✓ import boundary 是测试约定 |

**判定**：无越界。

---

## Summary

| Finding | Description | Severity |
|---------|-------------|----------|
| F1 | `tests/README.md` Engine "memory" 精度略高于测试粒度 | LOW |
| F2 | `dayu/README.md` `fetch_more` 描述准确 | PASS |
| F3 | `dayu/engine/README.md` Runner 扩展描述准确 | PASS |
| F4 | `dayu/host/README.md` projection catch-up 描述准确 | PASS |
| F5 | `docs/design.md` `fetch_more` 描述准确 | PASS |
| F6 | `tests/README.md` runtime import boundary 准确 | PASS |
| F7 | `tests/README.md` contracts import boundary 准确 | PASS |
| F8 | `tests/README.md` host import boundary 准确 | PASS |
| F9 | `implementation-control.md` 更新未在本次 diff | INFO |
| F10 | 无未来承诺、过程流水或实现细节 | PASS |
| F11 | README 职责无越界 | PASS |

## 结论

S17 文档更新准确反映当前代码事实，README 职责未越界，未写未来承诺或实现细节。唯一 finding 是 `tests/README.md` 中 Engine import boundary 的 "memory" 表述精度问题（LOW），不阻塞。可以接受。
