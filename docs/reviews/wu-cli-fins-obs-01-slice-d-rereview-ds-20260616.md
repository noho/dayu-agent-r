# WU-CLI-FINS-OBS-01 Slice D Review Fix Re-Review

## Gate

- Work unit: `WU-CLI-FINS-OBS-01`
- Slice: D, Fins tool awaiting and wait adapter lightweight handle
- Gate: re-review (review fix follow-up)
- Reviewer: AgentDS (DeepSeek)
- Fix artifact: `docs/reviews/wu-cli-fins-obs-01-slice-d-review-fix-codex.md`
- Prior review: `docs/reviews/wu-cli-fins-obs-01-slice-d-review-ds-20260616.md` (PASS)
- Date: 2026-06-16

## Fix Summary

Adjudication 确认两篇 review 均为 PASS，无 blocking findings。接受的唯一 low-cost follow-up：

- MiMo observation: `_FinsObservedOperationRecord` 已是 mutable dataclass 且所有字段读写均在 `_observation_lock` 下完成，但 class docstring 未声明该 invariant。

Fix 仅更新 `dayu/fins/ingestion_runtime.py` 中 `_FinsObservedOperationRecord` 的 docstring，增加持锁 invariant 说明：

```python
@dataclass
class _FinsObservedOperationRecord:
    """process-local awaiting observation record。

    该对象是 registry 内部可变快照；除创建阶段外，所有字段读取和变更都
    必须在所属 runtime 的 ``_observation_lock`` 保护下完成。
    ...
```

## Verification

### 未改行为

- `git diff dayu/fins/ingestion_runtime.py` 确认：仅 `_FinsObservedOperationRecord` docstring 新增锁 invariant 段落，无任何代码逻辑、类型签名、字段定义或方法体变更。
- 类声明（`@dataclass`）、字段列表、所有调用点均未变。

### 未引入 job/durable/sidecar 语义

- 新增 docstring 不包含 "job"、"durable"、"sidecar"、"cursor"、"sequence"、"resume_token"、"job_id" 等术语。只描述 `_observation_lock` 保护规则。

### 测试与类型检查

```text
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_host_assembly.py -q
152 passed, 3 warnings

source .venv/bin/activate && pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

git diff --check
clean
```

## 结论

**PASS**

Fix 是纯 docstring 增强，无行为变更，未引入任何旧语义。测试与 pyright 保持全绿。
