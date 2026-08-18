# UF-FIX07 aggregate deepreview accepted findings plan amendment

## Gate 元数据

- Work unit：`UF-FIX07 multi-file-primary-and-collision`
- Gate：`aggregate deepreview -> fix` 前的最小 plan amendment
- 日期：2026-08-15
- 基线 HEAD：`1e04273f0688806bcc0746a0f2178a01d4bc092b`
- 原 plan：`docs/gateflow/uf-fix07-multi-file-primary-collision-plan-20260815.md`（只读，不修改）
- Review inputs（只读）：
  - `docs/reviews/code-review-20260815-213300.md`：`PASS`
  - `docs/reviews/code-review-20260815-214245.md`：`1 MEDIUM + 1 LOW`
  - `docs/reviews/plan-review-20260815-215532.md`：`PASS with 2 actionable findings`
  - `docs/reviews/plan-review-20260815-220208.md`：`pass-with-risks`，`2 LOW + 2 open questions`
- Finding 裁决：Finding 1、Finding 2 均 `accepted`
- Plan-review 裁决：四项 findings 与两个 open questions 全部 `accepted`、`已纳入计划`
- Decision：`PLAN AMENDMENT FIXED / PLAN RE-REVIEW PENDING`
- Blocking open question：无
- 下一入口：`plan re-review`
- Artifact path：`docs/gateflow/uf-fix07-aggregate-review-plan-amendment-20260815.md`
- Fix artifact：`docs/gateflow/uf-fix07-aggregate-review-plan-amendment-fix-20260815.md`

本 amendment 只修订 aggregate deepreview accepted findings 的实施授权。当前 gate 不修改生产代码、测试、README、原 plan、
registry、oracle、scenario 或 frozen evidence，不运行 UF-PF07/UF-PF12，不提交、不 push、不创建 PR。

## 1. Supersession 边界

本 amendment 不改写原 plan，而是精确 supersede 以下条款；原 plan 其余 owner、identity、atomicity、material、storage、process、
validation 与禁止边界继续有效：

1. 原 plan §6.6 中 `_build_upload_source_fingerprint()` 的 filing fingerprint 公式、排序、skip/update/version 结论；
2. 原 plan Slice 3 `Exact allowed changes` 第 5 项；
3. 原 plan Slice 3 `Tests / assertions` 中 filing move/rename/content fingerprint 测试条款；
4. 原 plan Slice 4 `Exact allowed changes` 第 2 项中 filing fingerprint 与 originals 读取顺序的 README 条款；
5. 原 plan §9 的 allowed files 仅就本次 aggregate fix 收窄为 §7 列出的四个路径；不得借原 plan 的较大 allowlist 修改其它文件；
6. 原 plan §12 中“同 basename/同内容换目录 identical-skip”仅按本 amendment 的单文件及可安全比较情形解释；不可区分的
   multi-file duplicate descriptor 等价类改用 §4.4 的保守 contract。

本 amendment 不改变 filing path-derived storage asset identity、`original_filename`、`derived_from`、publication batch、
`primary_document` 或 downstream `get_primary_source()` 的 owner，也不改变 material fingerprint 公式。

### 1.1 Goal confirmation binding

本 amendment **不 supersede、不修改、也不重开**
`docs/gateflow/uf-fix07-multi-file-primary-collision-goal-confirmation-20260815.md`。Goal confirmation 仍是 binding scope
contract；本 amendment 只修正原 accepted implementation plan 在 aggregate deepreview 后暴露的遗漏。

Finding 1 直接保持并落实已确认目标 #3：CLI、LLM-facing tool、Service、fresh validation、manifest/storage publication 与
downstream process 必须使用同一个 authoritative primary fact，且不得从顺序、basename、stem、目录或生成结果反推。当前错误 skip
会在 Service fingerprint owner 丢弃该 authoritative fact；role-aware fingerprint 与 conservative no-skip 只是修复这条既定链路，
没有新增目标、验收标准或 owner。Finding 2 只让 README 与同一已实现 role-order contract 对齐。

## 2. 第一性原理判断与直接证据

### 2.1 Finding 1 成立且属于当前 owner boundary

authoritative primary 是已验证业务事实；若同一文件集合只切换 primary，最终发布的 `primary_document` 与 downstream 内容必须随之
改变。当前 `DoclingUploadService.prepare_upload()` 在构造 `original_assets` 后立即计算 fingerprint，并在
`_build_pending_assets()` 消费 authoritative primary 之前执行 `_can_skip_upload()`。当前 filing fingerprint 只序列化
`original_filename`、`sha256`、`size`、`source`，所以角色翻转不会改变 digest，auto 路径会错误返回 `skipped`，旧
`primary_document` 与 downstream 内容被保留。

因此根因位于 `DoclingUploadService` 已有 fingerprint/skip owner，而不是 CLI、validated selection、storage snapshot、processor
或 README。修复必须在该 owner boundary 编码角色并收紧 skip policy；不得让下游从旧 `primary_document`、文件名或目录反推请求角色。

### 2.2 Finding 2 成立但不要求改变生产顺序

`FinsUploadFilingFiles.ordered_files` 的 contract 是 authoritative primary 在前、companions 保持原相对顺序；
`DoclingUploadService` 按这一 role order 读取 originals。`dayu/fins/README.md` 当前写成“按输入顺序读取”，属于文档漂移。
正确修复是 README 改为 role order，不把生产实现改回 input order，也不增加双顺序 contract。

### 2.3 不可区分反例证明

设两个不同规范路径 `P1`、`P2` 都投影出完全相同的业务 descriptor：

```text
(original_filename, sha256, size, source) = ("report.pdf", H, N, "original")
```

若 fingerprint 仍把 descriptors 作为无路径、无顺序的排序多集，仅给每项增加 `is_primary: bool`，则：

```text
P1 primary / P2 companion -> {(D, true), (D, false)}
P2 primary / P1 companion -> {(D, true), (D, false)}
```

两次 payload 相同。仅加 role bool 不能识别翻转；任何相反声明都缺乏数据依据。要精确区分只能引入 path/order/identity 或新的
caller-supplied stable business identifier，但这些都超出已确认 contract，且 path/order 会破坏既有 privacy/move 语义。

本 amendment 选择最小保守 contract：可区分 descriptor 时精确 role-aware；primary 所在 descriptor 等价类不可区分时，明确
禁止 identical-skip，并在已有 source 上强制 update/version increment。它可能产生保守的额外 update，但不会静默丢弃 primary
变更，也不会持久化路径明文或伪造可区分性。

### 2.4 Finding adjudication

| Finding | 裁决 | 当前状态 | Plan 落点 |
| --- | --- | --- | --- |
| Finding 1：fingerprint 未编码 authoritative primary | `accepted` | `未修复`；等待 aggregate fix | §4–§5 supersede 原 plan §6.6/Slice 3 fingerprint contract |
| Finding 2：README 错写 input order | `accepted` | `未修复`；等待 aggregate fix | §6 修正为 primary-first role order |

### 2.5 Plan-review findings 与 open questions 裁决

| Review item | 裁决 | 状态 | 纳入位置 |
| --- | --- | --- | --- |
| `215532-F1`：version resolver 未在签名处绑定 unsafe 行为 | `accepted` | `已纳入计划` | §4.2 增加 exact branch contract 与 owner 职责；§4.5 绑定 typed result data flow |
| `215532-F2`：ambiguous version 断言不精确 | `accepted` | `已纳入计划` | §5.2 冻结 `v1 -> v2 -> v3` |
| `220208-F1`：缺少 multi-file 整组跨目录 move test | `accepted` | `已纳入计划` | §5.3 增加 safe multi-file whole-set move identical-skip |
| `220208-F2`：缺少 old v1 multi-file transition fixture | `accepted` | `已纳入计划` | §5.4 增加独立旧公式 fixture 与 v2 fail-safe update |
| `220208-OQ1`：goal confirmation 关系未显式书写 | `accepted` | `已纳入计划` | §1.1 明确不 supersede goal confirmation，并映射目标 #3 |
| `220208-OQ2`：validation 未恢复 aggregate affected scope | `accepted` | `已纳入计划` | §8 恢复原 Slice 4 的 13 tests、full pyright 与六文件 coverage gates |

六项 reviewer 输入均已闭合为 code-generation-ready plan 条款，不再是 blocking open question。

## 3. Goal、成功信号与非目标

### 3.1 Goal / success signals

1. 同一可区分文件集合只翻转 authoritative primary 时，auto upsert 必须进入 update，document version 增长，重新转换新 primary，
   发布的 `primary_document`、`derived_from` 与 downstream exact primary 内容全部切换；不得返回 identical-skip。
2. primary 不变且 multi-file descriptors 可安全比较时，input reorder 不改变 fingerprint，仍可 identical-skip。
3. 两个路径产生相同 `original_filename + sha256 + size + source` 时，不声称能区分它们；只要 authoritative primary 落在含 companion
   的同 descriptor 等价类中，auto upsert 一律保守 update，并在已有 source 上 version increment。
4. 普通单文件同 basename/内容跨目录重传继续 identical-skip；basename 改名或内容改变继续 update/version increment。
5. path-derived storage asset identity、绝对路径与 input order 不进入持久化 fingerprint payload；不读取旧 `primary_document` 来
   决定本次角色或 skip。
6. material fingerprint digest、skip/update/version 行为完全不变。
7. Fins README 如实说明 originals 按 role order 读取，并描述 role-aware 与不可区分时的保守 skip contract。

### 3.2 Non-goals

- 不修改 CLI/tool/raw request/validated selection；不增加 selector、business file id 或新 public/schema 字段。
- 不修改 storage、processor、read runtime、publication transaction 或 existing primary consumption。
- 不把 path-derived asset identity、path digest、绝对路径、request index、input order、mtime、inode 或随机值写入 fingerprint。
- 不做旧 fingerprint 的 dual-read、兼容 hash、migration shim 或 fallback；不扩大 UF-FIX08。
- 不改变不可区分 duplicate descriptors 的 admission；本修复只定义 conservative skip/update 行为。
- 不修改 material asset/fingerprint/event/failure contract。
- 不修改 registry/oracle/scenario/frozen evidence，不运行 UF-PF07/PF12，不提交、不建 PR。

## 4. 精确 contract 与 data flow

### 4.1 新增私有 typed result

在 `dayu/fins/pipelines/docling_upload_service.py` 增加：

```python
@dataclass(frozen=True, slots=True)
class _UploadSourceFingerprint:
    """上传指纹及 identical-skip 安全性。"""

    value: str
    identical_skip_safe: bool
```

`value` 是写入现有 meta `source_fingerprint` 的 digest；`identical_skip_safe` 只在当前 preparation 内控制 skip/version，不新增持久化
字段。该 bool 的 owner 是 fingerprint builder，不由 caller、storage 或 README 重算。

`_UploadSelectionPreparation` 增加显式字段：

```python
filing_primary: Path | None
```

- filing upsert 直接取 `FinsUploadFilingFiles.require_primary()`；filing delete 与 material 为 `None`；
- 该字段只把 authoritative selection 事实送到 fingerprint owner，禁止从 `ordered_files[0]`、`converter_inputs[0]` 或下游
  `primary_document` 反推；
- 不持久化该 Path，不进入事件、日志业务字段或 fingerprint payload。

### 4.2 精确函数签名

冻结以下私有签名；实现阶段若需要 public/storage/schema 变更，触发 stop condition：

```python
def _build_upload_source_fingerprint(
    assets: list[_PendingFileAsset],
    *,
    source_kind: SourceKind,
    filing_primary: Path | None,
) -> _UploadSourceFingerprint:
    ...

def _can_skip_upload(
    previous_meta: Mapping[str, JsonValue] | None,
    source_fingerprint: _UploadSourceFingerprint,
    overwrite: bool,
) -> bool:
    ...

def _resolve_document_version(
    previous_meta: Mapping[str, JsonValue] | None,
    source_fingerprint: _UploadSourceFingerprint,
) -> str:
    ...
```

`_build_upload_source_fingerprint()` 必须完整中文 docstring，明确 filing primary 缺失、primary identity 未 exact 命中 originals、
material 非法携带 filing primary、source kind 不支持时的 `ValueError`；不能用 `getattr/hasattr` 或 loose dict fallback。filing 必须
携带非空 originals 与非空 primary；material 必须传 `filing_primary=None`。

三个 helper 的职责必须按以下分支精确实现，不能只机械替换参数类型：

```python
# _can_skip_upload 只拥有“本次能否提前返回 skipped”的决策；不计算版本。
if overwrite or previous_meta is None:
    return False
if require_source_meta_is_deleted(previous_meta):
    return False
if not source_fingerprint.identical_skip_safe:
    return False
previous_value = _text_meta(previous_meta, "source_fingerprint")
return bool(previous_value) and previous_value == source_fingerprint.value

# _resolve_document_version 只拥有“既然未 skip、继续发布时使用哪个版本”的决策；
# 不读取 overwrite、is_deleted、primary_document，也不再次决定 skip。
if previous_meta is None:
    return "v1"
previous_version = _text_meta(previous_meta, "document_version") or "v1"
if not source_fingerprint.identical_skip_safe:
    return _increment_document_version(previous_version)
previous_value = _text_meta(previous_meta, "source_fingerprint")
if previous_value and previous_value != source_fingerprint.value:
    return _increment_document_version(previous_version)
return previous_version
```

关键不变量：只要 `previous_meta is not None`，`identical_skip_safe=False` 就必须**无条件**从 existing source 的
`previous_version` 增长一次，不得再受 digest 相等、previous fingerprint 是否缺失、overwrite 或 deleted 状态影响。
`previous_meta is None` 始终为 `v1`。安全 fingerprint 继续保持既有规则：只有非空 previous digest 与当前 `.value` 不同才增长。

`prepare_upload()` 必须把同一个 `_UploadSourceFingerprint` 实例先传给 `_can_skip_upload()`，未 skip 后再传给
`_resolve_document_version()`；写入 `_build_upsert_meta()`、`_PreparedAssetMutation.source_fingerprint` 以及最终 meta 的只能是
`source_fingerprint.value`。不得把 typed result 整体持久化，也不得在两个 helper 分别重建安全性。

### 4.3 Filing fingerprint payload 与 versioning

先把每个 filing original 投影为唯一业务 descriptor：

```json
{
  "original_filename": "report.pdf",
  "sha256": "...",
  "size": 123,
  "source": "original"
}
```

primary asset 的定位流程固定为：authoritative `filing_primary` -> 现有
`_build_filing_original_asset_identity(filing_primary)` -> 在 `assets[].name` 中 exact 命中一次。path-derived identity 只在内存中完成
role-to-asset 关联，不序列化进 payload；0 次或多次命中均以 `ValueError` fail closed。

Fingerprint payload 分两种自然 cardinality contract：

1. **单文件 filing**：primary 是 admission 已确定的唯一角色，不存在可翻转角色。继续使用原 plan 已实现的单元素 descriptor list
   payload 与相同 JSON 参数，保持现有 digest 公式；`identical_skip_safe=True`。因此普通单文件同 basename/内容跨目录仍直接命中
   identical-skip，不产生公式升级带来的无意义 update。
2. **多文件 filing**：使用带显式版本的 role envelope；primary descriptor 独立放置，companions 按
   `(original_filename, sha256, size, source)` 稳定排序：

```json
{
  "fingerprint_version": "filing-primary-role-v2",
  "primary": {
    "original_filename": "main.pdf",
    "sha256": "...",
    "size": 123,
    "source": "original"
  },
  "companions": [
    {
      "original_filename": "appendix.xlsx",
      "sha256": "...",
      "size": 456,
      "source": "original"
    }
  ]
}
```

统一继续使用 `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))` 和 SHA-256。版本字面量必须是模块级私有
`Final[str]`，不得散落。multi-file v2 与当前无角色旧 payload 有意不兼容：已有旧 multi-file fingerprint 的首次 upsert 会 update/
version increment；不做 dual hash skip，因为旧 digest 没有 authoritative role 证据。single-file 公式不升级。

material 分支必须继续构造当前按 `name` 排序的 list payload，digest 必须与当前固定向量逐字节一致，并返回
`identical_skip_safe=True`；不得加入 version、role 或 filing 参数。

### 4.4 不可区分 duplicate descriptor 的 conservative contract

构造 multi-file v2 payload 后，若 primary descriptor 与任一 companion descriptor 全字段相等，则：

- digest 仍按 §4.3 的诚实 payload 计算；不得加入 path hash、identity、input index 或 nonce 假装区分；
- `_UploadSourceFingerprint.identical_skip_safe=False`；否则为 `True`；
- `_can_skip_upload()` 必须先检查 overwrite/previous/deleted 的既有条件，再要求 `identical_skip_safe=True` 且 digest 相等才允许 skip；
- `_resolve_document_version()`：无 previous meta 时仍返回 `v1`；有 previous meta 且
  `identical_skip_safe=False` 时，严格按 §4.2 分支无条件在现有 previous version 上增长一次；安全情形继续只在 digest 改变时增长；
- 因此同一 ambiguous request 原样重传也会 update/version increment。这是已接受的保守 false-negative skip，不是可被下游补偿的
  bug；它以额外转换/写入换取“不静默丢失可能的 role flip”。

companions 之间存在相同 descriptor、但 primary descriptor 在其等价类中唯一时，`identical_skip_safe=True`；因为这些 companion
互换不改变 authoritative primary 事实。未来若 primary 切换进该重复等价类，v2 payload 会先因 primary descriptor 改变而 update，
并从该次起进入 conservative unsafe contract。反之，只要后续文件/内容变化使 primary descriptor 在集合中重新唯一，新的 typed
fingerprint 即恢复 `identical_skip_safe=True`；该次因 digest 改变而 update 后，再次重放同一 non-ambiguous selection 可以正常
identical-skip。conservative churn 只绑定当前 ambiguous descriptor state，不是 source 的永久标记。

### 4.5 prepare/skip/version/publication data flow

```text
validated FinsUploadFilingFiles.require_primary()
  -> _UploadSelectionPreparation.filing_primary
  -> read originals / build path-private storage identities
  -> _build_upload_source_fingerprint(original assets, source_kind, filing_primary)
       -> in-memory exact role-to-asset association
       -> single-file existing payload OR multi-file v2 role payload
       -> value + identical_skip_safe
  -> _can_skip_upload(previous meta, typed fingerprint, overwrite)
       -> safe + same digest only: skipped
       -> role change / ambiguous unsafe / digest change: continue
  -> convert authoritative primary
  -> _resolve_document_version(previous meta, typed fingerprint)
       -> no previous meta: v1
       -> existing + unsafe: unconditional previous version + 1
       -> existing + safe + changed digest: previous version + 1
       -> existing + safe + same/missing digest: preserve previous version
  -> persist only fingerprint.value through existing source_fingerprint field
  -> existing atomic publication writes derived_from + primary_document
  -> existing snapshot.get_primary_source() feeds downstream
```

不得在 skip owner 读取或解析旧 `primary_document`，不得比较 input position，不得从 derived filename 反向得到 role。发布路径只消费
本次 authoritative selection 已产生的 exact facts，保持原 plan 的 owner chain。

## 5. Tests 与精确 assertions

只修改 `tests/fins/test_docling_upload_service.py`，在 owner 级覆盖以下矩阵：

### 5.1 可区分 primary flip

- 创建 multi-file filing：A/B 的 descriptor 可区分，primary=A；精确断言 `status="uploaded"`、`document_version="v1"`、
  converter 只收到 A。
- 同一文件集合与内容不变，仅 primary=B 的 auto update：精确断言不是 skipped、fingerprint 不同、
  `document_version: "v1" -> "v2"`、converter 新增且只收到 B。
- 从真实 repository snapshot 断言 `primary_document` 等于 B 的 derived identity，`derived_from` 回指 B original identity，
  `get_primary_source()` 读取 B derived bytes；旧 A derived 不再作为 downstream primary。
- 再以 primary=B、同一 descriptors 重传：精确断言 `status="skipped"`、`document_version` 仍为 `v2`、converter call count
  不增长，证明 role-aware 不是“所有 multi-file 永远 update”。
- 以相同 primary/companions 但改变 raw companion 相对顺序构造 selection：fingerprint 相同并可 skip，证明不依赖 input order。

### 5.2 不可区分 duplicate descriptors

- 两个不同规范路径具有相同 basename、相同 bytes/size/source；分别指定 P1/P2 为 primary。
- 直接 helper 断言两次 v2 digest 相同且 `identical_skip_safe=False`，明确冻结“无法区分”而不是写错误的 digest-different 断言。
- create(primary=P1) 精确断言 `status="uploaded"`、`document_version="v1"`；原样 auto replay(primary=P1) 精确断言
  `status="uploaded"`、`document_version="v2"`；再仅翻转为 P2 精确断言 `status="uploaded"`、
  `document_version="v3"`。该 `v1 -> v2 -> v3` 链必须直接读取 repository meta/typed prepared mutation 的 canonical version，
  不能只断言定性的“version increment”。
- 翻转后断言 converter 使用 P2，repository `primary_document`/`derived_from` 精确指向 P2 path-private identity，downstream bytes 来自
  本次 P2 derived；虽然原始 bytes 相同，identity 断言必须证明角色指针已更新。
- source meta 与 fingerprint payload/digest 相关测试不得出现绝对路径明文；不能通过持久化 path digest 使测试通过。
- 补 companions-only duplicate 反例：primary descriptor 唯一而两个 companions 相同，断言 `identical_skip_safe=True`，避免把
  conservative policy 无边界扩大为“任意 duplicate 都禁止 skip”。
- 在 `v3` 后改变其中一个 descriptor，使 authoritative primary 在集合中重新唯一：该次因 digest 改变 uploaded 到 `v4`，随后原样
  replay 必须 `skipped` 且保持 `v4`，证明 unsafe/churn 只属于当前 ambiguous state，不会永久污染 source。

### 5.3 Move/rename/content/material regressions

- 保留并强化现有单文件测试：同 basename/同内容跨目录，storage identity 改变但 fingerprint 相同且 auto skipped/version 不增长；
  basename 改名且内容相同 update/version increment；内容改变继续 update/version increment。
- 新增 multi-file safe whole-set move owner test：以两个 descriptor 可区分的 originals 在目录 A create，保持 authoritative primary、
  basenames、bytes/size/source 与角色不变，将整组对应文件放到目录 B 后执行 auto update；断言两个 path-derived storage identities
  均改变，但新旧 typed fingerprint `.value` 相同且 `identical_skip_safe=True`，结果 `status="skipped"`、version 仍 `v1`、converter
  call count 不增长。用新目录 authoritative primary 调用 builder 必须 exact 命中新 original identity，证明 role association 不依赖旧
  path；因本次 skip，repository 继续保留旧已发布 tree，不错误声称发布了新 identity。
- 固定单文件 payload/digest 与 amendment 前公式相同，防止 versioning 无意改变 ordinary single-file skip。
- 现有 material 固定向量 `099dc963...1d7fdd` 必须保持不变，并断言 `identical_skip_safe=True`；代表性 material identical-skip、
  rename/content update/version 行为保持。

### 5.4 Old v1 multi-file -> v2 transition

- 在测试文件内用独立 fixture 按 amendment 前公式直接构造旧无角色 multi-file payload：descriptors 按
  `(original_filename, sha256, size, source)` 排序，使用固定 JSON 参数与 SHA-256 计算 old digest。fixture 禁止调用新的 production
  fingerprint builder，也禁止在 production 增加 legacy helper、dual-read 或兼容 branch。
- 用该 old digest 精确 seed `previous_meta={"document_version": "v1", "source_fingerprint": old_digest, ...}`，再以相同文件与
  explicit primary 构造当前 v2 typed fingerprint；断言 v2 `.value != old_digest`、`identical_skip_safe=True`、
  `_can_skip_upload(...) is False`，且 `prepare_upload` 返回 update mutation 而非 skipped result，canonical
  `document_version="v2"`。
- 再用 v2 digest 作为 previous fingerprint 重放相同 selection，断言 identical-skip 且 version 保持 `v2`；禁止任何“先尝试 v2、
  再回退 old v1 digest”的 dual-read 行为。
- 同一 fixture 同时固定单文件 amendment 前 digest 与当前单文件 `.value` 相等，普通单文件仍可 identical-skip，防止把 multi-file
  version transition 错误扩展到 single-file。

## 6. README amendment

只修改 `dayu/fins/README.md` 当前 upload contract 段落：

1. 将“全部 originals 按输入顺序读取”改为“按角色顺序读取：authoritative primary 在前，companions 保持原请求相对顺序”；
2. 将 filing fingerprint 描述改为：单文件继续由 filename/content descriptor 决定；多文件显式编码 authoritative primary 与排序后的
   companions；path-derived identity、绝对路径和输入顺序不进入 fingerprint；
3. 明确可区分集合只翻转 primary 会 update/version increment并切换 downstream primary；
4. 明确 primary 与 companion descriptor 完全相同时无法在无 path/order 标识下区分，auto 采用 conservative update 而不是
   identical-skip；不要声称仅 role bool 可解决；
5. 保留 ordinary single-file move identical-skip、rename/content update 与 material fingerprint 不变的说明。

README 只描述当前业务 contract，不暴露实际 path digest、内部 dataclass/type 名或旧迁移兼容方案。

## 7. Aggregate fix slice 与 allowed changes

本 amendment 只授权一个可验证 aggregate fix slice，不机械拆分代码、测试和 docs：

**Objective**：在现有 fingerprint owner 中闭环 role-aware skip/update，并同步 owner test 与 Fins README；修复两个 accepted findings。

**唯一 allowed paths**：

- production：`dayu/fins/pipelines/docling_upload_service.py`
- tests：`tests/fins/test_docling_upload_service.py`
- docs：`dayu/fins/README.md`
- artifact：`docs/gateflow/uf-fix07-aggregate-review-fix-20260815.md`

**Exact allowed changes**：

1. 增加 §4.1 typed fingerprint result 与显式 `filing_primary` preparation fact；只调整其必要构造/消费点。
2. 按 §4.2–§4.4 改写既有 fingerprint、skip 与 version 私有 owner；持久化仍只写现有 digest string。
3. 按 §5 修改 owner tests；不得通过 mock/fixture 固化 input-order 或 downstream inference。
4. 按 §6 修正 Fins README。
5. 创建 aggregate fix artifact，记录两个 finding 的 `已修复/部分修复/未修复/证据失效` 闭集状态、实际 diff、验证、docs decision、
   residuals 与下一 gate；不得修改两份 review inputs 或原 plan。

不得修改其它原 plan allowed production/test/README，也不得新增 helper 模块、public type、storage field、compatibility branch 或 migration。

## 8. 实现后验证命令（本 plan amendment gate 不执行）

实现完成后必须恢复原 accepted plan Slice 4 的完整 13-file affected gate；focused owner test 不能替代 aggregate regression：

```bash
source .venv/bin/activate
python -m pytest tests/fins/test_upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_processor_read_consistency.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
git status --short
git rev-parse HEAD
```

同一次 implementation validation 必须以相同 13-file suite 收集 branch coverage，并对原 UF-FIX07 六个修改生产文件逐文件执行
`>=80%` gate；不得用 aggregate percentage 掩盖单文件缺口：

```bash
source .venv/bin/activate
python -m coverage erase
python -m coverage run --branch -m pytest \
  tests/fins/test_upload_format_contract.py \
  tests/fins/test_fins_ingestion_runtime.py \
  tests/fins/test_fins_service_runtime.py \
  tests/cli/test_arg_parsing.py tests/cli/test_fins_commands.py \
  tests/fins/test_fins_ingestion_tools.py \
  tests/fins/test_docling_upload_service.py \
  tests/fins/test_docling_upload_service_integration.py \
  tests/fins/test_sec_pipeline_upload_filing_stream.py \
  tests/fins/test_sec_pipeline_upload_material_stream.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_fins_storage_atomicity.py \
  tests/fins/test_processor_read_consistency.py -q
python -m coverage report --include='dayu/fins/ingestion_runtime.py' --fail-under=80
python -m coverage report --include='dayu/fins/upload_format_contract.py' --fail-under=80
python -m coverage report --include='dayu/cli/arg_parsing.py' --fail-under=80
python -m coverage report --include='dayu/cli/commands/fins.py' --fail-under=80
python -m coverage report --include='dayu/fins/tools/upload_tools.py' --fail-under=80
python -m coverage report \
  --include='dayu/fins/pipelines/docling_upload_service.py' --fail-under=80
```

`dayu/fins/pipelines/docling_upload_service.py` 是本 aggregate fix 唯一修改的生产文件，除六文件 gate 外必须明确记录其 branch
coverage `>=80%`；其余五个报告恢复原 Slice 4 的 aggregate non-regression acceptance，不授权修改它们来追 coverage。

另外必须静态核验：

```bash
git diff --name-only
git diff -- docs/reviews/code-review-20260815-213300.md \
  docs/reviews/code-review-20260815-214245.md \
  docs/reviews/plan-review-20260815-215532.md \
  docs/reviews/plan-review-20260815-220208.md \
  docs/gateflow/uf-fix07-multi-file-primary-collision-plan-20260815.md \
  docs/gateflow/uf-fix07-multi-file-primary-collision-goal-confirmation-20260815.md
```

预期：13-file affected suite 通过；full pyright 为 0 且无新增/扩散错误；六个生产文件各自 branch coverage `>=80%`，其中 aggregate
fix production file 明确 `>=80%`；diff check 通过；implementation tracked diff 只含 §7 四个 allowed paths；全部只读 review、原 plan
与 goal confirmation 无 diff。不得执行 UF-PF07、UF-PF12。

## 9. Stop conditions

出现以下任一情况必须停止并交主控重新裁决，不得局部补偿：

1. 正确实现需要修改 validated selection、storage、processor、read runtime、public schema 或本 amendment allowlist 外文件；
2. 实现必须把绝对路径、path-derived identity/digest、input order/index、inode、mtime 或 nonce 写入 fingerprint 才能区分 duplicate
   descriptors；必须保留 conservative unsafe contract，不能越界追求精确 skip；
3. 实现需要读取旧 `primary_document`、derived filename、storage files 顺序或下游内容反推本次 authoritative primary；
4. material fixed digest 或 skip/update/version 行为发生变化；
5. ordinary single-file跨目录 identical-skip、rename/content update 任一回归；
6. multi-file v2 首次遇到旧无角色 digest 需要产品授权兼容 skip；本 amendment只允许安全 update，不允许 dual-read fallback；
7. 测试、full pyright、coverage、diff check 失败，或出现未分类 residual risk；
8. 需要修改 review artifacts、原 plan、registry/oracle/scenario/frozen evidence，运行 UF-PF07/PF12，提交、push 或创建 PR。

## 10. Residual risks / uncovered areas

| 风险或未覆盖项 | 分类 | Owner / destination |
| --- | --- | --- |
| primary 与 companion descriptor 完全相同的请求无法在不引入 path/order identifier 时区分，ambiguous state 重放会持续 version churn | accepted conservative boundary | 当前 fix：禁止 identical-skip；existing source 每次 ambiguous upsert 都无条件 update/version increment；descriptor 恢复 non-ambiguous 后 typed fingerprint 恢复 safe，该次 update 后再次 replay 可 skip，不是永久状态 |
| 当前 HEAD 已持久化的无角色 multi-file fingerprint 首次按 v2 upsert 会 update/version increment | fixed in current aggregate fix | 当前 fix 有意 fail safe，§5.4 独立旧公式 fixture 固定 transition；不做旧 digest dual-read/兼容 shim；若要求迁移，归 `UF-FIX08` |
| 旧 basename-based source schema 的兼容、首次重传或自动修复 | assigned to later work unit | `UF-FIX08` |
| 同 request/同 document 并发 writer | assigned to later work unit | `UF-FIX10` |
| fresh company meta warning | assigned to later work unit | `UF-FIX11` |
| optional real Docling 与 UF-PF07/UF-PF12 未执行 | assigned to later evidence work | 等待独立授权；本 fix 只跑 deterministic owner tests |
| registry/oracle/frozen evidence 仍记录修复前观察 | assigned to later evidence work | 当前禁止修改或重跑 |

所有 residual risks 已分类；无 blocking open question。该方案不引入新 public abstraction、storage schema 或 migration，只扩展现有
fingerprint owner 的 typed result 与 multi-file payload，属于闭合两个 accepted findings 所需的最小变更，没有 goal drift。

## 11. Completion status

- Changed files：修订本 amendment artifact；新增
  `docs/gateflow/uf-fix07-aggregate-review-plan-amendment-fix-20260815.md`。
- Production/tests/README：未修改。
- 原 plan、goal confirmation 与四份 code/plan review inputs：只读，未修改。
- Validation：本 gate 只做 code/plan/review 静态核对与 artifact whitespace/scope 检查；未运行 implementation tests、pyright、coverage、
  UF-PF07 或 UF-PF12。
- Plan-review items：四项 findings 与两个 open questions 全部 `accepted`、`已纳入计划`；无 blocking open question。
- Decision：`PLAN AMENDMENT FIXED / PLAN RE-REVIEW PENDING`
- Next entry point：`plan re-review`
- 按用户要求在此停止；不实施、不提交、不建 PR。
