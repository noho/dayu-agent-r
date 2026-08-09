# PR 190 F11/F12 aggregate review fix（2026-08-06）

## Gate metadata

- Work unit：PR 190 F11/F12 aggregate fix。
- Gate：aggregate deepreview finding fix。
- Finding source：
  `docs/reviews/pr-190-f11-f12-aggregate-review-adjudication-20260806.md`。
- Fix scope：仅 accepted `DS-01`。
- Fix result：`PASS`。
- Current gate / next entry point：MiMo 与 DeepSeek dual aggregate re-review。
- Stop boundary：本 artifact 后不启动 re-review，不 stage/commit/push，不修改 PR。
- Artifact path：
  `docs/reviews/pr-190-f11-f12-aggregate-fix-20260806.md`。

## Scope、动机与 owner decision

`CompactSemanticSectionV3` 合法拥有 Host semantic coverage categories，
`compact_output_template_v3()` 合法投影 public compact output shape。两个 owner 不应通过
导出私有 descriptor、生成 enum 或新增 runtime import 合并，但五个语义 section 的名称与顺序是必须成立的跨契约
invariant。现有
`test_compact_structure_owner_projects_template_schema_rules_and_parser` 已集中验证 public template、schema、prompt rules
与 parser 的同源结构，因此该 owner-level contract test 是最小且正确的验证边界。

本 fix 仅在该既有测试中增加顺序敏感断言：

```python
tuple(item.value for item in CompactSemanticSectionV3) == tuple(template)[1:]
```

其中 `template` 是 `compact_output_template_v3()` 的 fresh public projection；`[1:]` 只排除固定的 root
`schema` key。该断言会在语义 section 新增、删除、重命名或重排但另一 owner 未同步时失败。

未导出 `_ROOT` 或其它私有 descriptor，未修改 production/runtime、prompt、schema、registry、design、docs/README
或既有 review/adjudication artifact。裁决 rejected 的 `DS-02`、`DS-03` 和三个 open question 均未处理。

## Changed files

- `tests/host/test_compaction_contract.py`
  - 在既有 structure owner test 中增加 enum values 与 public template semantic keys 的 exact ordered equality assertion。
- `docs/reviews/pr-190-f11-f12-aggregate-fix-20260806.md`
  - 记录 finding closure、直接验证、docs decision、residual risk 与 gate stop point。

## Finding closure

| Finding | Adjudication | Fix status | Direct evidence |
| --- | --- | --- | --- |
| `DS-01` | accepted low-severity owner-test gap | 已修复 | 既有 owner test 现在 exact ordered 比较 `CompactSemanticSectionV3` values 与 public template 去除 `schema` 后的 keys；专项 node 与 focused suites 均通过 |
| `DS-02` | rejected-with-reason | 证据失效 | structure shape 与 prompt business prose 是不同 owner；未修改 prompt 或测试 |
| `DS-03` | rejected-with-reason for this work unit | 证据失效 | broad catch 是既有 fail-closed 行为及 Host observability debt；未修改 runtime |

## Direct validation

所有 Python 命令均先执行 `source .venv/bin/activate`。

### Owner invariant

```bash
pytest \
  tests/host/test_compaction_contract.py::test_compact_structure_owner_projects_template_schema_rules_and_parser \
  -q
```

结果：`1 passed in 0.31s`。该 node 直接执行新增 exact ordered invariant，并同时保留 template/schema/rules/parser
round-trip contract。

### Focused compaction contracts、LLM compaction 与 changed-file coverage

```bash
pytest \
  tests/host/test_compaction_contract.py \
  tests/host/test_llm_compaction.py \
  --cov=dayu.host.compact_structure \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

结果：`51 passed in 0.49s`；`dayu/host/compact_structure.py` 为 `203` statements、`21` missed、
`90%` displayed coverage（exact total `89.66%`），通过 `>=80%` 门槛。

### Type、lint、JSON 与 diff

```bash
pyright dayu/ tests/ utils/
ruff check tests/host/test_compaction_contract.py
python -m json.tool docs/cli_ci_oracles.json >/dev/null
python -m json.tool docs/cli_ci_scenarios.json >/dev/null
git diff --check
```

结果：

- pyright：`0 errors, 0 warnings, 0 informations`；仅提示存在更新版本，非检查 finding；
- Ruff：`All checks passed!`；
- JSON validation：两份 PR registry JSON 均有效；
- `git diff --check`：通过。

## Docs decision

- 本 fix 没有新增测试层级，只在已有 Host compaction contract owner test 内增加 invariant；按
  `tests/README.md` 的更新约束不需要修改 tests README。
- production、public contract、schema、prompt、registry、用户工作流和分层装配均未改变，不触发其它 README 或 design 更新。
- 用户明确禁止修改 prompt/schema/registry/docs/README；除本次明确要求的 review artifact 外均保持不变。

## Residual risks and uncovered areas

- `DS-01`：`fixed in current slice`；等待独立 MiMo 与 DeepSeek dual aggregate re-review 确认最终状态。
- `DS-03` 所述既有 traceback observability debt：`assigned to later work unit`，owner 为 Host observability；本 fix 不改变其
  fail-closed contract，也不将 rejected finding 重新纳入当前 scope。
- Replacement scenario adjudication：`assigned to later work unit`，owner 为 Oracle controller；本 fix 未修改 registry 或 evidence。
- 未分类 residual risk、blocking open question、deferred finding、needs-more-evidence：无。

## Completion status

- Aggregate finding fix：完成。
- Accepted finding：`DS-01 已修复`。
- Validation：通过。
- Commit/push/PR/re-review：均未执行。
- Gateflow 当前 gate / next entry point：双路 aggregate re-review；按用户 stop boundary 停在该 gate 入口。
