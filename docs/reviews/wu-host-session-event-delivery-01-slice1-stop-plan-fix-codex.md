# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 1 Stop Plan Fix

## 元数据

- Work Unit：`WU-HOST-SESSION-EVENT-DELIVERY-01`
- Gate：`plan-fix-after-slice1-stop`
- Controller decision：`return-to-plan-fix`
- Accepted plan commit：`8b29462c`
- 修订对象：`docs/host/wu-host-session-event-delivery-01-plan.md`
- 执行边界：只修订plan manifest，不继续implementation、test、review、commit、push或PR。

## 第一性原理与直接证据

动机成立。`Host.watch_session_events(...)`的async factory/public iterator contract由Host public API拥有，所有direct caller必须显式`await`。Controller artifact与当前source scan共同证明，accepted plan §5.2漏列了4个真实`utils/` public smoke direct callers；这些调用当前把factory返回值直接当作iterator消费。因此根因是S1 caller闭集不完整，不是public contract错误，也不授权任何下游兼容层。

## 精确修订

1. §5.2 public watch direct caller闭集新增：
   - `utils/smoke_host_public_r03_semantic_ownership.py`
   - `utils/smoke_host_public_conversation_memory.py`
   - `utils/smoke_host_public_conversation_memory_scenarios.py`
   - `utils/smoke_host_public_multiturn.py`
   所有调用必须显式`await`。
2. §7 S1 allowed scope显式授权上述4个文件仅做async factory/public iterator contract机械传播；不得修改smoke场景、断言、数据流、Service relay或其它行为。
3. 已授权Service/CLI fake的`__aiter__`精确返回类型修复继续属于原S1机械传播范围，不扩大scope。
4. S1 validation新增上述4个脚本的`py_compile`，完整pyright继续覆盖`utils/`，source propagation scan扩展为`dayu tests utils`。
5. `utils/`按`AGENTS.md`默认无需新增测试或单文件coverage，但production/test文件的coverage acceptance保持不变。

## 冻结边界

- 禁止同步compatibility、lazy attach、下游coroutine兼容以及`cast`/`getattr` shim。
- item-only policy与packaged `512/4`保持不变，不增加byte bound。
- S2、S3、S4 scope及accepted plan其它内容保持不变。
- 暂停中的production/test/utils implementation changes、Controller独占control doc与stop adjudication artifact均不修改、不撤销、不格式化、不stage、不清理。

## 文档验证

- 仅对本次修改的plan与本artifact执行whitespace/diff check。
- 复核task前后production/test/utils implementation diff，确认本次plan fix未产生新变化。
- 按Controller边界不运行implementation tests、pyright或implementation收口验证。

## 结论

Plan manifest已按`return-to-plan-fix`裁决精确补齐，可交回原独立review与Controller acceptance；无blocking open question。
