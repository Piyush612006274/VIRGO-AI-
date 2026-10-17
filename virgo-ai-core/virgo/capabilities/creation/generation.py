"""Reuse the existing LLM provider for untrusted typed file proposals."""

import json

from virgo.application.conversation import build_virgo_system_instruction
from virgo.contracts.errors import ValidationError
from virgo.contracts.models import GeneratedFileProposal, LLMRequest, new_correlation_id
from virgo.contracts.models.creation import CreationAction, CreationOperation
from virgo.contracts.protocols import CreationLLMProviderProtocol


class CreationGenerator:
    def __init__(self, provider: CreationLLMProviderProtocol) -> None:
        self._provider = provider

    def propose(
        self,
        operation: CreationOperation,
        *,
        intent: str,
        model: str,
        existing_content: str | None = None,
    ) -> GeneratedFileProposal:
        if operation.action not in (CreationAction.CREATE, CreationAction.UPDATE):
            raise ValidationError(
                "Creation generation requires a file write operation",
                source_module=__name__,
            )
        prompt = (
            "Return exactly one JSON object with keys target and proposed_content. "
            "Do not include markdown fences or commands.\n"
            f"Approved target: {operation.target}\n"
            f"User intent: {intent}\n"
            f"Existing content: {existing_content if existing_content is not None else '[new file]'}"
        )
        response = self._provider.generate(
            LLMRequest(
                prompt=prompt,
                model=model,
                system_instruction=build_virgo_system_instruction(
                    model,
                    "You create untrusted file-content proposals. Never claim permission, "
                    "execute commands, or change the approved target.",
                ),
                temperature=0.2,
                correlation_id=new_correlation_id(),
            )
        )
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as error:
            raise ValidationError(
                "Local model returned an invalid creation proposal",
                technical_detail=str(error),
                source_module=__name__,
                cause=error,
            ) from error
        if not isinstance(payload, dict) or payload.get("target") != operation.target:
            raise ValidationError(
                "Generated proposal changed the approved target", source_module=__name__
            )
        content = payload.get("proposed_content")
        if not isinstance(content, str):
            raise ValidationError(
                "Generated proposal content is invalid", source_module=__name__
            )
        return GeneratedFileProposal(
            operation=operation,
            proposed_content=content,
            provider_name=response.provider,
            model_name=response.model,
            validated=False,
        )
