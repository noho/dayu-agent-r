# UF-FIX11 aggregate deepreview finding 01 / 02 修复

## Gate metadata

- work unit：`UF-FIX11 company-metadata-ignored-change-warning`
- gate：`aggregate deepreview fix / self re-review`
- 日期：2026-08-17
- 分支：`codex/upload-filing-oracle`
- controller 裁决：修复 aggregate deepreview finding 01，并在 DS rereview 后接受、修复 finding 02
- finding inputs：
  - `docs/reviews/code-review-20260817-172506.md`
  - `docs/reviews/uf-fix11-deepreview-projection-ds-20260817.md`
  - `docs/reviews/uf-fix11-deepreview-state-owner-mimo-20260817.md`
  - `docs/reviews/uf-fix11-deepreview-fix-rereview-ds-20260817.md`
- completion status：`COMPLETE / READY FOR CONTROLLER RE-REVIEW`
- stage / commit / push / PR：均未执行

## Finding 与第一性原理判断

Finding 01 成立，严重度保持为低。当前 arbitration 已使闭集外 company decision 不可达，因此没有现存用户错误；但
`execute_prepared_filing_publication` 的 SKIP 执行分支只特判 `keep`，其余 disposition 都会进入 stage/commit。
`stage_upload_company_meta_decision` 又会对非 `stage` 静默返回，因此 arbitration 与 executor 一旦演进漂移，非法
`skip/no-intent` 会越过 mutation boundary：旧实现若 storage 返回 `None`，会在 physical commit 后才抛 `TypeError`；若
storage 返回 typed company outcome，则甚至会把没有合法 intent 的 durable commit 投影为成功 skip。

这个问题不是 storage、warning projection 或 CLI 的责任。canonical skip 是否允许 company mutation，是 filing publication
state machine 的业务兼容事实；其 owner 是 `dayu/fins/pipelines/filing_upload_publication.py`。修复必须在该 owner 内形成唯一
predicate，并在 arbitration 与 executor 消费 mutation capability 前共同使用，不能在 stage helper、commit outcome 或下游
projection 增加 fallback。

## 直接证据与红测

- 修复前 `_canonical_skip_requirements_are_met` 已完整表达 `keep/no-intent | stage/preserve_published intent`，但 executor
  没有复用该事实。
- 修复前 SKIP executor 对 `company_decision.disposition != "keep"` 无条件调用 stage，并在 commit 前转交 capability。
- `stage_upload_company_meta_decision` 对非 `stage` disposition 直接返回，不会替 executor 封闭 compatibility。
- 新 owner-level adversarial test 令 validator seam 返回经 frozen dataclass owner 重建、company decision 为
  `skip/no-intent` 的 fresh request，同时令 arbitration seam 强制返回 SKIP。在旧 production 实现上该状态会完成 commit 并
  返回 skip；原始定点红测结果为 `1 failed`，失败原因为 `DID NOT RAISE ValueError`。测试配置了 exact typed commit
  outcome，直接证明 executor 必须 fail-before-publication。

## 修复

### Production owner

在 `dayu/fins/pipelines/filing_upload_publication.py` 新增私有纯 predicate
`_company_decision_allows_canonical_skip`，唯一表达：

- `keep` 且无 intent；或
- `stage` 且存在 exact `preserve_published` intent。

`_canonical_skip_requirements_are_met` 删除原有内联规则，改为调用该 predicate。SKIP executor 在任何 company stage、batch
commit 或 capability transfer 前调用同一 predicate；非法组合立即抛 `ValueError`，此时 `batch_terminal_started` 仍为假，
outer `finally` 通过既有 rollback owner 恰好回滚一次。合法 `keep` 继续 rollback+skip；合法
`stage/preserve_published` 继续 stage→commit→skip。未新增 enum、公共 API、通用框架、兼容逻辑或 warning 语义。

### Owner tests

在 `tests/fins/test_filing_upload_publication.py` 增加：

- 真实 validator 产生的 `keep/no-intent` 与 `stage/preserve_published` 均由同一 private predicate 接受；
- 合法 keep SKIP 仍返回 skipped、commit 零调用、rollback 恰一次；
- arbitration 漂移注入 `skip/no-intent` 时立即失败，company stage 与 batch commit 均零调用，rollback 恰一次，临时文件树与
  输入 bytes 无 publication side effect。

既有 metadata-only skip 参数化测试继续覆盖两条合法 stage/preserve 执行路径、commit outcome 与 warning 投影。

### Finding 02 rereview test seam

DS 定向 rereview 接受 finding 01 的 production 修复，同时发现新增测试通过 `object.__setattr__` 就地修改 frozen
`ValidatedFinsUploadFilingRequest`。Finding 02 成立且严重度为低：当前 `company_meta_decision` 可以通过
`dataclasses.replace` 合法构造，就地写入没有必要，并会绕过 owner 当前及未来的 `__post_init__` 校验。

测试现改为两个模块级 typed helper：

- validator wrapper 调用测试文件已导入的真实 `validate_fins_upload_filing_request`，随后通过 `replace` 返回
  `company_meta_decision=UploadCompanyMetaDecision("skip", None)` 的新 frozen request；
- arbitration helper 只返回 SKIP decision，不再修改 request。

测试没有新增 nested function，也没有降低 finding 01 的红测能力；stage/commit 零调用、begin 一次、rollback exactly once、
临时文件树与输入 bytes 无 durable side effect 的断言全部保持。

## Changed files

- `dayu/fins/pipelines/filing_upload_publication.py`：新增唯一私有 predicate，并在 arbitration / executor 复用。
- `tests/fins/test_filing_upload_publication.py`：新增合法闭集与非法执行边界测试，并按 finding 02 改为 validator wrapper +
  `dataclasses.replace` 的 typed 注入 seam。
- `docs/gateflow/uf-fix11-deepreview-fix-20260817.md`：本 fix / self re-review artifact。

所有既有 untracked review artifacts 仅作为输入读取，未覆盖、回退、stage 或 commit。warning owner/projection、SEC/CN、storage、
runtime、README 与 frozen docs 均无修改。

## Validation

所有命令均在仓库根目录、`source .venv/bin/activate` 后执行。

### 红测

```text
pytest -q tests/fins/test_filing_upload_publication.py::test_incompatible_company_decision_fails_before_canonical_skip_mutation
```

修复前结果：`1 failed`，`Failed: DID NOT RAISE <class 'ValueError'>`。

### 最小修复测试

```text
pytest -q \
  tests/fins/test_filing_upload_publication.py::test_canonical_skip_company_compatibility_accepts_keep_and_preserve \
  tests/fins/test_filing_upload_publication.py::test_canonical_keep_skip_rolls_back_without_stage_or_commit \
  tests/fins/test_filing_upload_publication.py::test_incompatible_company_decision_fails_before_canonical_skip_mutation \
  tests/fins/test_filing_upload_publication.py::test_metadata_only_skip_transfers_capability_and_projects_exact_outcome
```

结果：`5 passed`。

### Owner 文件

```text
pytest -q tests/fins/test_filing_upload_publication.py
```

结果：`41 passed`。

Finding 02 test-only seam 调整后，最小测试再次为 `5 passed`，完整 owner 文件再次为 `41 passed`。

### S1+S2 / S3 focused combined

```text
pytest -q \
  tests/fins \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_wait_adapter.py
```

结果：`2158 passed, 1 skipped, 3 warnings`。唯一 skip 是既有 Docling integration 环境条件；三条 warning 均为已安装
edgar 包的 deprecation warning。

### Production branch coverage

```text
coverage erase
coverage run --branch -m pytest -q \
  tests/fins \
  tests/cli/test_output.py \
  tests/cli/test_fins_commands.py \
  tests/service/test_fins_wait_adapter.py
coverage report -m --include='dayu/fins/pipelines/filing_upload_publication.py'
```

结果：`dayu/fins/pipelines/filing_upload_publication.py` branch coverage `84%`，满足单文件 ≥80% gate。

Finding 02 只调整测试注入方式，production diff 保持逐字不变；因此此前 production combined
`2158 passed, 1 skipped, 3 warnings` 与 branch coverage `84%` 证据仍有效。按 controller 明确裁决，本轮没有重复运行
combined 或 coverage。

### Type 与 static boundary

```text
python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`。

- `git diff --check`：通过。
- cached diff：空；未 stage/commit。
- 禁止边界：warning owner/projection、SEC/CN、storage、runtime、README、frozen docs 均为零 diff。
- 未运行真实 CLI、network、calibration、scenario 或 frozen evidence。

## README decision

已读取 `dayu/fins/README.md` 与 `tests/README.md` 的更新约束。当前 Fins README 已说明 canonical skip 只有无 company intent
或合法 preserve intent 两种路径；本修复只把已有 state-machine invariant 前移到 executor mutation boundary，不改变公共契约、
用户行为、架构、运行命令或测试层级。测试文件也仍属于既有 publication owner matrix。因此遵循 controller 的冻结范围，README
无需更新。

## Self re-review 与 residual risks

- finding 01：`已修复`。arbitration 与 executor 不再复制 compatibility 规则；两者共同消费唯一 private predicate。
- finding 02：`已修复`。测试不再通过 `object.__setattr__` 绕过 frozen owner；validator wrapper 通过真实 validator 与
  `dataclasses.replace` 产生 typed fresh request，arbitration helper 只负责返回 SKIP。
- mutation boundary：非法组合在 stage/commit 前失败，outer rollback 恰一次；合法 keep 与 preserve 两路生命周期不变。
- public/schema boundary：无公共符号、enum、schema、warning 文案或 LLM-facing 文本变化。
- fixed in current slice：canonical SKIP executor 远端不变量依赖与 fail-after-publication 风险。
- assigned to later work unit：aggregate review 已记录的 mutable `file_events`、resolver version 人工 bump、material 同类名称行为、
  name-only physical swap 成本与 post-commit cleanup 可见性；本修复未扩大这些风险。
- uncovered by explicit scope：真实 CLI/network/calibration/scenario/oracle evidence；controller 明确禁止，本轮未运行。
- 未分类 residual risk：无。
- blocking open question：无。
- next entry point：controller aggregate deepreview re-review；是否建立 accepted deepreview commit 由 controller 后续裁决，本轮按指令不
  stage/commit。
