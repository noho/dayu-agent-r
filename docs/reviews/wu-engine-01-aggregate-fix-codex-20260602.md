# WU-ENGINE-01 Aggregate Deepreview Fix

## Scope

- 任务：修复 aggregate deepreview gate 接受的 DS low findings。
- 角色：AgentCodex implementation/fix。
- 修改范围：
  - `dayu/engine/runners/openai/diagnostic_payload.py`
  - `tests/engine/runners/openai/test_diagnostic_payload.py`
- 未执行：commit、push、创建 PR、修改总控文档。

## Root Cause

### F-01

`_is_sensitive_key` 只对原始 key 做小写后匹配，`_SENSITIVE_KEY_FRAGMENTS` 中的 `api_key` 无法匹配 `api-key` / `x-api-key` 等破折号形态字段。问题成立，属于脱敏边界覆盖不足。

### F-02

`_provider_error_summary` 只保留非空字符串，导致 provider error 中的 `code` / `type` / `param` 若为 JSON number、boolean 或 null 会被静默丢弃。问题成立，属于诊断信息保留规则过窄。

## Changes

### F-01 修复

- 新增 `_normalized_sensitive_key`，在敏感 key 匹配前统一执行：
  - 小写化；
  - 将 `-` 规范化为 `_`。
- `_is_sensitive_key` 改为基于规范化 key 匹配既有敏感片段，避免为 `api-key`、`x-api-key`、`access-token` 等形态写硬编码分支。
- 测试扩展敏感值泄漏检查，覆盖：
  - `api-key`
  - `x-api-key`
  - `client-secret`
  - `access-token`

### F-02 修复

- 新增 `_provider_error_scalar_preview`，集中表达 provider error 摘要字段的保留规则：
  - 非空字符串保留并按既有长度上限截断；
  - `int` / `float` / `bool` / `None` 保留为 JSON 标量；
  - 空字符串与容器值不保留。
- `_provider_error_summary` 改为调用该 helper，不再只接受字符串。
- 新增测试覆盖：
  - `code: 429`
  - `type: true`
  - `param: null`
  - 空字符串和容器字段仍被过滤。

## Validation

### 受影响测试

命令：

```bash
source .venv/bin/activate && pytest tests/engine/runners/openai/test_diagnostic_payload.py
```

结果：

```text
9 passed in 0.13s
```

### 目标 pyright

命令：

```bash
source .venv/bin/activate && pyright dayu/engine/runners/openai/diagnostic_payload.py tests/engine/runners/openai/test_diagnostic_payload.py
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

### 全量 pyright

命令：

```bash
source .venv/bin/activate && pyright
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

## README Sync

本次修改不改变公共接口、CLI、配置入口、Runner 事件字段形状、分层关系或用户可见工作流。`dayu/engine/README.md` 已有的 `raw_payload` 有界诊断语义仍准确，因此无需同步 README。

## Residual Risk

- 未发现新增类型风险；目标文件与全量 pyright 均通过。
- 本次仅覆盖破折号到下划线的 key 规范化；若未来需要覆盖其它分隔符形态，应继续在 `_normalized_sensitive_key` 中扩展统一规范化规则，而不是增加分散分支。
- 工作区保留未提交状态，等待 controller review。
