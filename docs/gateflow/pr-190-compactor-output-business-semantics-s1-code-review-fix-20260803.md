# PR 190 Compactor 输出业务语义 S1 code-review fix

## Gate metadata

- Gate：`code review -> fix`
- Work unit：补齐 Compactor LLM-facing 输出 schema 的核心字段与显式丢弃原因业务语义
- Slice：`S1 — Compactor output business semantics`
- Branch：`codex/interactive-oracle`
- Implementation artifact：`docs/gateflow/pr-190-compactor-output-business-semantics-s1-implementation-20260803.md`
- Decision：`fix-complete`
- Completion status：`code-review-fix-complete`
- Current gate after this artifact：`re-review`
- Next entry point：对 F01/F02 的 owner-test 修复执行 evidence-based re-review，并确认 F03 重复 finding 已关闭
- Blocking open questions：无
- Artifact path：`docs/gateflow/pr-190-compactor-output-business-semantics-s1-code-review-fix-20260803.md`

本 fix gate 在 code review 接受前不 stage/commit/push；re-review 接受后由 accepted slice checkpoint 只处理 intended files，并按 Gateflow 自动推进。

## Scope and owner decision

本轮只修复 deterministic owner-test 的回归守卫缺口。LLM-facing 业务语义仍由 `dayu/config/prompts/scenes/conversation_compaction_user.md` 唯一拥有；prompt 内容、Host/schema、publication manifest 与其它测试均不需要变化。

### Changed files

- `tests/host/test_llm_compaction.py`：补齐七个 frozen semantic fragments，并扩展 static forbidden-term guard。
- `docs/gateflow/pr-190-compactor-output-business-semantics-s1-code-review-fix-20260803.md`：新增本 durable fix artifact。

除以上两项外没有本 fix gate 的文件变化。既有 implementation dirty set、implementation artifact 与两路 review artifact 均原样保留。

## Review evidence

| Reviewer | Artifact | SHA-256 | Result |
|---|---|---|---|
| AgentMiMo | `docs/reviews/code-review-20260803-220950.md` | `3d1547d292af0b5a64fb55c63211e35949273d1e6cc1dbf1a18d36f1156832aa` | 无 finding，`pass` |
| AgentDS | `docs/reviews/code-review-20260803-221641.md` | `d62942a55ecd0740ec84d879b561b3cd78ad9ccd899e72aa5b0819aa609b83c9` | F01/F02/F03，`pass-with-findings` |

两份 review artifact 只读引用，fix 前后 hash 未变。

## Controller adjudication and fix status

### F01 — `accepted` — `已修复`

Owner test 已在对应 section 分组补齐以下七个 frozen fragments：

1. `不得发明新结论`；
2. `继续保留旧内容会过时、冲突或误导`；
3. `replacement 中保留的是替代后的当前内容`；
4. `丢弃它不会损失独立业务信息`；
5. `不得加入材料没有的事实、结论或任务`；
6. `不得把 \`trace_material\` 或 \`answer_material\` 当作事实依据`；
7. `不把工具证据、未来动作或新推断伪装成既有结论`。

每个独立判断均有自己的 exact substring assertion，不再由同一句前半段间接代表后半段语义。

### F02 — `accepted` — `已修复`

Static user-prompt forbidden guard 新增：

- 大小写敏感的 `Compact` 前缀，覆盖当前及后续 `Compact*` 内部 typed contract 名称，包括 reviewer 列出的具体类型；
- 内部模块名：`compaction.py`、`context_governance`、`memory.py`；
- Host 治理类型：`MemoryProjectionPolicy`、`SessionSummaryMemoryView`；
- 内部治理标识：`event_id`、`payload_ref`。

现有 business-required output schema、字段名与八种 `source_kind` 的正向存在断言保持不变；`Compact` 检查大小写敏感，不会误禁业务所需的小写 schema labels。

### F03 — `rejected-with-reason`

F03 描述的是 F01 已识别的同一 substring-fragment 覆盖缺口，没有独立 root cause、实现 owner 或额外修复动作。F01 的七项独立语义 assertion 完整补齐后，F03 所述证据不再成立；不重复增加第二套测试结构。

## Diff summary

- Production/prompt/publication diff：无。
- Owner-test fix：新增 7 个 frozen semantic assertions。
- Forbidden guard fix：新增 8 个 forbidden fragments，其中 `Compact` 前缀覆盖 reviewer 列出的 `Compact*` 具体类型。
- 没有新增 helper、类型、schema、状态机、fallback、loose parsing、兼容分支或下游补偿。

## Validation

全部 Python 命令均在 `source .venv/bin/activate` 后运行。

| Command | Result |
|---|---|
| `pytest tests/host/test_llm_compaction.py::test_prompt_assets_are_self_contained_for_fresh_v2_contract -q` | `1 passed` |
| `pytest tests/host/test_public_compact_smoke.py::test_default_compactor_prompt_is_llm_facing_and_self_contained -q` | `1 passed`；assembled prompt、完整 example parser/governance 路径保持通过 |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `git diff --check` | pass，无输出 |

## Digest preservation

### Intentionally unchanged implementation/publication files

- `dayu/config/prompts/scenes/conversation_compaction_user.md`：`sha256:a2f5711c84f6fdd51f921e5d266d05cdb3f6a34a6c8321ffc42f0c5dc75a0dce`
- `docs/cli_init_workspace_manifest_v1.json`：`sha256:fb6d0ba8fbf01b093419d178daf09c145bc8643e03b900703a91f2a3ff005f6c`
- `tests/cli/test_smoke_cli_init_provider_matrix.py`：`sha256:c86520e50941e25c5451b36669c74ad874a1da52c0145cda3ecc6fd6e7a65faa`
- `tests/host/test_public_compact_smoke.py`：`sha256:64ade7605786c2308e16e087e37ee4fa5f519886113cbe33923144a526c33e31`

以上 digest 与 fix 前基线一致，证明 prompt bytes、两级 publication truth、public smoke 均未被本 fix 修改。

### Changed owner test

- `tests/host/test_llm_compaction.py`：fix 后 `sha256:4d77165a473467c8fd57964e06c3b07cc5679e05917c093d98d637af6974eac0`。

## Docs decision

- `tests/README.md`：本 fix 只补强现有 owner-test assertions，不新增测试层级、运行方式或维护规则；`no-change`。
- `dayu/config/README.md`、Host/design、根 README 与 `dayu/README.md`：没有对应代码、prompt、contract、装配、分层或用户工作流变化；`no-change`。

## Residual risks and uncovered areas

- `fixed in current slice`：F01 的七项 frozen semantic regression blind spots 与 F02 的活跃内部术语 guard 缺口。
- `rejected-with-reason`：F03 与 F01 同根重复，不构成独立 residual risk。
- `assigned to later work unit`：真实 provider 对字段分类、drop reason 与 repair cap 的稳定遵循度；owner 为 real Compactor conformance evidence work unit。
- `assigned to later work unit`：frozen oracle/scenario 的 current-head readiness refresh；owner 为独立 readiness refresh work unit。
- `assigned to later work unit`：`forward_intents.status` 与 `reference_continuity.reason` 的 LLM-facing 业务语义；owner 为后续独立 LLM-facing schema work unit。

没有未分类 residual risk，没有 blocking open question。

## Completion decision

`code-review-fix-complete`

AgentMiMo 无 finding；AgentDS F01/F02 已按 Controller 裁决在 owner-test boundary 完整修复，F03 已以重复 root cause 驳回。定向 owner test、public smoke、完整 pyright、diff check 与 digest preservation 均通过。下一未完成 gate 是 `re-review`；本 gate 不 stage/commit/push。
