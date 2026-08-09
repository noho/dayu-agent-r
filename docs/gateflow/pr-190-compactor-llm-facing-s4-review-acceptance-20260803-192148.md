# PR 190 Compactor LLM-facing S4 review acceptance

## Gate decision

- Gate：S4 Documentation and aggregate validation review。
- Accepted base：`69ab297be50f4cdd1cfa1d092f470921d2d9efda`。
- Decision：**accept**；无待修 finding。
- Implementation artifact：`docs/gateflow/pr-190-compactor-llm-facing-s4-implementation-20260803.md`。
- MiMo review：`docs/reviews/pr-190-compactor-llm-facing-s4-mimo-review-20260803.md`。
- DeepSeek review：`docs/reviews/pr-190-compactor-llm-facing-s4-ds-review-20260803.md`。

## Controller adjudication

1. 文档忠实性：两路 reviewer 均回到 packaged prompts、`LLMContextCompactor` repair projector、Context Governance 与 memory policy estimator 的直接代码核对。新增设计和 README 文本与当前实现一致；不是以两路结论一致代替证据。
2. owner boundary：`dayu/config/README.md` 只承诺 prompt asset 的 trust/schema/repair contract；`dayu/host/README.md` 只承诺 Host accept/reject、internal feedback、projector/renderer 与 exact cap owner；`docs/host/design.md` 固定完整跨 owner 设计真值。未发现 ownership drift。
3. README trigger：根 README 没有用户入口、参数、工作流或排障变化，`dayu/README.md` 没有分层、依赖或装配变化；保持不改符合各自更新约束。
4. LLM-facing north star：新增文档明确不可信材料只是数据，自足定义 schema、业务语义、覆盖与 repair 动作；没有引入 filter、verifier、额外 schema 或 repair loop。未发现模型需要理解的 Host/Python/迁移内部术语。
5. validation：controller 接受两路独立复跑结果与 S4 implementation evidence：aggregate pytest `365 passed, 1 skipped`，pyright `0 errors`，两份 frozen JSON 可解析且无 diff，`git diff --check` 通过，read-only evidence checksum `13/13 OK`。
6. real-provider truth：Mimo 与 DeepSeek 均精确分类为 `network_unavailable` 后 exact skip；没有收到非空 candidate，因此 strict parse、governance accept、cap compliance 与 injection behavior 均是 `not_observed`。两路 review 均没有把 deterministic matrix 当成真实 behavior pass。

## Accepted residuals

- 真实模型行为仍为 `not_observed`；owner 是 S3 real-provider smoke 环境。网络和 credential 可用后按原 opt-in 命令重跑。
- 完整自然语言与 Conversation Memory evaluation 继续归既有 Issue 80；不扩大本 work unit。

## Frozen truth

- `docs/cli_ci_oracles.json` 未修改，SHA-256：`f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`。
- `docs/cli_ci_scenarios.json` 未修改，SHA-256：`7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`。
