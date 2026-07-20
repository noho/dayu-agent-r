# WU-SEMANTIC-OWNERSHIP-01 / R12 S2 corrected-plan review-fix Controller validation

## 1. Gate 与 verdict

- Gate：既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` / R12 S2 corrected-plan review-fix 的 Controller 独立验证；不是新 WU/sub-WU。
- Fixed plan：`docs/host/wu-semantic-ownership-01-r12-init-workflow-plan.md`，708 行 / 105,368 字节 / SHA-256 `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`。
- AgentCodex fix artifact：`docs/reviews/wu-semantic-ownership-01-r12-s2-stop-condition-plan-review-fix-codex.md`，73 行 / 8,938 字节 / SHA-256 `ba141650a8c2bc94a3e82bce63bf2b840c4255ceda64a8f431839b14146d4664`。
- Verdict：`PASS / R12-S2-PR-F01..F06 CLOSED 6/6 / READY FOR DUAL COMPLETE PLAN RE-REVIEW`。
- 当前仍不授权 S2 implementation、S3、aggregate、commit、push 或 PR。

## 2. 独立 owner / motivation 验证

Controller 完整读取 fixed plan 与 fix artifact，并重新核对当前 Service 代码、tests 与所有调用点：

1. `dayu/service/host_assembly.py::_effective_fins_workspace_root_config_value` 的 ordinary contract 确实让合法 raw 显式绝对/相对 Fins root 优先；`tests/service/test_host_assembly.py::test_fins_tool_discovery_spec_preserves_explicit_workspace_root` 直接锁定该行为。
2. PRESERVE 保留 raw config bytes，因此只把 ordinary `workspace_root` 改成 private root不能支配显式 Fins root。HIGH finding `R12-S2-PR-F01` 动机成立。
3. `_is_fins_workspace_bound_provider_config` 与 effective-config precedence 已由 `host_assembly.py` 唯一拥有；在同一 owner 增加 direct validation-only override 是最小正确边界。CLI strip raw field、复制 provider classification、metadata-only discovery 或 snapshot-drift compensation都不是可接受替代。
4. Fixed plan 精确区分 ordinary public workspace root 与 private Fins override：普通 `entrypoint_runtime` 显式传 `None`，R12 init validation是唯一 production non-`None` consumer；非 Fins/Web effective config仍消费 ordinary root。
5. Service/Fins producer语义不变，只有 Service effective-config owner、ordinary caller、direct owner test和 owner README 进入 S2 allowlist；Fins/package/Host/Engine/Tool/runtime/design/deferred ISSUE paths继续零 diff。

Design contradiction：`NONE`；blocking questions：`NONE`。

## 3. Accepted groups closure

| Group | Controller validation | 状态 |
|---|---|---|
| `R12-S2-PR-F01` | §3/§6.4/S2 tests/scans锁定 Service-owned override precedence、三类合法 raw root、raw bytes不变、ordinary runtime不变和非 Fins隔离；owner/allowlist正确。 | closed |
| `R12-S2-PR-F02` | §8 允许 owner-module syscall monkeypatch/mock，明确它不属于 provider/catalog shim；禁止 production callback/factory/test seam，并逐阶段列出 fault matrix。 | closed |
| `R12-S2-PR-F03` | validation child已删但 POSIX parent sync失败时只保留仍存在的 staging/container truth；partial delete只承诺真实 path/stage，不承诺完整取证树。 | closed |
| `R12-S2-PR-F04` | POSIX 使用直接 capability-gated fd-safe deletion；Windows 使用 owner-local identity/quarantine/reparse classification，不把 capability false变成全局拒绝。预置 nested junction真实 job必须 publication 前 fail closed、config不发布、external sentinel不变；race/fault证明与其分离。 | closed |
| `R12-S2-PR-F05` | file content、directory entry、secure deletion、per-root atomic visibility/live rollback已分开；Windows诚实不承诺未验证的 parent-directory crash durability，并要求 real normal transaction evidence。 | closed |
| `R12-S2-PR-F06` | S2 exact Service diff、override consumer scan、CLI classification/raw-strip negative scan、七个 production单文件 coverage与其余 zero-diff scope均已同步。 | closed |

Rejected/no-fix保持正确：不为 partial delete复制 forensic tree；不把 RESET 双 root snapshot/replace伪装成 single-syscall atomic，也不扩 Host/process lock、kill或watcher。

## 4. Controller follow-up

第一次完整读取后，Controller 发现两处同任务规格卫生并要求 AgentCodex窄修：

1. §10.2 旧 stop condition仍把整个 `workspace_root`写成 private，与新 §6.4冲突；终态已改为 `workspace_root=<canonical public workspace>` 加 `fins_workspace_root_override=<recorded canonical absolute private validation root>`。
2. S3 对 scan 前预置 nested junction曾允许“拒绝或只删除 entry”两种通过；终态已锁定为 pre-publication fail closed、truthful retained/absent path、public config不发布与 external sentinel byte/identity不变。“只删除 entry”仅属于独立 scan-delete race/fault证明。

AgentCodex 同任务 follow-up 没有修改历史 §15 provenance、scope、产品代码、测试、README、workflow或其它 artifact；fix artifact同步了 before/after plan identity。

## 5. 可执行性与机械验证

Controller 重新计算并通过：

- Service source locks：
  - `dayu/service/host_assembly.py` = `54559d2e...be52`
  - `dayu/service/entrypoint_runtime.py` = `014c5ea0...15c6`
  - `tests/service/test_host_assembly.py` = `04675e66...203e`
  - `dayu/service/README.md` = `4f4f30b8...be9d`
- S1 terminal product/test locks仍为 `937315f3...754`、`71be5ba8...77f`、`086a143c...d9f`、`820c2bf2...01a`；S2/S3新路径仍 ABSENT。
- `pytest tests/service/test_host_assembly.py --cov=dayu.service.host_assembly --cov-report=term --cov-fail-under=80 -q`：`73 passed`，coverage `95%`。
- `pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_interactive_path.py tests/service/test_entrypoint_runtime_prompt_path.py --cov=dayu.service.entrypoint_runtime --cov-report=term --cov-fail-under=80 -q`：`49 passed`，coverage `88%`。
- 三个 cumulative slices仍精确为 S1/S2/S3；未新增 slice/sub-WU。
- `git diff --check`：PASS；staged tree：empty。
- 工作树中的 control、S1累积 product/tests 与既有 review artifacts均为当前 umbrella有意状态，未被本 plan-fix覆盖或回滚。

## 6. 下一 gate

只授权 AgentMiMo 与 AgentDS 并发完整 re-review exact fixed-plan SHA `aa7b50a90c9623ea8dcafe8c4c651665b16b9ee3be76ec8357c4d47977fb2a4c`。两路必须独立验证：

- `R12-S2-PR-F01..F06` 6/6 closure；
- explicit absolute/relative Fins root是否真的被 override且 ordinary runtime仍不变；
- Windows pre-seeded reparse与 scan-delete race是否没有混为同一通过标准；
- POSIX/Windows durability承诺是否 truthful且实现规模不过度；
- fault matrix、allowlist、coverage、README/scans是否可执行；
- rejected paths、deferred ISSUE、Topic 8/9与三-slice boundary是否保持。

Implementation、S3、aggregate、commit、push和PR继续未授权。
