# WU-SEMANTIC-OWNERSHIP-01 aggregate regression fix Slice 1 secret finding Controller evidence

## 1. Gate identity / status

- 时间：`2026-07-18`。
- Gate：Slice 1 validation security finding adjudication；仍属于现有 umbrella WU remediation continuation，不是新 WU或新feature/issue。
- Finding：`S1-SEC-F01`。
- 状态：`OPEN / DESIGN-TRUTH CONTRADICTION / DUAL INDEPENDENT REVIEW REQUIRED`。
- 本artifact不含任何configured secret value、secret ref名称或敏感payload正文。

## 2. Fresh scan 与路径级证据

AgentCodex按accepted plan §6.7扫描本slice outputs、implementation artifact和`git diff --binary HEAD`，只输出计数：

```text
configured_secret_value_count=5
secret_value_match_count=3
matched_path_count=1
```

Controller在不输出secret value的前提下只追加路径/结构定位：

```text
matched_path=workspace/tmp/wu-semantic-ownership-01-ar-fix-s1-real-compactor/
  test_real_compactor_public_ope0/host.sqlite3
file occurrences=3

table=event_log column=payload_json rowid=2 occurrences=1
table=event_log column=payload_json rowid=13 occurrences=1
event_type=USER_INPUT_ACCEPTED
event_class=canonical_fact
matched_json_path=effective_execution_config.config.runner_spec.headers.Authorization
```

第三个file-level occurrence来自SQLite物理文件表示；logical row scan精确定位两条current canonical facts。`git-diff://HEAD`零命中，review/control/code diff均非命中owner。

## 3. Production同源链

这不是real-smoke fixture独有行为：

1. `dayu/service/host_assembly.py::_runner_spec_from_model`调用`_render_headers`。
2. `_render_headers`从`api_key_ref`命名的环境变量读取值，并把`{{REF}}`替换为实际值，返回含明文Authorization的`RunnerSpec.headers`。
3. `dayu/host/admission.py::_resolve_followup_effective_facts`把该完整`RunnerSpec`交给`effective_execution_config_json`。
4. `dayu/host/_execution_config_projection.py::runner_spec_json`用`dict(sorted(runner_spec.headers.items()))`原样投影headers。
5. 该projection作为`USER_INPUT_ACCEPTED.effective_execution_config`写入EventLog；dispatch/replay又从同一durable projection还原`RunnerSpec`。

`dayu/host/_execution_config_projection.py`的current durable implementation来自本umbrella WU内accepted commit `2f2b73f8`（R3-A S1），因此finding属于本umbrella已实施代码的remediation审查范围，而不是外部无关历史代码。

## 4. Design-truth直接冲突

- `docs/host/design.md`配置/装配边界规定Service/execution environment负责provider secret的使用、脱敏与保护。
- 同文ordinary run contract明确：Host不接收raw provider client、API key明文；`RunnerSpec.api_key_ref`只是secret引用名，不是secret本体。
- Host要求冻结effective runner spec以支持retry/replay/recovery，但current实现把已渲染Authorization明文当成可冻结headers；这两个要求在current代码中没有可同时满足的owner seam。
- `docs/engine/design.md`与`dayu/engine/README.md`也明确LLM-facing/diagnostic projection不得包含provider headers、Authorization/API key；本finding虽发生在durable canonical fact而非LLM projection，仍证明secret protection边界没有由唯一owner实现。

因此以下局部处理均不可接受：

- 删除/忽略gitignored smoke SQLite或缩小secret scan范围；
- 在测试里换synthetic key、跳过real compactor或把非零匹配标为waiver；
- 仅在EventLog JSON中删除/替换Authorization，却让dispatch/replay从redacted值构造RunnerSpec；
- 增加下游fallback、header名黑名单、兼容分支或统一authorization framework；
- 把明文移到另一个未定义保护语义的artifact/payload ref。

## 5. Independent review questions

AgentMiMo与AgentDS必须各自完整核对design truth、production链、durable replay/dispatch消费者与本证据，并回答：

1. `S1-SEC-F01`是否为valid blocking finding，还是存在足以拒绝它的direct owner evidence？
2. 唯一正确semantic owner与最小跨层boundary是什么？哪些owner必须修改，哪些层必须零改动？
3. current design truth是否足以code-generation，还是必须先做用户product decision/design-doc correction？
4. 如何同时满足：EventLog零secret value、current Run执行、retry/replay/recovery可解释、per-run RunnerSpec override、Service secret protection、Host不接收API key明文？
5. 是否存在不引入permission schema/authorization framework、不越界Issues 142/151/175/177/178的最小方案？
6. 需要哪些negative/real tests与secret scan证明修复不是test shim或表面redaction？

## 6. Current stop / next entry

- Slice 1 implementation不是ready for code review，AR-F01/03/04不能在secret gate失败时正式close。
- AgentCodex不得自行修复；三测试delta与implementation artifact保持protected。
- Next entry：AgentMiMo / AgentDS并发完整design-truth deepreview；Controller随后裁决是否需要用户product decision、plan correction或新的umbrella内部remediation slice。
