# UF-FIX11 company-metadata-ignored-change-warning Plan Re-Review

## Review Target and Scope

- **Reviewed target**: `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`（经 A1-A10 裁决修订）
- **Controller adjudication**: `docs/gateflow/uf-fix11-plan-review-adjudication-20260817.md`
- **Fix artifact**: `docs/gateflow/uf-fix11-plan-review-fix-20260817.md`
- **上一轮 review**: `docs/reviews/plan-review-20260817-090453.md`（AgentMiMo）
- **Scope**: 复审修订后的 plan，核对上一轮 findings 是否关闭，验证 A1-A10 裁决是否落实，检查是否有新 findings。

## 上一轮 Findings 关闭状态

| Finding ID | 上一轮严重程度 | Controller Decision | 修订后状态 | 验证结果 |
| --- | --- | --- | --- | --- |
| 001 | 高 | `rejected-with-reason` | 证据失效 | **确认关闭** — 反例把"名称不等价"误写成"NFKC+casefold 等价"；plan 已规定等价名称保持 `keep + rollback`。`_company_meta_from_published` 在 identity 不变时保留原 `updated_at`。 |
| 002 | 中 | `rejected-with-reason` | 证据失效 | **确认关闭** — 反例把 source skip 与 company identity mutation 混为同一 contract；UF-FIX10 no-mutation 约束针对 filing/source assets，用户已明确授权 company identity metadata 的原子 mutation。 |
| 003 | 中 | `accepted` | 已修复 | **确认关闭** — §9.2 增加完整 `def commit_batch` 清单（dayu 3 定义 + test 7 文件/9 定义），§12.5 增加 `rg` 验收，Slice 1 覆盖全部 fake 文件。 |
| 004 | 低 | `accepted` | 已修复 | **确认关闭** — §6.6 明确 filing 必须显式输出 `warnings`，空为 `[]`；只有 `SourceKind.MATERIAL` 的 missing 映射空 tuple；`null` 等 fail closed。 |
| 005 | 低 | `accepted` | 已修复 | **确认关闭** — 文案改为 "本次提交的公司名称未生效；已保留现有公司名称。请核对上传目标公司是否正确。" |
| 006 | 低 | `accepted` | 已修复 | **确认关闭** — shared filing publication 是内部 outcome 的唯一业务消费者；SEC/CN 禁止直接读取内部 outcome；early cancelled/delete 显式 `warnings=()`。 |

## Assumptions Tested

1. A1/A2 的 rejected-with-reason 是否合理
2. A3-A10 的 accepted findings 是否已在 plan 中落实
3. 修订后的 plan 是否引入新的 material issues
4. slices/allowed files/测试是否可直接实施
5. fake 全集清单是否完整
6. warnings JSON schema 行为是否明确
7. SKIP+preserve 调用路径是否清晰
8. 并发测试是否足够具体
9. whole-tree COMPLETE 校验是否保留

## Findings

修订后的 plan 已充分落实 A3-A10 的 accepted findings，A1/A2 的 rejected-with-reason 合理且有直接证据支持。没有发现新的 material findings。

### 验证详情

**A1/A2 验证**:
- A1: Plan §8.3 明确 "final company meta 字段/序列化 bytes、`updated_at` 与 source tree hash 不变"；禁止 commit 前 snapshot 推断 warning。这与 controller 裁决一致。
- A2: Plan §8.3 明确 "source publication 继续零 mutation；accepted company identity metadata update 是 UF-FIX11 对 UF-FIX10 source-skip no-mutation contract 的有意且唯一例外"。这与 controller 裁决一致。

**A3-A10 验证**:
- A3: §9.2 增加了完整的 `def commit_batch` 清单，§12.5 增加了 `rg` 验收，Slice 1 allowed files 覆盖全部 7 个 fake 文件。
- A4: §6.6 明确了 filing/material 的不同 schema 行为，`null` 等 fail closed。
- A5: 文案已改为 controller 指定的精确文案。
- A6: §6.5 明确了 shared filing publication 是唯一消费点，SEC/CN 禁止直接读取内部 outcome。
- A7: §8.3 和 Slice 2 明确了 metadata-only commit 继续服从 `_validate_complete_source_tree`。
- A8: §8.3 和 Slice 2 写死了 SKIP+preserve 的直接调用路径，禁止复用 publish helper。
- A9: §6.6 和 Slice 3 明确了 `to_json_summary()` 必须写 `warnings`。
- A10: Slice 2 增加了两个 barrier/event-controlled tests。

**新 Findings 检查**:
- 没有发现新的 material issues。
- Plan 的 slices 划分合理，allowed files 明确，tests 具体。
- fake 全集清单完整，覆盖 dayu 3 个定义 + test 7 文件/9 定义。
- warnings JSON schema 行为明确，filing 必须显式输出，material 只有 missing 允许空 tuple。
- SKIP+preserve 调用路径清晰，禁止复用 publish helper。
- 并发测试使用 barrier/event，禁止 sleep/polling。
- whole-tree COMPLETE 校验保留，metadata-only commit 继续服从完整性校验。

## Open Questions

无。所有上一轮 open questions 已在 controller 裁决和 plan 修订中解决。

## Residual Risks

| Residual | Classification | Owner/destination |
| --- | --- | --- |
| name-only metadata batch 的 writer lock/physical swap 成本 | `assigned to later work unit` | 后续性能/存储 work unit |
| material company-name warning | `assigned to later work unit` | 独立 material work unit |
| 真实 CLI evidence、oracle/scenario/frozen evidence | `assigned to later work unit` | evidence work unit |
| durable 后 guard-release/cleanup 报错时不发 warning | `assigned to later work unit` | storage operations work unit |

没有未分类 residual risk。

## Plan Review Conclusion

**pass**

修订后的 plan 已充分落实 controller 裁决的 A3-A10 accepted findings，A1/A2 的 rejected-with-reason 合理且有直接证据支持。Plan 的 semantic owner 清晰，typed contracts 完整，slices 划分合理，fake 全集清单完整，warnings JSON schema 行为明确，SKIP+preserve 调用路径清晰，并发测试具体，whole-tree COMPLETE 校验保留。

没有发现新的 material findings。Plan 可以进入 implementation。
