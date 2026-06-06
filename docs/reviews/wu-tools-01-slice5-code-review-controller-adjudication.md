# WU-TOOLS-01 Slice S5 Code Review Controller Adjudication

Gate: code-review adjudication
Work unit: WU-TOOLS-01
Slice: S5 - Web Tools Provider
Status: FIX REQUIRED

## 输入

- `docs/reviews/wu-tools-01-slice5-code-review-mimo.md`
- `docs/reviews/wu-tools-01-slice5-code-review-ds.md`
- `docs/reviews/wu-tools-01-slice5-implementation-codex.md`

## 裁决

MiMo 原始结论为 PASS，无 blocking finding。DS 原始结论为 PASS，并提出 3 个 medium finding 与 4 个 low finding。

Controller 复核时发现更高优先级问题：`dayu/tools/web` 生产代码存在大量 `typing.Any` 类型签名与 payload 类型，违反 AGENTS.md 中禁止 `Any` / `object` / 无类型签名的硬约束。因此 S5 implementation 不可直接接受，必须进入 fix gate。

## Accepted Findings

### A1 - Blocking: Web 生产代码存在 `Any` 类型边界

- 证据：`rg -n "\bAny\b|\bobject\b" dayu/tools/web` 命中大量 `typing.Any` import、函数参数、返回值、payload dict 与 Callable 签名。
- 裁决：blocking。迁移原则不覆盖 AGENTS.md 类型硬约束；旧代码迁移到当前仓库时必须完成严格类型边界适配。
- 修复要求：用 `JsonValue`、`Mapping[str, JsonValue]`、`TypedDict`、`TypeAlias`、最小 `Protocol` 与必要 `cast` 表达外部库边界；生产代码不得保留 `typing.Any`，`object` 仅允许 JSON schema 字面量。

### A2 - Medium: 未使用导入

- 证据：DS finding F1，`dayu/tools/web/web_tools.py` 导入 `RECOVERY_CONTRACT_VERSION` 但未使用。
- 裁决：accepted。移除未用 import，不改业务逻辑。

### A3 - Medium: 死包装函数

- 证据：DS finding F2，`dayu/tools/web/web_tools.py` 中 `_close_response_safely` 只透传到 orchestrator，且未被调用。
- 裁决：accepted。删除死包装；`web_fetch_orchestrator.py` 内部真实 close 逻辑不得改变。

### A4 - Review / Residual: Playwright fallback 取消投影

- 证据：DS finding F3，Playwright fallback 中 `CancelledError` 可能被 adapter 通用异常路径投影为 `execution_error`。
- 裁决：accepted for fix if minimal；若需要更大 ToolRuntime contract 设计，则记录 residual。
- 修复要求：优先用最小适配把取消投影为 current `ToolFailedOutcome(error="tool_cancelled")`，并补 deterministic test。

## Deferred Non-Blocking Items

- DNS 同步解析、日志适配器风格、函数别名风格、取消检查重复、live network 覆盖与 provider 级串行并发证据均不阻塞 S5 接受。
- Provider 级串行与 live network 覆盖作为残余风险继续追踪。
