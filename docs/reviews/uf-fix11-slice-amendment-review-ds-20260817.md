# UF-FIX11 slice-boundary plan amendment review（DS 定向复审）

- 生成时间：2026-08-17 11:19:51 +0800（本机系统时钟）
- Review target：`docs/gateflow/uf-fix11-slice-boundary-amendment-20260817.md` 及其修订后的完整 plan
  `docs/gateflow/uf-fix11-company-meta-warning-plan-20260817.md`
- 前置证据：`docs/gateflow/uf-fix11-s1-slice-boundary-blocker-20260817.md`（639 passed, 1 failed）、
  `docs/gateflow/uf-fix11-plan-acceptance-20260817.md`（controller acceptance，A1-A10/DS-RR1/DS-RR2 裁决）
- Scope：只 review amendment 的 slice-boundary 决策与 gate 可执行性，不 review 已冻结的 §1-§9 业务契约本身
  （其已由两路 final re-review `pass` 关闭）；dirty diff 仅用于验证断点与 allowed-files 边界，不审查其代码质量。
- 结论：**pass-with-risks**（见 Finding-001/002/003，均可在文档层修复，不影响原子边界决策本身）

## 1. Assumptions tested

| # | Assumption | 验证结果 |
| --- | --- | --- |
| A1 | 原 Slice 1 落地即红：fresh 不同名称 producer 生成 `stage/preserve` intent，而 `_canonical_skip_requirements_are_met` 只接受 `keep/no intent` | **成立**。`upload_company_meta.py` dirty diff 已实现 `name_change_requested` 分支生成 preserve intent；`filing_upload_publication.py:385-386` 现行谓词要求 `decision.disposition == "keep" and company_meta_intent is None`。两者直接冲突，与 blocker 记录一致。 |
| A2 | blocker 红测期望与 accepted 业务设计不可同时成立，S1+S2 合并是唯一不固化错误语义的边界 | **成立**。`test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision` 当前断言 `commit_tokens == []`、`rollback == begin`、`company.stage_tokens == []`；新契约下这些断言全部翻转。生产者丢弃 intent、修改测试保住旧期望或单独提交红色 domain/storage diff 均被 amendment 正确排除（A1 rejected-with-reason 已裁决）。 |
| A3 | 一旦 parser 对 `SourceKind.FILING` 缺失 `warnings` fail-closed，所有 filing terminal producer 必须与 parser 同 slice 落地 | **成立**。`FinsUploadPipelineResult.from_pipeline_json`（ingestion_runtime.py:1729）当前按 `result.get(...)` 宽松读取；新增 fail-closed 后，SEC/CN 的 ok/skipped/failure builder 若不同步输出 `warnings`，现有 roundtrip 测试（含 `tests/fins/test_fins_ingestion_runtime.py` 中真实 `CnPipeline` 链路）立即红色。producer→parser 原子绑定是因果强制的，不是可选绑定。 |
| A4 | `from_pipeline_json` 全部生产 callsite 都在 allowed files 内，且可用显式 `SourceKind` 收敛 | **成立**。生产 callsite 仅 4 处，全部在 `dayu/fins/service_runtime.py:180/187/226/246`（SEC/CN filing=FILING，US/CN material=MATERIAL），该文件在 S1+S2 allowed 内。`direct_events.py` 等无 callsite。 |
| A5 | SEC/CN terminal producer 枚举完整，且改动不需要触碰 host facade（`sec_pipeline.py` 等非 allowed 文件） | **成立**。SEC 主 terminal 为 `host._build_result(...)`（sec_upload_workflow.py:280），失败为 `_build_sec_filing_failure_event`（4 个 callsite，经 384 行同一点）；CN 主 terminal 为 `self._build_upload_result(...)`（cn_pipeline.py:911），失败为 `_build_cn_filing_failure_event`（4 个 callsite）；CN 同步 `upload_filing` 委托 stream，无独立 producer。两处 builder 签名均为 `**payload` 透传，`warnings=` 走 kwargs 即可，host facade 零改动。 |
| A6 | `commit_batch` 收敛清单（§9.2：dayu 3 个定义、test 7 文件/9 定义、docling 3 定义）与代码 exact 对应 | **成立**。`rg -n "def commit_batch" dayu tests` 实测：dayu 3（Protocol + `_fs_storage_infra` + `fs_batching_repository`），tests 9 定义分布于 7 文件，`test_docling_upload_service.py` 恰 3 处。 |
| A7 | `-> None` 是 `CompanyMetaCommitOutcome \| None` 的合法协变 override，pyright 不能单独证明 fake 收敛 | **成立**。plan 关于“必须用 §9.2 清单 + `rg` + 行为断言双重验收”的写法是正确的风险控制。 |
| A8 | name-only metadata commit 后 final `CompanyMeta` bytes 不变（含 `updated_at`）可成立 | **成立**。`_company_meta_from_published`（company_meta_contract.py:371）在 `final_identity == current_published.ticker_identity` 时保留 `updated_at`；name-only preserve 场景 identity 不变，§8.3 的逐字段/序列化 bytes 不变测试断言有代码支撑。 |
| A9 | SKIP+preserve 的 capability 转交顺序（stage → `batch_terminal_started=True` → `commit_batch`，此后 caller 不得再 rollback）与现有 PUBLISH 分支模式一致 | **成立**。`execute_prepared_filing_publication` 现有 PUBLISH 分支在 743 行先置 flag 再进 commit owner；`finally` 在 flag 为 False 时才 rollback（756 行）。DS-RR2 的顺序要求可直接落地。 |
| A10 | S1+S2 不改动 Host/Engine/material/oracle/scenario/frozen evidence，且改动不需要这些文件的配合 | **成立**。A5 已证 host facade 免改；material terminal payload 结构性不含 `warnings`，parser 对 `SourceKind.MATERIAL` missing→空 tuple 的规则不触碰 material producer；`SourceKind` 已存在于 `dayu/fins/domain/enums.py`（allowed 外但无需改动）。 |

## 2. Findings

### Finding-001-未修复-中-blacker 红测的期望契约改写未被 amendment 显式规格化

- **位置**: amendment §「修订决策」3-5、plan §10 S1+S2「Stop condition / Completion boundary」、§13.6
- **问题类型**: 不可直接实施（欠规格）/ open question 未收敛
- **当前写法**: amendment 与 plan 只说 blocker 红测必须“在同一 focused gate 关闭”“不得 deselect、不得分类到 S3”，但从未写明该测试在新契约下的期望终态是什么。
- **反例/失败场景**: `test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision` 现有断言是
  `commit_tokens == []`、`rollback_tokens == begin_tokens`、`company.stage_tokens == []`。新契约下这三个断言全部必须翻转
  （name-only preserve → SKIP + metadata-only commit → `commit_tokens == begin_tokens`、`rollback == []`、
  `company.stage_tokens == begin_tokens`、`warnings` 恰 1 个、final name 不变、source tree hash 不变）。
  “关闭红测”在字面上存在两种解读：(a) 让旧期望原样变绿——在新契约下不可能，除非 producer 丢弃 intent 或
  publication 加特例（两者均被冻结契约与 stop condition 禁止）；(b) 改写测试期望——正确但未被授权化、未被列出断言契约。
  实施 agent 面对 (a) 不可能、(b) 无规格的局面，可能改写出一个丢失去“stale action/company decision 被丢弃、
  final truth 不被单个 filing 改写”原始回归意图的弱测试，或在 review loop 中反复拉锯。
- **为什么有问题**: 本 amendment 的全部意义就在这个测试与 slice boundary 的关系上；把它标记为必须关闭却不同时
  冻结其关闭后的断言契约，等于在 focal point 留下规格空洞，与 plan 其余部分“code-generation-ready”的粒度不一致。
- **直接证据**: blocker 文档 §「确定性红测」指名该测试；`tests/fins/test_sec_pipeline_upload_filing_stream.py`
  `test_upload_filing_fresh_recheck_discards_stale_action_and_company_decision` 现行断言逐项翻转（上文反例）；
  plan §10 S1+S2 Tests 只给了对称测试的一般描述（“name-only skip warning”“alias-on-skip durable”），
  未把该既有测试的改写契约列为 exact change。
- **影响**: 实施 Agent 跑偏或弱化回归 / review 不可验收 / 后续返工
- **建议改法和验证点**: 在 plan §10 S1+S2「Exact changes」或「Tests」中增加一条：明确 blocker 测试在新契约下的
  期望终态（`skipped` + metadata-only commit 的 begin/commit/rollback token 新形态 + `warnings == [规范 warning]` +
  final company meta bytes 不变 + source tree hash 不变），并保留其对“fresh recheck 丢弃 stale preflight action/decision”
  的原始回归语义。验证点：amendment review 通过后，实施 agent 不必自行推断该测试的合法终态。
- **修复风险（低）**:
- **严重程度（中）**:

### Finding-002-未修复-低-§12.2 combined regression 未绑定到 S1+S2 review/commit boundary

- **位置**: plan §10 S1+S2「Completion / review / commit boundary」、§12.2、§15
- **问题类型**: 测试缺口（gate 边界欠明确）
- **当前写法**: §10 的 S1+S2 acceptance 前置只列“完整 focused suite 绿色 + 逐文件 coverage + 全仓 pyright + static
  boundary checks”，未提及 §12.2 combined regression（`tests/fins` + `tests/cli/*` + `tests/service/*`）；
  §15 Completion format 却要求交付说明报告 combined regression 结果。两处对同一验证项的存在性、时点不一致。
- **反例/失败场景**: 实施 agent 按 §10 字面执行，S1+S2 提交后 `tests/cli/test_fins_commands.py` 或
  `tests/service/test_fins_wait_adapter.py` 若因 parser/SourceKind 变更转红，红测会带着“accepted slice commit”进入树。
  （本次实测这两个测试面与 S1+S2 改动面的耦合很弱：CLI 测试用 fake SEC pipeline、不触真实 parser；
  wait adapter 测试无 `from_pipeline_json`/`FinsUploadPipelineResult` 耦合；direct stream 测试不 parse pipeline JSON。
  因此实际转红概率低，但 gate 的闭合性不应依赖“碰巧没耦合”。）
- **为什么有问题**: 用户明确要求挑战“coverage/pyright/review/commit gate 是否可执行”。coverage gate（§12.3.1）
  实际运行的是 `pytest tests/fins`（覆盖全部 fins 测试），但 `tests/cli`、`tests/service` 两个套件不在任何
  S1+S2 前置命令中；§15 又暗示它们被报告，边界处于欠定状态。
- **直接证据**: §10「Completion / review / commit boundary」清单 vs §15 第 2 条 vs §12.2 命令。
- **影响**: review 不可验收（gate 边界歧义）/ 低概率红测进入 accepted commit
- **建议改法和验证点**: 二选一并写死：(a) S1+S2 acceptance 前置补入“§12.2 combined regression 全绿”；
  (b) 显式声明 combined regression 由 S3 的 coverage gate（其命令本身就是 §12.2 的超集）关闭，并在 S1+S2
  boundary 注明排除理由。验证点：S1+S2 提交前无任何未 gate 的红色套件。
- **修复风险（低）**:
- **严重程度（低）**:

### Finding-003-未修复-低-共享文件双 slice 边界缺符号级精度

- **位置**: plan §10 S1+S2「Allowed files」中 `dayu/fins/ingestion_runtime.py`（仅 filing/material warnings parser
  contract 与 typed upload result）、`dayu/fins/service_runtime.py`（仅同步 parser callsite 的显式 `SourceKind`）与
  S3「Allowed files/Exact changes」、§6.6
- **问题类型**: 切片过粗（文件级共享、符号级未定）
- **当前写法**: `ingestion_runtime.py` 与 `service_runtime.py`（及其测试文件）同时出现在 S1+S2 与 S3 allowed files，
  切分依据只有 prose 描述。§6.6 把 `FinsUploadPipelineResult` 与 `FinsUploadResultSummary` 的 `warnings` 字段写在同一句，
  未按 slice 归因——`FinsUploadResultSummary` 同属 “typed upload result” 语义，实施 agent 可能把它当作 S1+S2 的
  “typed upload result” 提前加入字段（侵入 S3 的 durable projection），也可能反向遗漏。
- **反例/失败场景**: 实施 agent 在 S1+S2 给 `FinsUploadResultSummary` 加字段并顺手改 `to_json_summary()`（durable
  投影本属 S3）→ S1+S2 与 S3 的 exact changes 边界漂移，S3 前置“parser 已冻结、summary 未动”失效；或反过来把
  summary 字段推迟导致 S1+S2 的 parser invariant 无处落地。两个方向的漂移都不被现有 stop condition 直接拦截
  （stop condition 拦的是语义越界，不拦同文件内的符号归属）。
- **为什么有问题**: 文件级 allowed list 在共享文件上无法防止 scope 漂移；plan 其余部分强调“禁止范围泄漏”，
  共享文件正是最容易泄漏的位置，应给出符号级边界。
- **直接证据**: §10 S1+S2 allowed 注释 vs S3 allowed 注释；§6.6 首条未分 slice 的同句契约。
- **影响**: 实施 Agent 跑偏 / 范围泄漏 / 后续返工
- **建议改法和验证点**: 在 S1+S2 与 S3 各列一张共享文件的符号级 allowed changes 清单（如 S1+S2：
  `FinsUploadPipelineResult.from_pipeline_json` 签名 + `warnings` 解析 + `__post_init__` invariant；
  S3：`FinsUploadResultSummary.warnings` + `to_json_summary()` + `_upload_summary_from_result` 透传等），
  §6.6 同句按 slice 拆开归因。验证点：两个 slice 的 exact changes 互不重叠、覆盖完全。
- **修复风险（低）**:
- **严重程度（低）**:

## 3. 关于本次定向挑战的正面裁决（无 finding 的部分）

1. **S1+S2 是否为最小可绿原子边界——是。** 因果链已逐环验证：producer name-only preserve intent →
   canonical skip 谓词扩展 → SKIP metadata-only commit → `commit_batch` typed outcome → `UploadOperationResult`
   内部载体 → `FilingUploadPublicationOutcome.warnings` 投影 → SEC/CN terminal 序列化 → fail-closed parser →
   `SourceKind` 显式 callsite。每环都直接由前一环变红或语义断链强制；拆分任何一环都会制造“测试绿但语义红”
   （如 parser 晚于 producer 落地时 typed 层静默丢弃 warning）的中间态，或直接红色中间态。A1 的
   “producer 丢弃 intent” 替代方案已在 controller 裁决中 rejected-with-reason，此处不重开。
2. **是否漏文件/测试/producer/parser——未发现遗漏。** `commit_batch` 收敛清单与代码 exact 对应（A6）；
   生产 `from_pipeline_json` callsite 全集已收敛（A4）；SEC/CN 全部 filing terminal producer 已枚举且改动
   不需要非 allowed 文件配合（A5）；CN 同步入口委托 stream 无独立 producer；material/download 边界由
   `SourceKind.MATERIAL` missing→empty 规则与 `requested_company_name=None` 默认值保持零语义漂移。
3. **是否错误把可独立投影绑入——否。** SEC/CN producer 与 parser 的绑定由 A3 的 fail-closed 方向强制
   （`tests/fins/test_fins_ingestion_runtime.py` 含真实 `CnPipeline` 链路，CN 缺失 warnings 必然红）；
   `service_runtime.py` callsite 由无默认值参数机械强制；warning codec 是 shared publication 的同 slice 消费方。
   S3 的 direct/CLI/wait 投影正确地留在后续 slice，未提前绑入。
4. **coverage/pyright/review/commit gate 可执行性——可执行，两处边界待收紧（Finding-002/003）。**
   §12.1 单命令 focused suite 明确包含 blocker 测试且禁 deselect；§12.3.1 coverage 命令与 12 个 allowed 生产文件
   exact 对应；§12.4 pyright 全仓命令并正确声明“pyright 不能单独证明 fake 收敛”；§12.5 rg/人工清单逐项与
   代码事实吻合（含 `hasattr|getattr|Any|object` 扫描）；review/fix/re-review 单 loop + 单 protected commit
   的 gate 与该仓库既有 gateflow 惯例一致。
5. **红色中间态与范围泄漏——amendment 的处置正确。** 当前 partial diff 被显式声明为未接受工作区状态、
   不得 stage/commit；原 Slice 1/2 与任何红色中间态的分次提交被明确禁止；§13.6 为“恢复实现后 blocker 红测
   无法在 allowed files 内关闭”预留了回到 plan amendment 的失败出口；§9.4 禁止列表与实测 allowed 需求
   无冲突（host facade 免改是代码事实，非侥幸）。

## 4. Open questions

- OQ-1：S1+S2 accepted slice commit 的**文件集**是否包含 plan/amendment 两个 gateflow doc？commit message 已定
  （`gateflow: accept UF-FIX11 company metadata warning S1+S2`），但 commit 内容边界未写明；仓库既有惯例
  （如 c7f5ddb1）是 docs+code 同 commit，建议在 amendment acceptance 时一并明确，避免“doc 单独提交”被误判为
  红色中间态提交。

## 5. Residual risks 与追踪去向

- R-1：S1+S2 → S3 之间，typed warning 已产生并经 parser 保留，但 direct/CLI/tool 尚不投影，最终用户暂时不可见。
  **接受**：本地 commits 不对外发布（无 PR），S3 是唯一后续实现入口且前置为 accepted S1+S2 commit；
  追踪去向：plan §10 S3 Prerequisite。
- R-2：coverage gate 对 `sec_upload_workflow.py`/`cn_pipeline.py` 的整文件 ≥80% 依赖 tests/fins 内既有
  material/download 路径覆盖；若当前低于 80% 会在 S1+S2 gate 触发补测。**接受**：gate 自纠偏，plan 已禁止
  pragma/ignore 绕过；追踪去向：plan §12.3.1 逐文件报告。
- R-3：metadata-only skip 对 `_validate_complete_source_tree` 的 fail-closed 权衡（§13.4.4）与 name-only 物理
  publication 成本（§13.4.1）为 accepted tradeoff，非本 amendment 引入。**接受**：已分类 `fixed in current slice`/
  `assigned to later work unit`；追踪去向：plan §13.3/§13.5。

## 6. Final conclusion

**pass-with-risks**

amendment 的核心决策（S1+S2 不可拆分的原子边界、保留 partial diff 但零独立 acceptance、单 loop 单 commit、
S3 只做投影）有完整因果链与代码事实支撑，最小性与原子性主张成立；所有 gate 命令可执行且与代码现状 exact 对应；
未发现导致 amendment 不应进入实现的 blocker。三个 findings 均为文档层规格修补：
Finding-001（中）应在 amendment 接受前补齐 blocker 测试的改写后断言契约；
Finding-002/003（低）可在同轮 fix 中一并收敛。修复后即可进入 S1+S2 implementation。
