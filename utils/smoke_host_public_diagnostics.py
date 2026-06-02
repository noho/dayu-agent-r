"""Host public smoke diagnostics 的共享打印 helper。"""

from __future__ import annotations

from dayu.host.api import OpenHostOptions


def print_duplicate_governance_diagnostics(options: OpenHostOptions) -> None:
    """打印 effective duplicate governance policy 摘要。

    :param options: Host opener options。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    tooling_options = options.tooling_options
    if tooling_options is None:
        print("SMOKE ASSEMBLY tool_duplicate_governance=<none>")
        return
    policy = tooling_options.duplicate_governance_policy
    per_tool = ",".join(
        f"{tool_name}:{decision.value}"
        for tool_name, decision in sorted(policy.decisions_by_tool_name.items())
    )
    justification_args = ",".join(
        f"{tool_name}:{argument_name}"
        for tool_name, argument_name in sorted(
            policy.justification_argument_names_by_tool_name.items()
        )
    )
    print(
        "SMOKE ASSEMBLY tool_duplicate_governance_default="
        f"{policy.default_duplicate_decision.value}"
    )
    print(
        "SMOKE ASSEMBLY tool_duplicate_governance_per_tool="
        f"{per_tool or '<none>'}"
    )
    print(
        "SMOKE ASSEMBLY tool_duplicate_governance_justification_args="
        f"{justification_args or '<none>'}"
    )
    print(
        "SMOKE ASSEMBLY tool_duplicate_governance_message_hint="
        f"{policy.messages.hint}"
    )
