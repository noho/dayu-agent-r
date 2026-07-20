# WU-SEMANTIC-OWNERSHIP-01 R06 fixed plan re-review Controller 裁决

## 1. 裁决对象与结论

- fixed plan SHA-256：`ed057fdf5bdcfb463d82f76b74da5cebe50548ce1e63c01b9cf67e02fbd03e43`
- AgentMiMo re-review：`docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-rereview-mimo.md`，verdict `PASS`
- AgentDS re-review：`docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-rereview-ds.md`，verdict `PASS-WITH-FINDINGS`
- plan-fix Controller validation：`docs/reviews/wu-semantic-ownership-01-r06-fins-transaction-complete-publication-plan-fix-controller-validation.md`

Controller verdict：`PASS / PLAN_ACCEPTED_FOR_EXACT-SCOPE_LOCAL_COMMIT`。

两路都确认 `R06-PF-01..08` 已全部关闭；原始 MiMo/DS material、blocking、HIGH、MEDIUM findings 均有最终 closed/no-action/withdrawn 状态。Re-review 没有产生 accepted current plan finding、未决产品问题或 blocker。当前只授权 exact-scope R06 plan/evidence/control local commit；implementation 仍须等真实 commit SHA 写回总控并进入 S1 gate。

## 2. Controller 对新 observations/findings 的裁决

### RR-C-01 — MiMo 三项 evidence observations

**来源**：MiMo `R06-REREVIEW-001..003`。

**裁决**：全部 no-action，均已被 accepted plan 明确覆盖。

- standalone 6-K 当前分别构造 wrappers：plan root-cause 表已记录“6-K repair 还分别建 core”，§3.5/§7.3 已要求它先创建一个 shared `_FsRepositorySet`，再从同一 set 装配 batching 与全部 wrappers。
- `_ticker_dir_for_read` 当前 staging 路由：§3.4 已要求 published read 只读 published tree，§7.1 又在 S1 删除 `_require_batch_owner` 与 ambient routing；这是 S1 直接实现点。
- blob core `_get_handle_meta` 前置：§5.1 已明确 blob-first 时不得要求 source meta，只验证 batch/core/ticker/contained path；这是 S2 直接实现点。

MiMo 关于“当前 I/O 在毫秒级、不会成为 bottleneck”的性能断言没有测量证据，Controller 不接受该事实判断。当前裁决只依赖 accepted contract：exclusive publication lock 按 ticker 分片、read guard 只覆盖一次 meta/list/bytes I/O 或 fd open，长文件读取不持锁，并由真实并发 tests 验证长 writer 不阻塞 reader。若 implementation 证明该 exclusive lock 使必要 I/O 形成不可接受瓶颈，按 stop condition 回 Controller；不得据无测量推测改为进程内锁或新 lock framework。

### RR-C-02 — public-to-public read composition inventory

**来源**：DS `R06-REREVIEW-R01`，LOW。

**裁决**：no-action implementation observation，不是 plan gap。

Plan §4.2 已对闭集作全称约束：每个 public published read outer entry 只获取一次 guard，public-to-public 组合必须抽取 private unguarded helper，禁止再次获取非重入锁；§7.1 tests 与 §8.4 又要求 composed public entry 证明 outer 只获取一次且不自死锁。这比列出易陈旧的方法名 inventory 更自适应，且实现必须由真实调用图审计所有 public read methods。Controller 在 S1 entry task/validation 中把调用图审计作为直接检查点，不为重复文字再改 plan。

### RR-C-03 — standalone 6-K independent core construction

**来源**：DS `R06-REREVIEW-R02`，MEDIUM，要求 plan 再加一句。

**裁决**：rejected-as-new-finding；直接证据成立，但 fixed plan 已经精确写明所要求的非对称迁移。

Plan §2 root-cause 表明确记录“6-K repair 还分别建 core”；§3.5 明确四个 composition owner“分别……创建一个 `_FsRepositorySet`，并从同一 set 装配新的 `FsBatchingRepository` 以及 source/blob/processed/company/maintenance wrappers”；§7.3 再次要求 `sec_6k_primary_document_repair.py` 首次实例化 batching wrapper并与全部 wrappers共享同一个 set/core。DS 建议的“先引入 `build_fs_repository_set` 再把同一 set 传给 wrappers”已经是这两节的唯一可行含义，不存在 uniform additive wiring ambiguity。再加同义句只会重复，不提高 code-generation readiness。

S3 implementation/validation 仍必须以直接测试证明 batching 与三个业务 wrappers 共用一个 core；不得用私有 `id(core)` 作为业务 contract 断言，优先以 cross-core token rejection 与同-token mutation visibility 的 public behavior 证明。

### RR-C-04 — 两个 `LocalFileSource` 实现

**来源**：DS `R06-REREVIEW-R03`，LOW。

**裁决**：rejected-as-current-finding，保留为 code-review observation。

直接证据只证明两个分层独立实现都满足 `Source` Protocol，没有证明任何 production path 用 documents-layer `LocalFileSource` 重新包装 Fins storage source。向 documents implementation 添加“不要包装”注释既不是类型/owner约束，也会扩出 S1 allowlist，属于下游预防性补丁。R06 正确 owner 是 Fins `get_source()` / `get_primary_source()` 返回携带 storage opener 的 Fins source；S1 code review 与真实 smoke 只需证明这些真实 storage-backed paths 未替换成 documents implementation。若调用图出现实际重包装，再回 owner boundary 修复，不提前增加警告 shim。

## 3. Final ledger

| 类别 | 数量 | 状态 |
| --- | ---: | --- |
| Controller accepted fixes `R06-PF-01..08` | 8 | closed |
| MiMo new evidence observations | 3 | no-action / plan already covers |
| DS new findings/observations | 3 | no-action 1、rejected-as-new-finding 1、rejected-as-current-finding 1 |
| current accepted plan findings | 0 | none |
| unresolved product questions | 0 | none |
| blockers | 0 | none |

由于 current accepted finding 为零，不需要第二次 plan-fix 或第三轮 re-review。两路已对 fixed complete plan 完成 re-review，重复零改动 gate不会增加证据。

## 4. Safety、deferred scope 与 next gate

Accepted plan 保留 containment、symlink prevention、atomic write、writer fencing、journal recovery 与 crash evidence，并新增与 writer lock 分离的短时跨进程 publication guard；它没有实现统一 tool authorization，也未删除任何既有权限/防御机制。

R07-R11、Issue 142/151/175/177/178、旧 schema compatibility、process isolation、callback transport 与统一 authorization 仍明确 deferred。R06 plan commit 不授权其实现。

下一步是把 fixed plan、entry/fix/review/re-review/controller artifacts 与当前 control state 作为一个 exact-scope accepted plan commit。记录真实 commit SHA 后，R06 进入 S1 implementation gate；S1 仍须按累计 reviewability 流程完成 implementation、Controller验证、双路 review、所有 accepted findings fix/re-review，不能跳到 S2。
