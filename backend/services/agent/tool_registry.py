"""Tool catalog lookup and runtime dispatch for Agentic RAG."""

from typing import Any, Callable

from sqlalchemy.orm import Session

from backend.services.retrieval.search_service import RetrievalSearchService
from backend.services.agent.tool_catalog import get_tool_definitions
from backend.services.agent.tool_definitions import (
    ToolCategory,  # Re-exported for compatibility with legacy registry imports.
    ToolDefinition,
    ToolExecutionResult,
    ToolParameter,  # Re-exported for compatibility with legacy registry imports.
)
from backend.services.agent.tool_executor import AgentToolExecutor
from backend.repositories.retrieval_repository import MeetingChunkRepository


class AgentToolRegistry:
    """Expose tool contracts and dispatch calls to their runtime executor."""

    def __init__(
        self,
        session: Session,
        retrieval_search: RetrievalSearchService | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory
        self.chunks = MeetingChunkRepository(session)
        self.retrieval_search = retrieval_search or RetrievalSearchService(session)
        self.executor = AgentToolExecutor(
            chunks=self.chunks,
            retrieval_search=self.retrieval_search,
        )

    def execute_tool_scoped(self, **kwargs: Any) -> ToolExecutionResult:
        """Execute one tool with a session owned by the calling thread."""
        if self.session_factory is None:
            return self.execute_tool(**kwargs)
        with self.session_factory() as session:
            registry = AgentToolRegistry(session=session)
            return registry.execute_tool(**kwargs)

    def get_tools(self) -> list[dict[str, Any]]:
        """Return tool definitions in the LLM function-calling format."""
        return [self._tool_to_dict(definition) for definition in self._get_all_definitions()]

    def get_tool_by_name(self, name: str) -> ToolDefinition | None:
        """Return a tool contract by name, or ``None`` when unknown."""
        return next(
            (definition for definition in self._get_all_definitions() if definition.name == name),
            None,
        )

    def execute_tool(
        self,
        *,
        meeting_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolExecutionResult:
        """Validate and dispatch one tool call while normalizing failures."""
        definition = self.get_tool_by_name(tool_name)
        if definition is None:
            valid_tools = ", ".join(d.name for d in self._get_all_definitions())
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: '{tool_name}'. Valid tools are: {valid_tools}",
            )

        # Keep runtime overrides/mocks assigned on the registry authoritative.
        self.executor.chunks = self.chunks
        self.executor.retrieval_search = self.retrieval_search
        executors = {
            "search_semantic": lambda: self.executor.search_semantic(
                meeting_id=meeting_id,
                arguments=arguments,
            ),
            "search_keyword": lambda: self.executor.search_keyword(
                meeting_id=meeting_id, arguments=arguments
            ),
            "search_records": lambda: self.executor.search_records(
                meeting_id=meeting_id, arguments=arguments
            ),
            "search_section": lambda: self.executor.search_section(
                meeting_id=meeting_id, arguments=arguments
            ),
            "get_summary": lambda: self.executor.get_summary(
                meeting_id=meeting_id, arguments=arguments
            ),
        }

        executor = executors.get(tool_name)
        if executor is None:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool '{tool_name}' is defined but has no executor.",
            )

        try:
            return executor()
        except Exception as exc:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                error=f"Error executing tool '{tool_name}': {str(exc)}",
            )

    def _get_all_definitions(self) -> list[ToolDefinition]:
        return get_tool_definitions()

    @staticmethod
    def _tool_to_dict(definition: ToolDefinition) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in definition.parameters:
            param_def: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.type == "array":
                param_def["items"] = {"type": "string"}
            if param.enum:
                param_def["enum"] = param.enum
            if param.default is not None:
                param_def["default"] = param.default
            properties[param.name] = param_def
            if param.required:
                required.append(param.name)

        parameters: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            parameters["required"] = required

        return {
            "type": "function",
            "function": {
                "name": definition.name,
                "description": definition.description,
                "parameters": parameters,
            },
        }


def create_tool_registry(
    session: Session,
    retrieval_search: RetrievalSearchService | None = None,
) -> AgentToolRegistry:
    """Create an AgentToolRegistry with the supplied database dependencies."""
    return AgentToolRegistry(session=session, retrieval_search=retrieval_search)
