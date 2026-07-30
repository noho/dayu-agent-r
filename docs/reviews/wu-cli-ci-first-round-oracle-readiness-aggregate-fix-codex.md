# CLI CI 第一轮 Oracle Readiness Aggregate Deepreview Fix

## Artifact Metadata

- Gate：`aggregate deepreview fix`
- Review：`docs/reviews/code-review-20260730-102719.md`
- Finding：ADR-01
- Status：待 re-review

## Fix

- `execution_outcome` owner 从 `per-leaf/path` 收束为 `per-scenario raw process observation`。
- `evidence_status/gap_kind` owner 从 `per-leaf/path` 收束为 `per-scenario evidence integrity record`。
- Agent suggestion/adjudication 必须引用 frozen report digest、scenario/correctness surface 和 evidence refs；
  leaf/path 只保留为导航/分组。

## Validation

- Report、readiness proof、outcome/evidence 和 user adjudication 现在使用同一个 scenario identity。
- 未增加 fallback、兼容字段或下游重算。

## Residual Risks

- 无本 finding 遗留风险。
