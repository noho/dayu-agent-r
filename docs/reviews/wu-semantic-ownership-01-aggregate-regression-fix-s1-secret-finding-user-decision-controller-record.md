# WU-SEMANTIC-OWNERSHIP-01 Slice 1 Secret Finding User Decision Controller Record

## Identity

- Umbrella work unit：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- Prior candidate finding：`S1-SEC-F01`。
- Decision source：用户在 2026-07-19 对本地 Agent trust boundary 的明确产品裁决。
- Status：`USER DECISION RECORDED / PRIOR CODE BLOCKER SUPERSEDED / PLAN CORRECTION REQUIRED`。
- 本 artifact 不记录任何 secret value 或具体 secret ref 名称。

## Corrected code fact

当前 schema 的 `config/` 主要保存 provider/model 配置、`api_key_ref` 与 header template；真实 secret value 由运行环境解析。这个实现事实不改变用户裁决的信任边界：大愚 Agent 是本地运行的 Agent，内部 Config、Host SQLite 与 EventLog 属于同一受信任本地产品域。将同一 provider secret/header 保存到内部 SQLite/EventLog 不被视为新增的当前产品泄露面，也不要求为了“EventLog 零 secret”引入额外 descriptor、type split、resolver callback 或 execution seam。

## Authoritative user decision

1. Host SQLite/EventLog 可以保存 provider API key 明文或包含该值的内部 headers，以冻结一次 Run 实际使用的执行配置并支持 retry/replay/recovery。
2. 该内部 durable behavior 不是当前 WU 的安全 code finding，也不是 configured-secret scan 的 release blocker。
3. Tool Trace 与 audit projection 不得包含 API key 明文。
4. 本裁决不授权把 secret 投影到 LLM-facing memory/compact/evidence、用户可见 HostEvent/UI 文本或 operator logs；现有脱敏与截断机制继续保留，因为本轮没有删除这些安全机制的产品需求。
5. 不引入 Host-safe/Engine-only 双类型、content-addressed header descriptor、secret resolver callback、通用 secret manager、permission schema 或统一 tool authorization framework。
6. 当前 `RunnerSpec` 与内部 effective execution snapshot 可以继续承载解析后的 headers；其 internal durable copy 与 Tool Trace/audit/public projection 必须保持边界清晰。

## Finding disposition

- `S1-SEC-F01` as “plaintext provider header in internal EventLog requires production redesign”：`REJECTED BY USER PRODUCT DECISION / CLOSED AS CODE BLOCKER`。
- Controller evidence 与双路 design-truth reviews 保留为发现过程和旧真源冲突证据，不删除、不改写。
- Prior Controller recommendation in
  `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-s1-secret-finding-controller-adjudication.md`
  is superseded by this user decision and cannot authorize implementation。
- 仍需 plan correction 的内容不是 secret storage redesign，而是：
  - 写回 Host/UI 设计真源，明确 internal durable state 与 Tool Trace/audit/public projections 的信任边界；
  - 修正 Slice 1 configured-secret validation，使 exact internal Config/EventLog owner path 被分类为 accepted local durable storage，而 Tool Trace/audit/LLM-facing/public/log/diff surfaces 继续要求 zero plaintext；
  - 用直接 owner tests/source scans 验证 Tool Trace 与 audit 不投影 secret；若发现真实投影缺陷，再作为同一 umbrella 的 accepted review finding 进入代码修复。

## Scope and non-goals

- 仍是同一个 umbrella WU，不创建新 WU/feature/issue。
- 不修改 Topic 8 的 Engine exception redaction/truncation behavior。
- Topic 9 仍为 no-code decision，不实施统一 tool authorization framework。
- 不删除现有日志脱敏、LLM-facing 安全投影、path/network/process/storage 防御机制。
- 不越界实施 Issues 142、151、175、177、178。
- 不因为本裁决把任意 workspace 文件都视为 secret-safe；只接受明确 owner 的 Config 与 Host internal durable state。Tool Trace、audit、LLM/public projections、logs、review artifacts 和 git diff 仍必须 fail closed。

## Next gate

AgentCodex 必须先基于本裁决完成 design-truth writeback 与 aggregate regression fix plan correction。修正计划应删除 `S1-SEC-F01` production redesign，增加 projection-boundary verification，并保留 Slice 1 三个既有 test delta。之后执行 AgentMiMo/AgentDS 并发完整 plan review、fix、re-review，再恢复 Slice 1 implementation validation/review/accepted commit。
