"""Fixed registry for Creation Engine tools; no arbitrary execute tool exists."""

from virgo.contracts.errors import ToolExecutionError
from virgo.contracts.models import RegisteredTool


class CreationToolRegistry:
    def __init__(self) -> None:
        self._tools = {
            "inspect_file": _tool(
                "inspect_file",
                "Read bounded metadata or UTF-8 text inside a workspace",
                "read_only",
                "read_only",
                False,
            ),
            "create_text_file": _tool(
                "create_text_file",
                "Create one approved workspace-contained text file",
                "explicit",
                "reversible_write",
                True,
            ),
            "edit_text_file": _tool(
                "edit_text_file",
                "Replace one approved workspace-contained text file",
                "explicit",
                "reversible_write",
                True,
            ),
            "delete_text_file": _tool(
                "delete_text_file",
                "Delete one explicitly approved file after backup",
                "explicit",
                "high_impact",
                True,
            ),
            "validate_output": _tool(
                "validate_output",
                "Run deterministic in-process output validation",
                "read_only",
                "read_only",
                False,
            ),
            "run_validation_test": _tool(
                "run_validation_test",
                "Run one allowlisted executable with separated arguments",
                "task_scope",
                "read_only",
                False,
            ),
        }

    @property
    def tools(self) -> tuple[RegisteredTool, ...]:
        return tuple(self._tools.values())

    def require(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError as error:
            raise ToolExecutionError(
                "Creation tool is not registered", source_module=__name__, cause=error
            ) from error


def _tool(
    name: str,
    description: str,
    permission_level: str,
    risk_level: str,
    rollback_supported: bool,
) -> RegisteredTool:
    return RegisteredTool(
        name=name,
        description=description,
        permission_level=permission_level,
        risk_level=risk_level,
        timeout_seconds=30.0,
        cancellation_supported=True,
        validation="Typed input and workspace scope validation",
        audit_logged=True,
        rollback_supported=rollback_supported,
    )
