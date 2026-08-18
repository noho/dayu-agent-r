# upload-filing-ticker-alias-contract second plan re-review controller adjudication

## Gate metadata

| 字段 | 值 |
| --- | --- |
| Gate | `plan re-review (round 2) adjudication` |
| Work unit | `upload-filing-ticker-alias-contract` |
| Adjudicator | `AgentController` |
| Timestamp | `2026-08-14 23:13:03 +0800` |
| Reviewed plan | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-codex.md` |
| Fix artifact | `docs/reviews/wu-upload-filing-ticker-alias-contract-plan-fix-2-codex.md` |
| Reviewer artifacts | `docs/reviews/plan-rereview-20260814-230257-mimo.md`; `docs/reviews/plan-rereview-20260814-230257-ds.md` |
| Decision | `pass-with-risks` |
| Next gate | `accepted plan local commit -> S1 implementation` |

## Controller conclusion

接受修订计划。AgentMiMo 给出 `pass`；AgentDS 给出 `pass-with-risks` 且没有 blocker。两路都以直接代码/状态机证据确认 P1–P5 已关闭，A1–A8 与 R1/R2 未回退，旧 P4“拒绝 material aliases / 删除 producer”的错误方案已完整撤回。

计划现在冻结了以下端到端 owner contract：ticker grammar、canonicalization 与 stable dedupe 由 `CompanyTickerIdentity` builder 唯一拥有；CompanyMeta 持久化 accepted aliases；storage descriptor 持久化 canonical corpus identity；filing 与 SEC/CN material producer共用同一 upload decision / commit intent；storage在 identity guard内由 descriptor canonical与valid CompanyMeta aliases构造唯一index并完成原子冲突校验；read route只消费该index。

## Accepted findings

### F1 — accepted as binding implementation constraint：descriptor corruption 与 I/O 必须显式分型

AgentDS 的低严重度 finding成立，但不要求再次 plan fix。S2 implementation 必须遵守以下 binding constraint：

1. authoritative descriptor scan不得仅依赖 `Path.exists()` / `Path.is_file()` 的布尔结果来区分“descriptor缺失/结构非法”和“文件系统不可访问”。Python 3.11 的 path predicate可能把stat失败折叠为`False`。
2. scan使用专用、typed private helper，通过显式 `os.lstat` / `os.stat` 或等价的异常保真机制区分：
   - `ENOENT` 且published ticker directory仍存在：`CompanyTickerIdentityCorruptionError(kind="invalid_descriptor")`；
   - symlink、non-regular、schema/namespace/locator/external canonical双向校验失败：同一`invalid_descriptor`；
   - `EACCES`、`EPERM`及其它普通I/O：保留为storage operational failure，read投影`storage_unavailable`，upload投影`storage/storage_io`，不得误报durable corruption。
3. 不允许通过匹配异常字符串或下游fallback分型；该private helper是scan的唯一descriptor classification owner，并可复用既有descriptor payload/bidirectional validation，但必须保留原始I/O类别。
4. tests必须分别注入 descriptor file不可读与ticker directory不可访问两类permission failure，并与真正descriptor缺失、symlink/non-regular形成对照；断言read/upload投影与首次backup/swap前时点。

该约束只精化 P5 的实现机制与测试，不改变 `invalid_descriptor` closed kind、锁图、merge、slice或scope。

## P1–P5 adjudication

- P1 `accepted`：meta-less published corpus是descriptor-owned canonical-only identity；read、首次发布、后续补meta与双向canonical/alias冲突共享同一index。`publishes_new_corpus`在same-ticker writer后冻结，未发现race或锁环。
- P2 `accepted`：`test_prompt_command.py`与`test_entrypoint_runtime.py`已纳入constructor迁移及multiline residue scan。
- P3 `accepted`：6-K discovery branch改为新增`target_tickers=None` public-path精确测试，不再声称既有测试直接覆盖。
- P4 `accepted`：SEC/CN normal material producer确实持久化CompanyMeta；material与filing必须共用identity/decision/intent并可靠保存aliases。旧“filing-only alias”方案为`rejected-with-reason`，不得实施或作为兼容分支保留。
- P5 `accepted with implementation constraint`：`invalid_descriptor` closed kind完整；按上节显式stat/lstat规则防止permission/I/O误分类。

## Preserved decisions and residual risks

- A1–A8保持closed；R1/R2 rejected reasons保持有效。
- 旧workspace schema/migration、UF-PF05、oracle/scenario/frozen evidence、其它finding、scan性能与recovery guard contention继续按plan分类为later work或用户明确排除。
- 不创建PR、不push。Gateflow继续在当前分支创建accepted plan、S1、S2、deepreview与closeout本地commit。

## Gate transition

本plan gate通过。先提交本work unit的goal/plan/review/fix/adjudication artifacts，提交标题为：

```text
gateflow: accept plan for upload-filing-ticker-alias-contract
```

随后自动进入 S1 implementation。S1仍只是不可部署checkpoint，通过review后必须继续S2。
