# UF-FIX06 plan re-review 3（N1 专项验证）

## Review 元数据

- Work unit：`UF-FIX06 converter-capability-owner`
- Gate：`plan re-review`（第三轮，N1 专项）
- Reviewer：AgentMiMo
- 日期：2026-08-15
- Scope：只验证 plan 与 plan-fix 中 N1 是否按追加裁决完全修复；确认此前 findings 无回退。
- 输入：
  - `docs/gateflow/uf-fix06-converter-capability-owner-plan-20260815.md`
  - `docs/gateflow/uf-fix06-converter-capability-owner-plan-fix-20260815.md`
  - `docs/reviews/uf-fix06-plan-re-review-adjudication-20260815.md`（追加裁决 N1）

## N1 裁决要求复核

Controller 追加裁决 N1（低，accepted）要求：

1. `upload_failure_reason_from_json` 的 kind/code 一致性推导必须同步识别 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`；
2. owner test 明确断言 usage failure reason 的 `to_json()` 经该函数恢复后与原值相等（round-trip）；
3. 保持未知 code 与错配 kind/code 继续拒绝。

## Plan 文本逐项验证

### 要求 1：`upload_failure_reason_from_json` 同步识别 usage code

**Plan Slice 3 Exact changes #6**（line 408–412）原文：

> 同步扩展 `upload_failure_reason_from_json` 的 kind/code 一致性推导，使
> `UNSUPPORTED_UPLOAD_FORMAT` 唯一推导为 `USAGE`，同时保持未知 code 与错配 kind/code 拒绝

✅ 明确要求扩展 `upload_failure_reason_from_json`，使 `UNSUPPORTED_UPLOAD_FORMAT` 唯一推导为 `USAGE`。
✅ 明确保留未知 code 与错配 kind/code 拒绝行为。

### 要求 2：owner test 明确 round-trip 相等

**Plan Slice 3 Tests / assertions**（line 428–430）原文：

> `USAGE/UNSUPPORTED_UPLOAD_FORMAT` failure reason 的 `to_json()` 结果经
> `upload_failure_reason_from_json` 恢复后与原值相等；未知 code 与已知 code 配错 kind
> 继续被拒绝，不得因新增 `USAGE` 放宽 closed contract。

✅ 明确断言 round-trip：`to_json()` → `upload_failure_reason_from_json` 恢复后与原值相等。
✅ 明确断言未知 code 与错配 kind 继续被拒绝。
✅ 明确约束"不得因新增 `USAGE` 放宽 closed contract"。

### 要求 3：拒绝未知/错配

以上两处均已覆盖。补充检查 §5.2 failure projection 设计（line 150–159）：

- `FinsUploadFailureKind` 增加 `USAGE` ✅
- `FinsUploadFailureCode` 增加 `UNSUPPORTED_UPLOAD_FORMAT` ✅
- `fins_upload_failure_from_exception` 显式匹配 `FinsUploadFormatError` 并投影为 `USAGE/UNSUPPORTED_UPLOAD_FORMAT` ✅

**Plan-fix N1 表**（line 137–139）确认修复状态为"已修复"，修订位置指向 Slice 3 Exact changes #6 与 Slice 3 Tests / assertions，与 plan 正文一致 ✅。

## 此前 findings 回退检查

| Finding | 上一轮状态 | 当前状态 | 回退证据 |
|---|---|---|---|
| M1 | 已修复 | 维持已修复 | Slice 1 不变 |
| M2 | 已修复 | 维持已修复 | Slice 2/4 不变 |
| D1 | 已修复 | 维持已修复 | Slice 2/3 不变 |
| D2 | 已修复 | 维持已修复 | Slice 3 不变 |
| D3 | 已修复 | 维持已修复 | Slice 1 不变 |
| D4 | 已修复 | 维持已修复 | Slice 2 不变 |
| D5 | 已修复 | 维持已修复 | Slice 3 不变 |
| O1 | 已修复 | 维持已修复 | Slice 2/4 不变 |
| O2 | 已修复 | 维持已修复 | Slice 3 不变 |
| R1 | 已修复 | 维持已修复 | Slice 3 不变 |
| R2 | 已修复 | 维持已修复 | Slice 1/2 不变 |
| R3 | 已修复 | 维持已修复 | Slice 2/3 不变 |

无回退。N1 的修订仅在 Slice 3 Exact changes #6 和 Slice 3 Tests / assertions 增加了 `upload_failure_reason_from_json` 同步识别与 round-trip 断言，不触碰已有 findings 的修复位置。

## Open questions

无。

## Residual risks

沿用此前分类，无新增：

| Residual risk | 分类 | Owner / destination |
|---|---|---|
| batch companion association | assigned to later work unit | UF-FIX07 |
| 真实格式矩阵 | assigned to later work unit | UF-PF06 |
| 137 条 mandatory scenario | assigned to later work unit | UF-PF12 |
| 显式 primary / 碰撞 | assigned to later work unit | UF-FIX07 |
| `.xsd` 以外 companion-only | assigned to later work unit | 后续 XBRL 产品能力 work unit |

## Conclusion

**pass**

N1 按追加裁决完全修复：plan Slice 3 Exact changes #6 明确要求 `upload_failure_reason_from_json` 同步识别 `USAGE/UNSUPPORTED_UPLOAD_FORMAT`，Slice 3 Tests 明确断言 round-trip 相等并继续拒绝未知/错配 kind-code。此前全部 12 个 findings（M1/M2/D1–D5/O1/O2/R1/R2/R3）维持已修复，无回退。plan 当前 code-generation-ready。
