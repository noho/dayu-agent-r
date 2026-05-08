# Host P5.5 Plan Review

## Review 结论

原审查结论为不通过，需先修复 1 个 Medium finding 后再进入用户人工 review。本轮文档修复后，Finding 1 已按建议处理，后续仍需用户人工 review。

本次只审查 `docs/host/phase5_5-plan.md`，未修改该 plan 本体。P5.5 的动机成立：P1-P5 已完成 no-full-governance 纵向 smoke，统一回看 deferred / 非目标 / 不实现能力能降低漏排、误排和旧事实污染风险。plan 的目标、非目标、扫描范围、分类状态、early scan 历史定位、review gate 与停止点整体方向正确，覆盖了 P5.5 用户意图，也明确不写生产代码。

原阻塞点在于 migration-plan 写回 gate 的表述不一致：部分段落会被实施 Agent 理解为“仅完成文档审查即可改总控计划”，弱化了总控流程中“review 通过后停等用户确认”的硬停止点。该阻塞点已在 `docs/host/phase5_5-plan.md` 中统一为 patch 清单、review、用户人工确认、再写回的顺序。

## 审查依据

- `AGENTS.md`
- `docs/host/migration-plan.md`
- `docs/host/phase5_5-plan.md`
- 抽查的 P1-P5 plan / review deferred 线索
- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`

## Finding 1 [Medium] [已修复]

`migration-plan` 写回 gate 表述不一致，可能弱化用户确认停止点。

证据：

- 旧版 `docs/host/phase5_5-plan.md:80` 使用二选一式 gate 表述，允许被理解为审查与用户确认任选其一。
- 旧版 `docs/host/phase5_5-plan.md:152`-`158` 只描述审查后的写回范围，没有同时要求用户确认。
- 旧版 `docs/host/phase5_5-plan.md:226` 只写审查后的写回动作，同样缺少用户确认条件。
- 但同一 plan 又在 `docs/host/phase5_5-plan.md:165`-`167`、`267`-`272` 明确要求 review 通过后停等用户人工 review，用户确认前不得实施 migration-plan 写回。
- 总控流程 `docs/host/migration-plan.md:61`-`67` 要求 phase plan review 通过后停等用户人工 review，用户确认后才 commit phase plan 与 review 文档；`docs/host/migration-plan.md:84`-`91` 也禁止用户确认前 commit / push / create PR / merge。

影响：

P5.5 的主要输出之一是总控排期与边界修订建议，`docs/host/migration-plan.md` 又是后续 P6+ 目标、非目标、验收信号的真源。如果实施 Agent 按较弱表述在仅完成文档审查后直接修改 migration-plan，会绕过用户对 phase 边界调整的人工确认，破坏总控 / Agent 分工。

建议修复：

把所有 migration-plan 写回条件统一改成“先输出 patch 清单；常规 plan review 与必要专项 review 通过后，仍必须停等用户人工确认；用户确认后才允许写回 migration-plan”。如果 P5.5 inventory 发现需要调整 P6+ 目标、非目标或验收信号，也应先提交建议清单与 review 证据，不由实施 Agent 单方面落地总控真源变更。

## 其余检查结果

- 目标清晰：`docs/host/phase5_5-plan.md:5`-`11` 明确 P5.5 只做扫描、分类、排期核对与文档修订建议，不写生产代码。
- 范围正确：`docs/host/phase5_5-plan.md:52`-`60` 覆盖 P1-P5 phase plan、migration-plan P6-P13、当前 design / README、review deferred / remaining risk 与代码 TODO / FIXME 线索。
- 分类规则可执行：`docs/host/phase5_5-plan.md:82`-`99` 给出封闭状态枚举，并禁止“后面再说”等模糊状态。
- early scan 边界正确：`docs/host/phase5_5-plan.md:20`、`103`、`139`、`223`、`251` 都要求把 `phase5_5-early-scan.md` 作为 P5 前历史线索，不把其旧判断当当前事实。
- P5.5 用户意图覆盖充分：`docs/host/phase5_5-plan.md:101`-`123` 已把 ToolRegistry、business fins tools、OutputContract / validation replay、EventLog persistence、Session lifecycle、Attempt recovery、Remote、Outbox、Wait、audit hard-gate、memory / context governance、provider token estimator、transparent fetch_more 等高风险项列为初始关注清单。
- review gate 基本正确：`docs/host/phase5_5-plan.md:229`-`247` 要求常规 plan review 与至少一个 OLD / NEW、最佳实践或架构边界 review，并对 OutputContract、ToolRegistry、`dayu.fins.storage`、P6 observer / P12 hard-gate、P7 / P8 lifecycle 分界提出专项检查。

## 验证

执行过的自查命令：

- `git status --short`
- `git log --oneline -5`
- `sed -n '1,260p' AGENTS.md`
- `sed -n '1,260p' docs/host/migration-plan.md`
- `sed -n '1,520p' docs/host/phase5_5-plan.md`
- `nl -ba docs/host/phase5_5-plan.md | sed -n '1,360p'`
- `nl -ba docs/host/migration-plan.md | sed -n '1,230p'`
- `rg -n "非目标|不实现|明确不做|后移|defer|Deferred|暂不|不包含|未落地|Remaining risks|remaining risk|TODO|FIXME" docs/host/phase1-plan.md docs/host/phase1_5-plan.md docs/host/phase2-plan.md docs/host/phase3-plan.md docs/host/phase4-plan.md docs/host/phase5-plan.md docs/host/*review*.md`
- `rg -n "P5|P5.5|当前未落地|未落地|后移能力|context overflow|fetch_more|ToolRegistry|OutputContract|validation|business fins|provider token|governance" docs/host/design.md dayu/host/README.md dayu/README.md tests/README.md`

说明：最后一条命令因仓库当前不存在 `dayu/README.md` 返回了 `rg` 路径错误，但仍输出了 `docs/host/design.md`、`dayu/host/README.md` 与 `tests/README.md` 的匹配结果。该错误不影响本次对 P5.5 plan 的 finding 判断。
