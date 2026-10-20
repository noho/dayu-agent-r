"""真实 Fs 原文工具经过进程与 Host 截断后逐页取齐的联合契约。"""

from pathlib import Path
from collections.abc import Mapping
import json

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionRequest, ToolCallRequest
from dayu.contracts.tool_call import BatchToolExecutionContext
from dayu.host.tool_runtime import ToolRuntimeHandle
from dayu.contracts.tool_declaration import ToolBundle
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.fins.domain.enums import SourceKind
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools.fins_limits import FinsToolLimits
from dayu.fins.tools.fins_tools import build_fins_read_tool_definitions
from tests.fins.test_original_read_runtime import publish_original
from tests.fins.test_original_read_contract import HTML
from tests.tools.test_combined_tools_acceptance import _tool_runtime, _context
from tests.host.test_toolruntime_truncation_fetch_more import _source_ref
from typing import cast


def _call(name: str, arguments: Mapping[str, JsonValue], ordinal: int) -> ToolCallRequest:
    """参数：名称、参数、次序。返回：实际工具请求。异常：构造错误。"""
    return ToolCallRequest(
        tool_call_id=f"original-{ordinal}",
        name=name,
        arguments=arguments,
        index_in_iteration=ordinal,
        provider_state=None,
    )


@pytest.mark.asyncio
async def test_real_process_tool_fetch_more_then_next_original_page(tmp_path: Path) -> None:
    """参数：真实 Fs 根。返回：无。异常：双层截断、身份、范围、拼接或 cursor 单次语义不符。"""
    text = "<html><body>" + "中&amp;\r\n" * 50 + "</body></html>"
    publish_original(tmp_path, text)
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    try:
        reader = runtime.get_read_runtime()
        assets = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)
        asset = next(a["asset"] for a in assets["assets"] if a["asset"]["filename"] == "main.html")
        definitions = build_fins_read_tool_definitions(
            reader, tmp_path, FinsToolLimits(original_text_display_chars=17, original_structure_display_items=1)
        )
        handle, _ = _tool_runtime(ToolBundle(definitions=definitions), (_source_ref(),))
        context = _context()
        start, ordinal = 0, 0
        chunks: list[str] = []
        receipt: list[JsonValue] = []
        while True:
            ordinal += 1
            arguments: dict[str, JsonValue] = {
                "ticker": "TEST",
                "document_id": "original-doc",
                "source_kind": "filing",
                "filename": "main.html",
                "expected_sha256": asset["sha256"],
                "start": start,
                "max_chars": 100,
            }
            response = await handle.tool_executor.execute(
                BatchToolExecutionRequest(calls=(_call("read_original_text", arguments, ordinal),), context=context)
            )
            outcome = response.records[0].outcome
            assert isinstance(outcome, ToolCompletedOutcome)
            value = outcome.result.value
            receipt.append(value)
            assert isinstance(value, Mapping)
            assert value["asset"] == asset
            assert value["requested_range"] == {"asset": asset, "start": start, "end": len(text)}
            wrapped = value["text"]
            assert isinstance(wrapped, Mapping) and wrapped["truncated"] is True
            prefix, fetch = wrapped["value"], wrapped["fetch_more"]
            assert isinstance(prefix, str) and isinstance(fetch, Mapping)
            ordinal += 1
            more = await handle.tool_executor.execute(
                BatchToolExecutionRequest(
                    calls=(
                        _call("fetch_more", {"cursor": fetch["cursor"], "scope_token": fetch["scope_token"]}, ordinal),
                    ),
                    context=context,
                )
            )
            rest = more.records[0].outcome
            assert isinstance(rest, ToolCompletedOutcome) and isinstance(rest.result.value, str)
            receipt.append(rest.result.value)
            page = prefix + rest.result.value
            assert page == text[start : start + 100]
            assert value["returned_range"] == {"asset": asset, "start": start, "end": start + len(page)}
            chunks.append(page)
            if value["next_start"] is None:
                assert value["truncated"] is False
                break
            assert value["truncated"] is True and value["next_start"] == start + len(page)
            start += len(page)
        assert "".join(chunks) == text
        target = tmp_path / "host-joint-receipt.json"
        target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
        print(f"完整 Host 联合回执：{target}")
        assert all(
            d.schema.function.description and "省略 limit" in d.schema.function.description
            for d in definitions
            if d.name in {"read_original_text", "read_original_structure", "query_original_facts"}
        )
    finally:
        runtime.close()


async def _execute(
    handle: ToolRuntimeHandle,
    context: BatchToolExecutionContext,
    name: str,
    arguments: Mapping[str, JsonValue],
    ordinal: int,
) -> JsonValue:
    """参数：真实 Host、上下文、调用名/参数/次序。返回：实际完整业务投影。异常：非 completed 断言失败。"""
    response = await handle.tool_executor.execute(
        BatchToolExecutionRequest(calls=(_call(name, arguments, ordinal),), context=context)
    )
    outcome = response.records[0].outcome
    assert isinstance(outcome, ToolCompletedOutcome)
    return outcome.result.value


@pytest.mark.asyncio
async def test_structure_namespace_then_facts_survive_host_list_truncation(tmp_path: Path) -> None:
    """参数：真实 Fs 根。返回：无。异常：公开 namespace 发现、facts 或两层列表续读契约不符。"""
    publish_original(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    try:
        reader = runtime.get_read_runtime()
        definitions = build_fins_read_tool_definitions(
            reader, tmp_path, FinsToolLimits(original_structure_display_items=1, original_facts_display_items=1)
        )
        handle, _ = _tool_runtime(ToolBundle(definitions=definitions), (_source_ref(),))
        context = _context()
        assets = await _execute(
            handle,
            context,
            "list_document_assets",
            {"ticker": "TEST", "document_id": "original-doc", "source_kind": "filing"},
            1,
        )
        assert isinstance(assets, Mapping) and isinstance(assets["assets"], list)
        asset = next(
            cast(Mapping[str, JsonValue], a)["asset"]
            for a in assets["assets"]
            if isinstance(a, Mapping) and isinstance(a["asset"], Mapping) and a["asset"]["filename"] == "main.html"
        )
        assert isinstance(asset, Mapping)
        select: dict[str, JsonValue] = {
            "ticker": "TEST",
            "document_id": "original-doc",
            "source_kind": "filing",
            "filename": "main.html",
            "expected_sha256": asset["sha256"],
        }
        structure = await _execute(handle, context, "read_original_structure", {**select, "max_nodes": 3}, 2)
        assert isinstance(structure, Mapping)
        nodes = structure["nodes"]
        assert isinstance(nodes, Mapping) and nodes["truncated"] is True
        visible, fetch = nodes["value"], nodes["fetch_more"]
        assert isinstance(visible, list) and isinstance(fetch, Mapping)
        remaining = await _execute(
            handle, context, "fetch_more", {"cursor": fetch["cursor"], "scope_token": fetch["scope_token"]}, 3
        )
        assert isinstance(remaining, list)
        complete_nodes = visible + remaining
        expected = reader.read_original_structure(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename="main.html",
            expected_sha256=str(asset["sha256"]),
            max_nodes=3,
        )
        assert complete_nodes == expected["nodes"]
        assert structure["truncated"] is True and structure["next_start"] == expected["next_start"]
        root = complete_nodes[0]
        assert isinstance(root, Mapping) and isinstance(root["attributes"], list)
        uri = next(
            a["value"]["preview"]
            for a in root["attributes"]
            if isinstance(a, Mapping) and a["name"] == "xmlns:c" and isinstance(a["value"], Mapping)
        )
        assert isinstance(uri, str)
        facts = await _execute(
            handle,
            context,
            "query_original_facts",
            {
                **select,
                "concepts": [
                    {"namespace_uri": uri, "local_name": "Flag"},
                    {"namespace_uri": uri, "local_name": "Symbol"},
                ],
                "limit": 2,
            },
            4,
        )
        assert isinstance(facts, Mapping)
        wrapped = facts["facts"]
        assert isinstance(wrapped, Mapping) and wrapped["truncated"] is True
        first, fetch = wrapped["value"], wrapped["fetch_more"]
        assert isinstance(first, list) and isinstance(fetch, Mapping)
        rest = await _execute(
            handle, context, "fetch_more", {"cursor": fetch["cursor"], "scope_token": fetch["scope_token"]}, 5
        )
        assert isinstance(rest, list) and len(first + rest) == 2
        assert facts["truncated"] is False and facts["next_offset"] is None
        expected_facts = reader.query_original_facts(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename="main.html",
            expected_sha256=str(asset["sha256"]),
            concepts=[{"namespace_uri": uri, "local_name": "Flag"}, {"namespace_uri": uri, "local_name": "Symbol"}],
            limit=2,
        )
        assert first + rest == expected_facts["facts"]
        target = tmp_path / "host-structure-facts-receipt.json"
        target.write_text(json.dumps([assets, structure, remaining, facts, rest], ensure_ascii=False, indent=2))
        print(f"完整结构/facts 联合回执：{target}")
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_facts_fetch_more_then_next_offset_has_no_lost_occurrences(tmp_path: Path) -> None:
    """参数：真实 Fs 根。返回：无。异常：进程工具页内取齐/跨页拼接的 occurrence 丢失、重复或顺序改变。"""
    occurrence = '<z:nonNumeric name="c:Flag" contextRef="C" target="alternate" continuedAt="tail">SAME</z:nonNumeric>'
    text = HTML.replace("</body>", occurrence * 5 + "</body>")
    publish_original(tmp_path, text)
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    receipt: list[JsonValue] = []
    try:
        reader = runtime.get_read_runtime()
        asset = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)[
            "assets"
        ][0]["asset"]
        definitions = build_fins_read_tool_definitions(reader, tmp_path, FinsToolLimits(original_facts_display_items=1))
        handle, _ = _tool_runtime(ToolBundle(definitions=definitions), (_source_ref(),))
        context = _context()
        select: dict[str, JsonValue] = {
            "ticker": "TEST",
            "document_id": "original-doc",
            "source_kind": "filing",
            "filename": "main.html",
            "expected_sha256": asset["sha256"],
            "concepts": [{"namespace_uri": "urn:concept", "local_name": "Flag"}],
        }
        joined: list[JsonValue] = []
        offset, ordinal = 0, 0
        while True:
            ordinal += 1
            page = await _execute(
                handle, context, "query_original_facts", {**select, "offset": offset, "limit": 2}, ordinal
            )
            assert isinstance(page, Mapping) and page["asset"] == asset and page["parse_status"] == "complete"
            receipt.append(page)
            wrapped = page["facts"]
            assert isinstance(wrapped, Mapping) and wrapped["truncated"] is True
            visible, fetch = wrapped["value"], wrapped["fetch_more"]
            assert isinstance(visible, list) and isinstance(fetch, Mapping)
            ordinal += 1
            rest = await _execute(
                handle, context, "fetch_more", {"cursor": fetch["cursor"], "scope_token": fetch["scope_token"]}, ordinal
            )
            assert isinstance(rest, list)
            receipt.append(rest)
            full_page = visible + rest
            assert len(full_page) == 2
            joined.extend(full_page)
            if page["next_offset"] is None:
                assert page["truncated"] is False
                break
            assert page["truncated"] is True and page["next_offset"] == offset + len(full_page)
            offset += len(full_page)
        expected = reader.query_original_facts(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename="main.html",
            expected_sha256=asset["sha256"],
            concepts=[{"namespace_uri": "urn:concept", "local_name": "Flag"}],
        )
        assert joined == expected["facts"] and len(joined) == expected["total_matches"] == 6
        starts: list[int] = []
        for fact in joined:
            assert isinstance(fact, Mapping) and isinstance(fact["node"], Mapping)
            opening = fact["node"]["opening"]
            assert isinstance(opening, Mapping)
            position = opening["start"]
            assert isinstance(position, int)
            starts.append(position)
        assert len(set(starts)) == 6 and starts == sorted(starts)
        target = tmp_path / "host-facts-paging-receipt.json"
        target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
        print(f"完整 facts 分页联合回执：{target}")
    finally:
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,missing",
    [
        ("list_document_assets", "document"),
        ("read_original_text", "document"),
        ("read_original_structure", "document"),
        ("query_original_facts", "document"),
        ("read_original_text", "asset"),
        ("read_original_structure", "asset"),
        ("query_original_facts", "asset"),
    ],
)
async def test_process_original_missing_resources_keep_typed_code_and_hint(
    tmp_path: Path, tool_name: str, missing: str
) -> None:
    """参数：真实 Fs 根、工具和缺失维度。返回：无。异常：真实进程/Host 投影丢失 typed not_found 与恢复步骤。"""
    publish_original(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    try:
        definitions = build_fins_read_tool_definitions(runtime.get_read_runtime(), tmp_path, FinsToolLimits())
        handle, _ = _tool_runtime(ToolBundle(definitions=definitions), (_source_ref(),))
        arguments: dict[str, JsonValue] = {
            "ticker": "TEST",
            "document_id": "absent-doc" if missing == "document" else "original-doc",
            "source_kind": "filing",
        }
        if tool_name != "list_document_assets":
            arguments.update(filename="absent.html" if missing == "asset" else "main.html", expected_sha256="a" * 64)
        if tool_name == "query_original_facts":
            arguments["concepts"] = [{"namespace_uri": "urn:concept", "local_name": "Flag"}]
        response = await handle.tool_executor.execute(
            BatchToolExecutionRequest(calls=(_call(tool_name, arguments, 0),), context=_context())
        )
        failure = response.records[0].outcome
        assert isinstance(failure, ToolFailedOutcome)
        assert failure.result.error == "not_found"
        assert (
            failure.result.hint
            and "list_document_assets" in failure.result.hint
            and "source_kind" in failure.result.hint
        )
        assert "table_ref" not in failure.result.hint
    finally:
        runtime.close()
