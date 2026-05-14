# Host Phase 3 P3-S1 Code Review Controller Adjudication

- **gate name**: P3-S1 code review / controller adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **assigned slice**: P3-S1 Schema And Row Codecs
- **implementation artifact**: `docs/reviews/gateflow-implementation-host-p3-s1-schema-row-codecs-20260514.md`
- **review artifact**: `docs/reviews/gateflow-code-review-host-p3-s1-schema-row-codecs-mimo-20260514.md`
- **artifact path**: `docs/reviews/gateflow-code-review-host-p3-s1-schema-row-codecs-controller-adjudication-20260514.md`

## Finding Decisions

### P3S1-MIMO-001: 测试未验证 active partial unique index 拒绝 terminal status 组合

- **decision status**: accepted
- **severity accepted by controller**: low
- **reason**: DDL 当前正确，但测试只证明 active + active 被拒绝、different sessions active 被允许；缺少 active + terminal 同 Session 可共存的正面证明。该测试能更直接证明 partial unique index 的 active status 集合边界。
- **required fix**: 增加测试，验证同一 Session 可同时存在 active Run 与 terminal Run，且不触发 active partial unique index。

### P3S1-MIMO-002: `_serialize_str_enum` 的 isinstance 校验可被非 StrEnum 的 Str 子类绕过

- **decision status**: rejected-with-reason
- **severity accepted by controller**: none
- **reason**: finding 的触发路径不成立。`_serialize_str_enum` 在访问 `value.value` 前先执行 `if not isinstance(value, StrEnum): raise HostDurableError(...)`；普通 `str` 子类或带 `.value` 属性的非 `StrEnum` 对象不会通过该分支。当前签名 `value: StrEnum` 也符合本模块内部泛型 serializer 的用途。进一步用 MRO 做更严格检查属于过度防御，不是当前 slice 必要修复。
- **required fix**: none

## Gate Decision

- **accepted findings requiring fix**: P3S1-MIMO-001
- **rejected findings**: P3S1-MIMO-002
- **blocking findings**: 0
- **decision**: enter P3-S1 fix gate for the accepted test gap only.
