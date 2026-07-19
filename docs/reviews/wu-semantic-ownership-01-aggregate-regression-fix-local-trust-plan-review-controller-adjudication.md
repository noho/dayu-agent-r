# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Local-Trust Plan Review Controller Adjudication

## 1. Gate identity

- 时间：`2026-07-19 08:52:24 +0800`。
- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation；不是新 WU，也没有重新打开独立旧 sub-WU。
- Gate：用户 local-trust 裁决写回后的完整 corrected-plan 双路 review 裁决。
- 用户裁决：本地 Config 与 Host SQLite / EventLog 属于同一受信任产品内部域；Host internal durable state 可以保留执行所需的 resolved API key / headers。Tool Trace 与 audit 不得泄露明文；既有 public、LLM-facing 与 operator-log 零泄露投影继续保留。

## 2. Immutable review inputs

- Final corrected plan：`docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md`，SHA-256 `afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252`。
- Host design：`docs/host/design.md`，SHA-256 `2be90cc2e107ce14fd5ee594c85e2a223217b9d6689b2d4a0cafba2adf3ec628`。
- UI design：`docs/ui/design.md`，SHA-256 `ed25d5d4577864cbf7ca6860aad043607921bd7db4f72cffb876c871fb99b4b7`。
- AgentMiMo review：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-review-mimo.md`，SHA-256 `951c851a37f05acb4737df15f7f501e7058292798270f41e5639b00e5e3029c5`。
- AgentDS final corrected review：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-review-ds.md`，SHA-256 `64b17d4d6788f9551c16ae89f2ffee75dee4b592563e09396a855b0dcd196da3`。
- AgentDS 首版没有完整读取总控，Controller 不接受该版流程证据；同一任务补读 `docs/host/issues-implementation-control.md` 全部 2313 行至 EOF 后，AgentDS 重新核验八个维度并保持 PASS。最终 corrected artifact 才是有效第二路证据。

## 3. Finding adjudication

- AgentMiMo：`PASS / finding none`。
- AgentDS final corrected review：`PASS / finding none`。
- Controller 接受两路共同结论：用户裁决已准确写回设计与计划；Tool Trace、audit、public HostEvent、LLM-facing material 与 logs 的排除语义分别有直接 projection owner 证据；五个新增 test-only paths 对应五个不同 owner，不是重复测试。
- Synthetic sentinel 必须同时证明 Host internal durable round-trip 与 Engine execution input 保留 exact value，并证明各禁止投影不含该 sentinel；不得使用 header 字段名黑名单、下游 repair、mock-only bypass 或新 secret infrastructure。
- Configured-value scan 只允许把 Config source 与 exact `USER_INPUT_ACCEPTED.effective_execution_config.config.runner_spec.headers` logical path 分类为 `ACCEPTED_TRUSTED_INTERNAL`；其它 Host logical path 计数必须为零。Tool Trace、audit、public/LLM/log/其它 output/review/diff surfaces 均为 `ZERO_REQUIRED`，必须逐类报告，不得合并 waive。

最终 ledger：

```text
accepted plan finding = 0
open plan finding = 0
rejected reviewer candidate = 0
blocking question = 0
design contradiction = 0
```

## 4. Scope decision

- 保持 exactly three slices；Slice 1 与 Slice 3 production allowlist 为空，Slice 2 production allowlist不变。
- `S1-SEC-F01` 是 no-code blocker closure，只增加五个 owner-level sentinel tests 与 semantic scan evidence；不得设计 Host-safe / Engine-only type split、header descriptor、secret resolver callback、secret manager、permission schema 或统一 tool authorization framework。
- Issues 142、151、175、177、178 与 Web / WeChat / render tracker scope保持 deferred；Topic 8/9 保持 no-code decision。
- Slice 1 实现可在新的 Controller resume authorization 下继续；Slice 2/3、code review、commit、aggregate deepreview、push/PR 与 closeout仍未授权。

## 5. Verdict

`PASS / CORRECTED PLAN ACCEPTED / SLICE 1 RESUME AUTHORIZED BY SEPARATE ARTIFACT`
