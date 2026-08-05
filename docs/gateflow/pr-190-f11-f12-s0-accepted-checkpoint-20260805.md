# PR 190 F11/F12 S0 Accepted Checkpoint

## Gate identity

- Slice: `S0 — design truth`
- Base: `427b1c858d5e926f309935fa206963deb1618436`
- Branch: `codex/interactive-oracle`
- Verdict: **PASS — accepted slice**
- Semantic still-open: `0`
- Owner still-open: `0`
- New blockers: `0`

## Accepted contract

- F11 的公开 compactor response identity 只由 Host Tool Trace durable resolver 从 canonical compact terminal 与 proposal manifest graph 精确绑定；完整 keyset exhaustion 前不得报告 missing，mismatch、duplicate、malformed 与 cursor corruption 全部 fail closed。
- F12 使用 fresh compact v3：模型只生成五类业务语义及必要 provenance；Context Governance 从 immutable boundary、accepted provenance 与同一 `MemoryProjectionPolicy` 派生 represented、omitted 与 policy usage audit。
- initial 与 repair 共享 structure 真源但分别渲染；Host internal request/source-boundary digest 不进入任何 LLM-facing 文本。
- Engine 只拥有 provider-neutral structured-output request/capability、合法组合与 transport 投影；不按 provider 名称推断，不静默降级。
- 旧 compact v2 normative contract、兼容 reader、alias、wrapper 与双设计真源均不保留。

## Review chain

| Artifact | SHA-256 | Result |
|---|---|---|
| `docs/gateflow/pr-190-f11-f12-s0-design-implementation-20260805.md` | `1ae28a8fe945ce28e3fa82809b2a618b0cfc64e7d83af94c4c50705334fffda1` | implementation complete |
| `docs/reviews/pr-190-f11-f12-s0-design-review-mimo-20260805.md` | `ab15eb0556ff83af5d5b45170fd64ac96eb0d498e4dac80c8e487170188b0b4c` | PASS |
| `docs/reviews/pr-190-f11-f12-s0-design-review-ds-20260805.md` | `b4f922b0b01322387ab4e18e7d42d1e2e596393fccc53ad9f6d55e419dc24416` | PASS with one mechanical count finding |
| `docs/gateflow/pr-190-f11-f12-s0-design-review-adjudication-20260805.md` | `7a8d03e420efc243825e2fddf64ee0d247b7abebde40a0ad118b0b5e6a7f825a` | count finding accepted and fixed |
| `docs/reviews/pr-190-f11-f12-s0-design-rereview-mimo-20260805.md` | `dc5eb8de15ebea9d0c4ebf59313c7332205ed52abe57339eda6d4a16eb62fdc9` | PASS |
| `docs/reviews/pr-190-f11-f12-s0-design-rereview-ds-20260805.md` | `9c21d67ca34917feda89c30f2ab0ffea293f053eb192be7e3da037a6901e8894` | PASS |

Design truth digests at acceptance:

- `docs/host/design.md`: `e92ba1e027ce28b815916f2ac5ff0c0a37dcbab001b036250d48b9982d9c1978`
- `docs/engine/design.md`: `b190e3a8ee2df84d29546ca04d4fb7d81a73877b27a3bddd04d2aaa40db17b1e`

## Validation and next entry point

- Conflicting v2 normative scan: `0` hits.
- Markdown fence markers: Host `182`, Engine `8`; both even.
- `git diff --check`: PASS.
- S0 is documentation-only; production tests, coverage and pyright begin with implementation slices.
- Next entry point: `S1 — F11 public Tool Trace response identity`.
