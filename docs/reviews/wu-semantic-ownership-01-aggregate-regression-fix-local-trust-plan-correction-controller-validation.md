# WU-SEMANTIC-OWNERSHIP-01 Aggregate Regression Fix Local-Trust Plan Correction Controller Validation

## Gate identity

- Umbrella：`WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- Gate：2026-07-19 local trust-boundary user decision后的 design-truth / aggregate plan correction validation。
- Status：`PASS / READY FOR DUAL COMPLETE PLAN REVIEW / IMPLEMENTATION NOT AUTHORIZED`。
- 本 artifact 不记录任何 configured secret value、secret ref 名称或命中正文。

## Validated correction

AgentCodex artifact：

- path：`docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-correction-codex.md`
- SHA-256：`116e9a77428cb6ee133a5c31ebb82c6be629fa1de56ecc1c8a53fbda70532f10`
- disposition：AgentCodex亲自完成，未启动subagent；完整读取真源与先前Slice 1 evidence；未修改product code、tests、README、control或其它review artifact。

Controller完整读取 correction artifact、三份修订文档与当前 diff，并接受以下边界：

1. 本地 Config 与 Host SQLite/EventLog是同一 trusted internal product domain。
2. Service解析secret并构造resolved typed `RunnerSpec`；Host可以接收并把exact effective execution持久化为内部canonical truth。
3. Tool Trace、audit、HostEvent/read/outbox、memory/compact/evidence、LLM-facing runner observation与operator logs不得投影provider secret明文。
4. 当前直接代码证据与fresh surface scan没有发现真实projection leak；`S1-SEC-F01`关闭为no-code blocker。
5. 原三个implementation slices数量、依赖顺序与production allowlist不变。Slice 1仅增加五个projection-owner synthetic-sentinel test paths和分surface scan。
6. 不引入Host-safe/Engine-only split、header descriptor、secret resolver callback、secret manager或统一tool authorization framework；deferred Issues保持不变。

## Exact path/hash validation

本 correction gate only paths：

| Path | Final SHA-256 | State |
| --- | --- | --- |
| `docs/host/design.md` | `2be90cc2e107ce14fd5ee594c85e2a223217b9d6689b2d4a0cafba2adf3ec628` | modified |
| `docs/ui/design.md` | `ed25d5d4577864cbf7ca6860aad043607921bd7db4f72cffb876c871fb99b4b7` | modified |
| `docs/host/wu-semantic-ownership-01-aggregate-regression-fix-plan.md` | `afaa18c5608e6eeae0046318865bd1b3dd2f9a176c4b0739aa5b099e0ae3a252` | modified |
| `docs/reviews/wu-semantic-ownership-01-aggregate-regression-fix-local-trust-plan-correction-codex.md` | `116e9a77428cb6ee133a5c31ebb82c6be629fa1de56ecc1c8a53fbda70532f10` | added |

Protected evidence：

- `docs/engine/design.md` unchanged SHA-256：`f209126046ffdb8a55f41a538c929842817f328f8c3bbc8f080b8c1c5489bf31`。
- `tests/service/test_host_admin.py` unchanged protected delta SHA-256：`5acf57a06d1c7fee82a27ae0c3ccdfcddfe745a42439a514c0551665904f96db`。
- `tests/tools/web/test_smoke_web_ci.py` unchanged protected delta SHA-256：`86968b937d4289d29427a2bd68934a074ca0499dfa3563ec326eae73f2432ee3`。
- `tests/host/test_public_compact_smoke.py` unchanged protected delta SHA-256：`f60a1d6e190c948986be355fc66ad71cb64e207691e8a12646ea23cbdcc66169`。
- staged tree为空。
- `git diff --check`通过。
- 旧冲突文字“Host不接收API key明文”“EventLog不能包含API key/headers”“secret不写入Host durable state”已从当前Host/UI design中删除或按用户裁决收窄。

## Direct projection evidence disposition

- Tool Trace：canonical event whitelist不包含`USER_INPUT_ACCEPTED`，typed extractor不复制effective execution config。
- Audit：audit line builder输出固定metadata/ref/digest字段，不复制raw EventLog payload。
- Public HostEvent/read：typed projection不复制raw payload；该source event不生成activity正文。
- LLM-facing input/memory/compact：user-input consumers只读取`display_text`等显式业务字段；Engine execution `RunnerSpec.headers`不是LLM-facing projection。
- Logs：current callsites与fresh output scan无resolved header value命中；Topic 8既有Engine异常脱敏保持不变。

Fresh configured-value evidence按用户裁决分类：唯一非零结果是受信任Host internal SQLite中的exact effective runner headers；Tool Trace、audit、logs、其它outputs、review surface和git diff均为零。该结果验证plan的semantic classification，不授权按任意路径或文件名waive secret exposure。

## Validation decision

- Correction is internally consistent and ready for adversarial dual plan review。
- AgentMiMo/AgentDS必须完整审查design writeback、三-slice plan、五个新增owner-test边界、real scan分类与no-overdesign约束。
- Review必须重点挑战：五个tests是否重复/过量、是否能用更小owner-level contract闭环；audit/trace owner证据是否真实；trusted internal classification是否过宽；plan是否误把Engine execution input当LLM-facing；stop condition是否保持唯一owner。
- AgentCodex implementation、test changes、Slice 1 code review/commit、Slice 2/3、aggregate deepreview、push/PR/closeout仍未授权。
