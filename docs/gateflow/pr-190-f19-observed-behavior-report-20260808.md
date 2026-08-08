# PR 190 F19 B2 observed behavior report（2026-08-08）

## Verdicts

- Product/setup implementation：`PASS / no product change`。F19只使用双路复审通过的run-owned external driver、fresh fixed
  profile与真实AAPL材料；没有修改产品、schema、scene、profile、analyzer、测试或README。
- Real observation：`needs-more-evidence`。两条fresh chain共执行5个真实MiMo segment，Host均记录canonical
  `RUN_SUCCEEDED`，但12次ordinary runner input没有产生任何`CONTEXT_COMPACTED`或compactor response。
- Publication：`FAIL / nonconforming`。F19补齐count/terminal refs、每条attempted chain的path-redacted public Tool Trace
  JSON/Markdown与`execution-index.json`，final scan有效且digest独立复算一致；但冻结`observation-summary.json`的三个
  chain entries均缺少plan要求的逐链budget及deadline owner ref/SHA。
- B2 Oracle：`unadjudicated`。本报告不替用户接受
  `interactive.interactive.g06.cap-constrained-memory-replacement@1`。
- Overall readiness：`not ready`；registry保持`calibration`。

## Frozen setup and scope

- bundle id：`pr190-f19-b2-2q6y6X3b`；只通过bundle-relative refs引用public/private evidence，不发布机器私有绝对路径。
- target product commit：`ce0c171a022a073c6355ace44e7c5e34a668d4bb`；production CLI SHA-256：
  `b44f70ec0117c7aef44ea7ff56d559ed8be9c8fd8b380855f4169a399d7f7cae`；model：`mimo-v2.5-pro-plan`。
- 三个workspace只复制immutable `config/`与真实AAPL `portfolio/`；首次opener前没有`.dayu`或任何历史durable/attempt state；
  三份input-tree SHA-256均为`a30bebd917586eee1349650134df9e96c7ad6dbeec26ecc35867b7c7fa216460`。
- fixed profile digest：`54368eb2113db96656d35010cf5db228b3483cfc140651e3e5ddcf8db10036b4`；
  EvidenceFact cap为1 item / 160 chars；scene owner的effective `max_iterations=20`，typed hard cap为21 calls/Run。
- provider budget冻结为1800秒global window、180秒finalization reserve、每chain最多540秒；F19实际启动5个segment，第三链按
  bounded-minimal stop未创建deadline、未调用provider。
- F18两条non-covering与一条provider-not-started记录仍留在原immutable failed bundle；F19没有复制、覆盖或重标它们。

## Direct observations

1. `s_0003`为68,039 chars / 9,782 words，目标值`416,161`、`133,050`、`391,035`、`123,216`、
   `21.7`、`18.2`全部absent；`s_0013`为61,252 chars，包含FY2025目标`416,161`与`133,050`，
   `21.7`与`18.2`absent。
2. Chain 01 R1/R2分别形成risk fact和FY2025 sales/operating-income fact；两段均遵循
   `get_document_sections -> read_section`，canonical terminal sequences为`3→37`、`39→73`。R2后compaction count为0，
   因此R3/R4没有启动。
3. Chain 02 R1/R2/R3的canonical terminal sequences为`3→37`、`39→62`、`64→76`。R2取得相同FY2025值并继续明确
   `21.7%/18.2%`未验证，但跳过prompt要求的前置`get_document_sections`；该instruction drift原样保留。R3后compaction
   count仍为0，因此R4没有启动。
4. 五个PTY process在cleanup EOT后均以process exit 1结束；独立Host lifecycle owner对同五个Run均记录
   `RUN_SUCCEEDED`。两个事实分别保留，不用process状态覆盖canonical terminal，也不反向把canonical success改写成process exit 0。
5. 每条attempted chain均记录6个`CONTEXT_BUDGET_EVALUATED`与6个`RUNNER_CALL_INPUT_ASSEMBLED`；production public
   Tool Trace analysis均为0个compactor response。没有出现`runner_candidate_invalid`或产品failure。

## Mandatory B2 evidence

| # | Requirement | Status | Owner evidence |
| ---: | --- | --- | --- |
| 1 | real output caps in initial compactor input | `needs-more-evidence` | compactor input未产生；1/160仅在Host construction owner确认。 |
| 2 | Host cap/usage audit | `partial / needs-more-evidence` | 12次canonical budget evaluation已观察，但无compact operation/input usage。 |
| 3 | accepted constrained replacement | `needs-more-evidence` | 无`CONTEXT_COMPACTED` terminal。 |
| 4 | previous EvidenceFact keep/omit | `needs-more-evidence` | 无accepted baseline进入replacement boundary。 |
| 5 | FY2025 accepted provenance且不升级21.7%/18.2% | `needs-more-evidence` | ordinary succeeded output中观察到SEC provenance及unsupported ratio约束，但没有compactor接受该fact。 |
| 6 | accepted provenance与omitted exact complement | `needs-more-evidence` | 无accepted replacement。 |
| 7 | same-boundary repair与budget-exhausted fallback | `needs-more-evidence` | 无proposal/repair/fallback compactor call。 |
| 8 | artifact/EventLog/Memory/RunInput/public Tool Trace同源 | `needs-more-evidence` | 无compact artifact或accepted compact truth。 |
| 9 | fresh reconnect消费同一accepted truth | `needs-more-evidence` | R4 prerequisite按约束保持关闭。 |
| 10 | screen/argv/keys/exit/files/logs/Tool Trace/SQLite前后及scan | `observed for attempted segments` | 每个attempt均有private capture manifest，公开Tool Trace已脱敏，最终scan有效。 |

## Publication identity

- `evidence/public/observed-behavior-report.md`：
  `131ae48c429e7831760041dba7d65d4fa3efc697ea1007ec25e2bd6b09f26079`；
- `evidence/public/observation-summary.json`：
  `78883564cbff492c38bad7eae0953cf117bd14443ef978b4b9cb56d21acade34`；
- `evidence/public/execution-index.json`：
  `30772500c6c337e2489e01dab7539b61a99928aa5ff5347af8d216b2a5555938`；
- `evidence/public/digest.json`：
  `b9215b71938922d1fe381a987d1022635cf321df15dc21a22a3ebc1364d00bbb`；
- final writer `evidence/public/secret-scan.json`：
  `716d2128233fc7ce023621e1542afb948f108dd2f5a6fa8336a76882fa9019b4`。

Final scan覆盖94个evidence regular files、2,991,916 bytes与4个可用credential exact values；secret match、public绝对
私有路径、raw database、symlink与scan error均为0。final scan后没有public写入。Controller另行只读复算digest声明的9个文件，
file-byte SHA与size mismatch均为0。

上述hygiene与byte-integrity结论不关闭publication semantic finding：顶层统一`per_chain_cap_seconds=540`只能表达共同cap，
`material-calibration-wrapper-summary.json`中的5份budget是逐segment spawn-time projection；二者都不能替代冻结计划要求的
`observation-summary.json.chains[]`逐链budget。Chain 01/02的private deadline owner files也没有在summary/execution index中以
relative ref与file-byte SHA绑定，Chain 03没有显式的no-deadline逐链budget record。public tree已由final scan封存，本work unit不得
原地补写。

## Controller decision

固定profile方案在owner边界下合法并成功运行，旧Trial2不可恢复诊断不构成该setup的前置；但本次真实材料量没有在reviewed
state-machine停止点前触发compactor。该结果不是产品缺陷证明，也不能满足B2 mandatory predicates。F19应以
`implementation PASS / observation needs-more / publication FAIL / Oracle unadjudicated / overall not ready`诚实closeout；若继续
B2，必须由新的goal确认一个provider-free可证明的trigger setup，不能在本work unit内继续校准或追加provider。
