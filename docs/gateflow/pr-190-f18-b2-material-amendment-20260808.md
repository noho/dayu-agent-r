# PR 190 F18 B2 material amendment（2026-08-08）

## Controller 决定

`cap-constrained-memory-replacement@1` 的 registry invocation、required evidence 与 Oracle predicates 只要求 previous
EvidenceFact 和 new evidence 在 `evidence_fact_item_cap=1` 下形成真实竞争；它们不要求 FY2024/FY2025 配对，也不要求 R1
source 完全没有 FY2025 年份信息。原 plan 把 FY2024 财务材料隔离写成唯一 setup，扩大了 owner contract。

因此，fixed profile 路径不构成 blocker。最小 scenario correction 是：R1 用同一真实 AAPL corpus 中与 R2 财务目标隔离的
business-risk material 形成 canonical previous EvidenceFact，R2 再取得独立 FY2025 财务 EvidenceFact，R3 观察两者在 cap=1
下的 keep/omit、accepted provenance 与 omitted exact complement。产品、profile、scene、harness均不修改。

R2在 baseline accepted 后同样先完成当前文档 grounding，再只读 `s_0013`（Part II Item 8，`61,252 chars / 9,744
words`，content SHA-256 `d1a11c06db1a08e644946e6869cc152aa55353c5437214c1c2b85a1e62065607`）。该真实
material包含目标 `416,161/133,050`，并为下一次 R3 `ORDINARY` boundary 提供足够的 completed R2 material；不得改用只含
358 words 的 `s_0013_c03` 后再靠额外 prompt/tool padding 追阈值。

## Provider-free owner evidence

- bundle-relative source：`workspaces/formal-chain-03/portfolio/AAPL/processed/<identity>/sections.json`；
- document：`fil_0000320193-25-000079`；
- section：`s_0003`，Part I Item 1A Risk Factors；
- owner content：`68,039 chars / 9,782 words`；
- content SHA-256：`563b193a9c31061fa48f25b1b27709e94150d5c9cfceace80ce2a961b6a23b36`；
- exact negative scan：不含 `416,161`、`133,050`、`391,035`、`123,216`、`21.7`、`18.2`；
- typed legality：先以 `get_document_sections(ticker, document_id)` grounding，再以
  `read_section(ticker, document_id, ref=s_0003)` 读取；production `read_section_max_chars=80,000`，可完整承载该 section。

该内容足以使 completed R1 material 在下一次 `ORDINARY` boundary 跨过 soft threshold；R1内 tool-result continuation 仍由
五阶段 Host owner 决定继续，R2 pre-start 才是 baseline compactor 的唯一目标。这个判断来自 typed context stage 与直接
material size，不从错误字符串、模型回答或顺序猜测。

## Frozen effective iteration owner

execution profile声明24，但 production interactive scene 以 `scene_override` 产生 effective `max_iterations=20`。
`20 loops + 最多1次 force_answer = 21/Run` 是 typed hard cap；原 plan 的25/Run只保留为更宽的外部停止 ceiling，不得修改
workspace scene去凑24。

## 已消耗但不覆盖的运行

| Attempt | Canonical terminal | Ordinary calls | Wall | Compactor | Disposition |
| --- | --- | ---: | ---: | ---: | --- |
| `formal-chain-01/R1` | `RUN_SUCCEEDED` | 5 | `27.5583s` | 0 | non-covering；broad financial source含R2目标事实 |
| `formal-chain-02/R1` | `RUN_SUCCEEDED` | 2 | `15.0313s` | 0 | non-covering；typed fiscal filter返回0 facts |

累计7个ordinary calls、`42.5896s`。原始 screen、argv、按键、terminal、durable snapshots与raw PTY保持不变，不覆盖、不重标
PASS；它们继续计入统一的 `1620s` provider execution、`1800s` scenario cap与call ledger。有效候选链仍最多3条，每条必须从
fresh workspace第一次 opener 起固定同一 profile identity。

## Gate

本 amendment 只修正 scenario material 与预算解释。MiMo/DS 两路独立 plan review 均为 PASS 前不得再调用 provider；review
若发现 owner legality、source isolation、预算或 fresh-chain 约束缺口，则停止并修订，不能用 provider 试错。

## 执行与 publication closeout

MiMo/DS 两路独立 plan review 均已 PASS，artifacts 分别为
`docs/reviews/plan-review-20260808-172014.md` 与 `docs/reviews/plan-review-20260808-172234.md`。F18 实际保留两条
canonical success 但 non-covering 的 provider segment，以及一条在 CLI spawn 前因 empty prompt 被 harness precondition 拒绝、
provider 未启动的 segment；前两条累计7个ordinary calls、`42.5896s`，compactor calls为0。纠正后的合法 segment 准备完成时，
frozen monotonic `global_deadline - 180s` 启动门已经关闭，因此按预算 owner 停止，B2 verdict为`needs-more-evidence`，不补跑、
不覆盖旧结果，也不接受 Oracle。

冻结 public bundle `pr190-f18-b2-fixed-XUmH8YBg` 的最终refs与SHA-256为：

- `evidence/public/observed-behavior-report.md`：`0969738ba5d75b4749b785fc6d8203cfd53e55a6cf850cbd3ad2408eacc3f8aa`；
- `evidence/public/observation-summary.json`：`1bc5eeb1f2c5537e0e5ebd60ad7f6e06c244f8d10802bb2cb6a42cd6d65d2457`；
- `evidence/public/material-audit-summary.json`：`6399d1280a7c567ed96e563739f0338b32371f01ea3c578357582ff38c15af8f`；
- `evidence/public/pre-provider-calibration-summary.json`：`2b855885e5820bf2e902b64b3352425cef8486498bf17ae8655c14031436baa1`；
- `evidence/public/digest.json`：`36fd642ad1700a7386ad7263bd1ef52496ba465ffea5dd367abcc2f175e4a627`；
- `evidence/public/secret-scan.json`：`40f7885d6d1c517c2db40289d636b02a2cc3837bc5c04081f15432ad294e4f47`。

最终scan覆盖5个被扫描文件、`27,450` bytes，secret/path/errors均为0。`secret-scan.json`之后没有public写入；B2继续保持
`unadjudicated`，registry继续为`calibration`，overall readiness继续为not ready。

### Publication conformance finding

final review确认上述六个顶层文件SHA与final scan统计本身正确，但冻结bundle不能裁决为publication conforming：

1. `observation-summary.json.material_audit_sha256` 为
   `37eee3c9665c21874b8caf545acd0a49af0e2d5faa69a52a257ff4702acf10e4`，既不等于
   `material-audit-summary.json` 文件SHA `6399d128...`，也不等于该JSON的canonical SHA `18284f2e...`；字段没有声明其它
   digest domain，不能由消费者确定其owner语义。
2. accepted plan要求每条attempted chain发布path-redacted public Host resolver/Tool Trace analysis JSON/Markdown，并发布
   `execution-index.json`；`observation-summary.json`还必须包含per-chain budgets、actual counts与terminal refs。冻结public tree
   缺前两类文件，summary也只有聚合ledger与简化attempt outcome/reason/ref。private capture和report文字不能替代public contract。

`secret-scan.json`是final writer，故不能在F18 bundle内回写修复而破坏immutable publication。F18 publication verdict固定为
`FAIL/nonconforming`；F19必须在新bundle中从source of truth生成并校验明确digest字段，发布完整execution index与per-attempt
analysis后再执行新的final scan。
