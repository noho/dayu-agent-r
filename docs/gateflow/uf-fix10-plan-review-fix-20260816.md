# UF-FIX10 same-request-concurrency plan review fix

## 0. Gate 元数据

- work unit：`UF-FIX10 same-request-concurrency`
- gate：`plan review -> fix`
- 日期：2026-08-16
- 当前分支：`codex/upload-filing-oracle`
- reviewed target：`docs/gateflow/uf-fix10-same-request-concurrency-plan-20260816.md`
- review artifacts：`docs/reviews/plan-review-20260816-221939.md`、`docs/reviews/plan-review-20260816-222742.md`
- Controller decision：接受 MiMo 01-04、DS F1-F7 以及 DS open questions 1-2；MiMo 01/03 与 DS F1 作为同一state-machine closure bundle修复；无rejected finding
- scope：只修复plan/artifact，不修改生产代码、测试、README，不commit
- changed files：`docs/gateflow/uf-fix10-same-request-concurrency-plan-20260816.md`、`docs/gateflow/uf-fix10-plan-review-fix-20260816.md`
- completion status：`FIX COMPLETE / RE-REVIEW REQUIRED / IMPLEMENTATION NOT AUTHORIZED`
- artifact path：`docs/gateflow/uf-fix10-plan-review-fix-20260816.md`
- next entry point：`re-review`

## 1. 第一性原理裁决

两份 review 指出的动机成立：现有 per-ticker writer 和 atomic swap 已能保证物理发布全序，真正缺口是“所有filing skip是否由writer-owned fresh view上的唯一publication owner裁决”。pre-prepare identical skip、`MISSING -> COMPLETE` action变化、batch-time usage/error映射和staging company-meta reader都是该owner boundary的必要契约，不是附加硬化。因此全部accepted findings都在本plan内修复，没有将它们降级为residual或下沉到workflow/test fallback。

## 2. Findings 裁决与fix状态

fix/re-review 状态使用 Gateflow 固定值；本 artifact 中全部accepted finding均为`已修复`，等待re-review复核。

| finding | Controller 裁决 | fix 状态 | plan 修复 | residual classification |
| --- | --- | --- | --- | --- |
| DS F1：preparation early skip绕过final arbitration | `accepted`；与 MiMo 01/03 合并为state-machine bundle | `已修复` | §6.3/§7.1冻结：filing identical不再返回终态skip，必须完成conversion、形成prepared candidate并进入batch arbitration；material不变。所有最终skip只来自publication owner，终态不投影conversion/stored假事件 | `fixed in current slice`（plan-fix）；实现与证据由S1/S2覆盖 |
| DS F2：batch-time failure映射与failed action真源未冻结 | `accepted` | `已修复` | §6.4增加封闭映射表：state-dependent usage -> `SOURCE_PUBLICATION_CONFLICT`；UNSAFE -> `SOURCE_INTEGRITY_UNSAFE`；I/O/corruption -> path-free `STORAGE_IO`；repair revision/blocked保留existing codes；explicit create failed terminal使用initial `create/create` | `fixed in current slice`（plan-fix）；S1 mapping tests + S2 terminal tests |
| DS F3：required field导致S1 allowed files不闭合 | `accepted` | `已修复` | §8.2/§10.1加入四个既有fixture文件，并限定只对所有direct constructor机械补`publication_identity=None`，不改断言/fake语义 | `fixed in current slice`（plan-fix）；S1 closure validation |
| DS F4：staging company meta owner/实现位置未指定 | `accepted` | `已修复` | §6.2冻结 `_fs_company_meta_core.py::_read_company_meta_from_ticker_dir_unguarded()` 为唯一strict reader；published/staging都委托它，batch只传`staging_ticker_dir`，不读published path、不重复parse；相关owner文件加入S1 allowed files | `fixed in current slice`（plan-fix）；S1 real-FS + spy tests |
| DS F5：FileExistsError投影证据错误 | `accepted` | `已修复` | §2.1.4修正为`FileExistsError` 由先命中的`except OSError`经owner投影为`STORAGE_IO/storage_io`，不再声称`UNEXPECTED_RUNTIME` | `fixed in current slice`（plan-fix） |
| DS F6：缺少跨进程winner/loser覆盖 | `accepted` | `已修复` | §10.2新增spawn multiprocessing real-FS exact-auto test；process-safe barrier确保两进程在initial MISSING下完成prepare后才竞争，bounded queue断言exact `{ok, skipped}` / `{1,0}` 与单次publication | `fixed in current slice`（plan-fix）；S2实现证据 |
| DS F7：SKIP路径缺cancellation checkpoint | `accepted` | `已修复` | §6.4/§7.1冻结SKIP terminal前cancel observation；命中后rollback并返cancelled，不报skip；rollback失败为`STORAGE_IO` | `fixed in current slice`（plan-fix）；S1 owner + S2 terminal tests |
| MiMo 01：`MISSING -> COMPLETE`与publish/skip规则矛盾 | `accepted`；合并进 DS F1 state-machine bundle | `已修复` | §7.2-§7.4冻结：`MISSING -> COMPLETE` + exact auto + overwrite false + exact identity + company keep只能`SKIP`；`MISSING -> MISSING`才`PUBLISH`；其它走封闭conflict/failure表 | `fixed in current slice`（plan-fix）；S1/S2覆盖 |
| MiMo 02：batch company meta来源未指定 | `accepted` | `已修复` | 与 DS F4 同一owner fix；§6.2指定helper、strict parse、allowed file与不得读published path的测试证据 | `fixed in current slice`（plan-fix） |
| MiMo 03：resolved-action invariant与exact-auto例外矛盾 | `accepted`；合并进 DS F1 state-machine bundle | `已修复` | §7.2-§7.4明确prepared=`create`/fresh=`update`只在`MISSING -> COMPLETE` exact-auto skip专用分支合法，不触发stable-branch invariant | `fixed in current slice`（plan-fix） |
| MiMo 04：asset source隐式跨模块字面量对齐 | `accepted` | `已修复` | §6.1冻结contract-owned `FilingUploadAssetSource` alias与typed constants；prepared/durable删除各自private filing constants并共用contract | `fixed in current slice`（plan-fix）；S1 identity tests |

没有 `rejected-with-reason`、`deferred-with-owner` 或 `needs-more-evidence` finding；没有部分修复或证据失效finding。

## 3. Accepted open questions

| open question | Controller 裁决 | fix 状态 | 冻结答案 | residual classification |
| --- | --- | --- | --- | --- |
| DS OQ1：`primary_original_asset_name` 命中name还是original filename | `accepted` | `已修复` | 精确命中original descriptor的storage `name`；docling `derived_from`与primary使用同一storage identity，绝不使用用户basename | `fixed in current slice`（plan-fix） |
| DS OQ2：prepared assets/companions排序 | `accepted` | `已修复` | prepared/durable `assets` 和 companions 都按storage `name`字典序排序，exact dataclass equality不依赖偶然输入/文件顺序 | `fixed in current slice`（plan-fix） |

DS OQ3 只在“保留early skip”时成立。Controller 已接受 DS F1 并删除filing early-skip terminal，因此该条件分支已消失；这不是rejected finding，也不留residual。

## 4. Codegen-ready closure

修订后的plan已不需实现者重新设计：

1. §6.1-§6.5固定了publication identity、asset source、staging read helper、prepared candidate、failure code与shared owner。
2. §7.1-§7.5固定了执行顺序、裁决优先级、stable observation、canonical skip、完整state table、cancel checkpoint与terminal action真源。
3. §8-§10关闭了production/test/fixture allowed files，并把S1/S2 exact assertions、跨进程证据、validation commands与stop conditions绑定到owner boundary。
4. README decision、non-goals、UF-PF/oracle exclusions保持不变，没有goal drift。

## 5. Validation

- `git diff --check`：通过，exit 0，无输出。
- 两个未跟踪plan artifact分别执行`git diff --no-index --check /dev/null <artifact>`：均无whitespace-error输出；exit 1只表示与`/dev/null`存在预期diff。
- 结构自检通过：DS finding行=7、MiMo finding行=4、DS accepted open-question行=2，11个finding均命中`accepted / 已修复`；plan包含§6.1-6.5、§7.1-7.5、S1/S2、open-question closure与所有冻结关键字。
- `git status --short` 只有份本work unit文档：修订plan、本fix artifact与两份review artifact；无production/test/README变更。`git diff --cached --name-only`为空，无staged变更。
- 本fix gate不运行pytest、coverage或pyright；本轮没有代码修改，且用户明确禁止修改/实现生产代码与测试。

## 6. Docs decision

- 本fix gate不修改任何README。
- accepted plan中的README实现期触发决策保持不变：S2代码落地后按原计划检查/更新`dayu/fins/README.md`与`tests/README.md`；根README、`dayu/README.md`与Host/Engine/Service/config README不更新。

## 7. Residual risks

| residual risk | 处理 | Gateflow classification / owner |
| --- | --- | --- |
| converter非确定性 | exact asset identity不等时conflict，不覆盖winner | `fixed in current slice`：S1 identity + S2 route tests |
| rollback失败、skip前cancel | primary/secondary、cancelled/skip/storage failure映射已冻结 | `fixed in current slice`：S1 lifecycle + S2 terminal tests |
| SHA-256理论碰撞 | 继续使用现有storage integrity policy并比较完整role/name/size/content-type/requirements | `assigned to later work unit`：storage integrity policy hardening，非当前goal |
| post-`COMMITTED` guard release failure | 保持existing durable commit truth；后续exact auto可收敛为skip | `assigned to later work unit`：batch terminal-contract hardening，非当前goal |
| manual filesystem writer绕过repository lock | 本契约只承诺repository-protocol writer | `assigned to later work unit`：storage operational hardening |
| fresh company warning | 不扩大本work unit | `assigned to later work unit`：`UF-FIX11` |
| material same-request concurrency | material语义保持不变 | `assigned to later work unit`：需要时另立material work unit |
| UF-PF10/12、oracle/scenario/frozen evidence | 本轮禁止执行/修改 | `assigned to later work unit`：evidence/oracle work unit |

没有unclassified residual risk，没有blocking open question。

## 8. Completion

- decision：`fix pass; re-review required`
- finding status：DS F1-F7、MiMo 01-04全部`accepted / 已修复`
- open question status：DS OQ1-2全部`accepted / 已修复`
- implementation authorization：未授权
- commit：未创建，且本gate禁止commit
- next entry point：`re-review`
