# Code Re-Review

## Scope

- Mode: current changes
- Branch: docs/phase12-design-discussion
- Base: main
- Output file: docs/reviews/phase12-2-service-assembly-rereview-mimo-20260522.md
- Re-review trigger: DS Finding 1 fix by AgentCodex
- Excluded scope: docs/reviews/repo-review-20260522-070034.md, docs/reviews/repo-review-20260522-070045.md

## DS Finding 1 Fix Verification

**原 Finding**: `_agent_fallback_mode_from_config` 使用手工 if/elif 链映射 fallback mode，应复用 Engine enum 原生值校验。

**Fix 内容**:
1. `dayu/service/host_assembly.py:815`: `_agent_fallback_mode_from_config` 改为 `return AgentFallbackMode(value)`
2. `tests/service/test_host_assembly.py:153-170`: 新增 `test_agent_fallback_mode_from_config_uses_engine_enum_values` 测试

**Fix 验证**:
- `AgentFallbackMode(value)` 是 Engine StrEnum 的标准构造方式，对 `force_answer` / `raise_error` 返回对应 enum 成员，对非法值抛出 `ValueError`
- 新测试覆盖合法值映射和非法值拒绝两个路径
- `pytest tests/service/test_host_assembly.py -q`: 3 passed
- `python -m pyright dayu/service tests/service`: 0 errors

**结论**: DS Finding 1 已收口。fix 简洁、正确，无新增问题。

## Findings

未发现实质性问题。

## Blocking Finding Count

0

## 结论

**PASS** - DS Finding 1 已收口且无新增 blocker。

验证结果:
- `pytest tests/service/test_host_assembly.py -q`: 3 passed
- `python -m pyright dayu/service tests/service`: 0 errors
- DS Finding 2 (README 死链) 已裁决为本轮前既存 out-of-scope/deferred，本轮不修
