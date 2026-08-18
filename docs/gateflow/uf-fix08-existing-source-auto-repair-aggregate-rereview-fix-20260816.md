# UF-FIX08 existing-source-auto-repair：aggregate re-review fix

## Gate 元数据

- work unit：`UF-FIX08 existing-source-auto-repair`
- gate：`aggregate deepreview re-review -> fix`
- 日期：2026-08-16
- 分支：`codex/upload-filing-oracle`
- HEAD：`65d352e6`（workspace fix 未提交）
- authoritative re-review：`docs/reviews/deep-review-20260816-195058.md`
- non-pass input：`docs/reviews/deep-review-20260816-194657.md` 为首版 PASS，未覆盖 R1
  adversarial 场景，只读保留但不作为 gate pass
- finding：`R1`（accepted blocker）
- completion status：`FIX_COMPLETE_AWAITING_AGGREGATE_RE_REVIEW`
- blocking questions：无
- current gate / next entry point：`aggregate deepreview re-review`
- artifact path：
  `docs/gateflow/uf-fix08-existing-source-auto-repair-aggregate-rereview-fix-20260816.md`

## Root cause 与唯一 owner

R1 与上一轮 M2 同根，但发生在 manifest 无法提供可信 document identity 的 sibling
branch：

1. source-kind root 没有 actual source directory。
2. manifest locator 存在，但 `_inspect_source_manifest()` 因非 regular file、非法 JSON、
   ticker/shape/item/document ID 违约或重复 ID 将其归类为 `trusted=False`。
3. `_apply_manifest_facts()` 旧分支只对已有 inventory item 叠加
   `SOURCE_MANIFEST_UNTRUSTED`。inventory 为空时，只剩 shared reason，没有 public
   `SourceIntegrityClassification` 承载该 unsafe 事实。
4. `list_source_integrity()` 因此返回空 tuple，public preflight 误判 clean，真实 SEC
   workflow 越过 designated gate 后才在 company batch commit 被 raw `ValueError` 拒绝。

唯一 owner 是 `dayu.fins.storage._fs_source_integrity._inspect_source_kind_unguarded()`。workflow 不应
读 shared reason、raw manifest 或 blocked reason，public preflight 也不应增加新参数。

## Fix

在 `_apply_manifest_facts()` 产生同次 scan payload 之后、canonical/target/repair-blocked 派生之前，
inspector 增加一个封闭 gate：

- 仅 `requested_document_id is None`（whole-kind mode）；
- 仅 public inventory 为空；
- 仅 shared reasons 含 `SOURCE_MANIFEST_UNTRUSTED`；
- 直接抛 `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`。

该分支复用已有 unassignable-root typed path。untrusted manifest 无可信 document ID，因此不生成
synthetic inspection；exact mode 仍使用 caller 的 requested ID 返回
`UNSAFE(SOURCE_MANIFEST_UNTRUSTED)/revision=None`；nonempty inventory 仍将每个 actual item 投影为
UNSAFE。revision、publication guard、batch capability、commit validator、repair blocked 与 public API 签名均未变。

## Changed files

| 文件 | 变更 |
| --- | --- |
| `dayu/fins/storage/_fs_source_integrity.py` | whole-kind 空 inventory + shared untrusted manifest 事实直接 typed fail-closed |
| `tests/fins/test_fins_storage_atomicity.py` | filing/material owner tests：exact UNSAFE/no revision，whole list 抛 `UNSAFE_PUBLICATION` |
| `tests/fins/test_sec_pipeline_download.py` | 将真实 SEC 空 inventory manifest 测试参数化为 trusted-dangling/untrusted，断言 provider/company/rejection 零副作用 |
| `docs/gateflow/uf-fix08-existing-source-auto-repair-aggregate-deepreview-fix-20260816.md` | 回写 R1 最终状态与最新验证 |
| `docs/gateflow/uf-fix08-existing-source-auto-repair-aggregate-rereview-fix-20260816.md` | 本 durable rereview-fix artifact |

## Finding 裁决

| Finding | 裁决 | 最终状态 | 证据 |
| --- | --- | --- | --- |
| R1 untrusted manifest + empty inventory public fail-open | `accepted` | `已修复` | filing/material exact/whole owner tests 与 SEC trusted/untrusted 真实 workflow tests 全部通过；失败面为 `SourceIntegrityPreflightError(UNSAFE_PUBLICATION)`，不再到 company commit 泄漏 raw `ValueError` |

`deep-review-20260816-195058.md` 其余 finding 状态不变：M1 证据失效；trusted-dangling M2、
private revision docstring 与 canonical-items gating 均已修复；findings 5-8 与 L1-L15 保持已记录裁决/
owner。

## Validation

所有命令均在 `source .venv/bin/activate` 后执行，未使用 xdist。

| 验证 | 结果 |
| --- | --- |
| R1 精确节点（filing/material owner + SEC trusted/untrusted，含 trusted M2 回归） | 6 passed |
| storage + SEC/CN download matrix | 408 passed，3 个第三方 deprecation warnings |
| accepted focused matrix | 1238 passed，3 个第三方 deprecation warnings |
| `tests/fins` 全量 | 1859 passed，1 skipped（环境条件），3 个第三方 deprecation warnings |
| 全仓 pyright `dayu/ tests/ utils/` | 0 errors，0 warnings，0 informations |
| 单进程 branch coverage | focused 1238 passed；`_fs_source_integrity.py` 86%（501 statements、63 missed、208 branches、36 partial branches，阈值 80%） |
| `git diff --check` | 通过；本未跟踪 artifact 的 no-index check 无 whitespace diagnostics（exit 1 仅表示与 `/dev/null` 有内容差异） |
| scope/frozen guards | 通过；tracked diff 仅 3 个授权 production/test 文件；oracle/scenario/Host/Engine design 与 Host/Engine/Service/CLI production 零 diff；4 份 review artifacts 均保持未跟踪只读 |

未运行 UF-PF08/UF-PF12、真实 CLI/provider/converter evidence，未修改 oracle/scenario/
design/evidence/registry。

## README decision

`dayu/fins/README.md` 已明确 source-kind manifest/actual tree 不可信必须 `UNSAFE`，whole-tree
download 在 company/maintenance/rejection 副作用前 fail closed；`tests/README.md` 已包含当前 focused
命令与 whole-tree UNSAFE 零副作用 matrix。R1 是恢复已文档化 contract，不修改 README。

## Residual risks

R1 无 residual。原 aggregate fix artifact 已分类的 residual owners 保持不变：`UF-FIX10`、
`UF-FIX11`、material repair、migration、evidence/registry、future general download failure projection、
upload operational failure projection、validated-request contract hardening、storage operational policy 与后续
coverage hardening。多悬空 ID + nonempty inventory 的排序无直接节点，由当前集合差与稳定排序
实现覆盖，归 storage coverage hardening。

无 unclassified residual risk，无 blocking open question。

## Gate decision

R1 accepted blocker 已在唯一 storage owner 修复并完成全量验证。AgentMiMo 首版 PASS 不作为
gate pass；当前仍停在 `aggregate deepreview re-review`，不 commit、不 push、不创建 PR。
