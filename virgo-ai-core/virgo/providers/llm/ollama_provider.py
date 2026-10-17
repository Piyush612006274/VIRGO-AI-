"""Loopback-only Ollama-compatible local language-model provider."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from threading import Event
from typing import NoReturn, Protocol, cast
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from virgo.contracts.errors import (
    ModelUnavailableError,
    OperationTimeoutError,
    ProviderUnavailableError,
    ValidationError,
)
from virgo.contracts.models import LLMRequest, LLMResponse, LLMStreamChunk

DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60.0
OLLAMA_PROVIDER_NAME = "ollama"
LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


class OllamaTransportProtocol(Protocol):
    """Small injectable HTTP boundary used by the local provider."""

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None,
        timeout_seconds: float,
    ) -> Iterator[bytes]: ...

    def close(self) -> None: ...


class UrllibOllamaTransport:
    """Instance-owned standard-library HTTP transport."""

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None,
        timeout_seconds: float,
    ) -> Iterator[bytes]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self._endpoint}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            yield from response

    def close(self) -> None:
        """No persistent standard-library connection is retained."""


class OllamaLLMProvider:
    """Synchronous provider for one explicit loopback Ollama endpoint."""

    provider_name = OLLAMA_PROVIDER_NAME

    def __init__(
        self,
        *,
        endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
        timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        transport: OllamaTransportProtocol | None = None,
    ) -> None:
        _validate_local_endpoint(endpoint)
        if (
            not isinstance(timeout_seconds, int | float)
            or not 0 < timeout_seconds <= 600
        ):
            raise ValidationError(
                "timeout_seconds must be between zero and 600",
                source_module=__name__,
            )
        self._endpoint = endpoint.rstrip("/")
        self._timeout_seconds = float(timeout_seconds)
        self._transport = transport or UrllibOllamaTransport(self._endpoint)
        self._closed = False

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def health_check(self) -> bool:
        response = self._request_json("GET", "/api/version")
        if not isinstance(response.get("version"), str) or not response["version"]:
            raise self._provider_error("Ollama returned an invalid version response")
        return True

    def list_models(self) -> tuple[str, ...]:
        response = self._request_json("GET", "/api/tags")
        models = response.get("models")
        if not isinstance(models, list):
            raise self._provider_error("Ollama returned an invalid model list")
        names: list[str] = []
        for model in models:
            if not isinstance(model, dict) or not isinstance(model.get("name"), str):
                raise self._provider_error("Ollama returned invalid model metadata")
            names.append(cast(str, model["name"]))
        return tuple(names)

    def generate(self, request: LLMRequest) -> LLMResponse:
        self._validate_request(request)
        self._require_model(request.model)
        response = self._request_json(
            "POST",
            "/api/generate",
            _generation_payload(request, stream=False),
        )
        try:
            return LLMResponse(
                text=_required_string(response, "response"),
                model=_required_string(response, "model"),
                provider=OLLAMA_PROVIDER_NAME,
                completed=_required_bool(response, "done"),
                generation_duration_seconds=_optional_duration(response),
                prompt_token_count=_optional_count(response, "prompt_eval_count"),
                completion_token_count=_optional_count(response, "eval_count"),
                correlation_id=request.correlation_id,
            )
        except ValueError as error:
            raise self._provider_error(
                "Ollama returned an invalid generation response", error
            ) from error

    def stream(
        self,
        request: LLMRequest,
        cancellation: Event | None = None,
    ) -> Iterator[LLMStreamChunk]:
        self._validate_request(request)
        self._require_model(request.model)
        if cancellation is not None and cancellation.is_set():
            raise self._cancelled_error(request)
        completed = False
        try:
            lines = self._transport.request(
                "POST",
                "/api/generate",
                _generation_payload(request, stream=True),
                self._timeout_seconds,
            )
            for line in lines:
                if cancellation is not None and cancellation.is_set():
                    raise self._cancelled_error(request)
                response = _decode_json(line)
                chunk = LLMStreamChunk(
                    text_delta=_required_string(response, "response", allow_empty=True),
                    done=_required_bool(response, "done"),
                    model=_required_string(response, "model"),
                    correlation_id=request.correlation_id,
                )
                completed = chunk.done
                yield chunk
            if not completed:
                raise self._provider_error("Ollama stream ended without completion")
        except (ValidationError, ProviderUnavailableError, OperationTimeoutError):
            raise
        except TimeoutError as error:
            raise self._timeout_error(error) from error
        except URLError as error:
            self._raise_url_error(error)
        except Exception as error:
            raise self._provider_error("Ollama streaming failed", error) from error

    def close(self) -> None:
        if self._closed:
            return
        self._transport.close()
        self._closed = True

    def _validate_request(self, request: LLMRequest) -> None:
        self._ensure_open()
        if not isinstance(request, LLMRequest):
            raise ValidationError(
                "Generation requires an LLMRequest",
                source_module=__name__,
            )

    def _require_model(self, model: str) -> None:
        if model not in self.list_models():
            raise ModelUnavailableError(
                "Selected local model is not installed",
                technical_detail=f"Unavailable Ollama model: {model}",
                source_module=__name__,
            )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        self._ensure_open()
        try:
            lines = self._transport.request(
                method,
                path,
                payload,
                self._timeout_seconds,
            )
            return _decode_json(b"".join(lines))
        except (ProviderUnavailableError, OperationTimeoutError):
            raise
        except TimeoutError as error:
            raise self._timeout_error(error) from error
        except URLError as error:
            self._raise_url_error(error)
        except Exception as error:
            raise self._provider_error("Ollama request failed", error) from error

    def _ensure_open(self) -> None:
        if self._closed:
            raise ProviderUnavailableError(
                "Ollama provider is closed",
                source_module=__name__,
            )

    @staticmethod
    def _timeout_error(error: BaseException) -> OperationTimeoutError:
        return OperationTimeoutError(
            "Ollama request timed out",
            technical_detail=f"{type(error).__name__}: {error}",
            source_module=__name__,
            cause=error,
        )

    @staticmethod
    def _provider_error(
        message: str,
        error: BaseException | None = None,
    ) -> ProviderUnavailableError:
        return ProviderUnavailableError(
            message,
            technical_detail=(
                f"{type(error).__name__}: {error}" if error is not None else None
            ),
            source_module=__name__,
            cause=error,
        )

    @staticmethod
    def _cancelled_error(request: LLMRequest) -> ValidationError:
        return ValidationError(
            "Local generation was cancelled",
            source_module=__name__,
            correlation_id=request.correlation_id,
        )

    def _raise_url_error(self, error: URLError) -> NoReturn:
        if isinstance(error.reason, TimeoutError):
            raise self._timeout_error(error) from error
        raise self._provider_error("Ollama is unavailable", error) from error


def _validate_local_endpoint(endpoint: str) -> None:
    try:
        parsed = urlparse(endpoint)
        valid_port = parsed.port is not None
    except (TypeError, ValueError):
        valid_port = False
        parsed = urlparse("")
    if (
        not isinstance(endpoint, str)
        or parsed.scheme != "http"
        or parsed.hostname not in LOCAL_HOSTS
        or not valid_port
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValidationError(
            "Ollama endpoint must be an explicit loopback HTTP address",
            source_module=__name__,
        )


def _generation_payload(request: LLMRequest, *, stream: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "model": request.model,
        "prompt": request.prompt,
        "stream": stream,
        "options": {"temperature": float(request.temperature)},
    }
    if request.system_instruction is not None:
        payload["system"] = request.system_instruction
    if request.max_tokens is not None:
        cast(dict[str, object], payload["options"])["num_predict"] = request.max_tokens
    return payload


def _decode_json(content: bytes) -> dict[str, object]:
    decoded = json.loads(content)
    if not isinstance(decoded, dict):
        raise ValueError("response must be a JSON object")
    return cast(dict[str, object], decoded)


def _required_string(
    response: Mapping[str, object],
    key: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = response.get(key)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_bool(response: Mapping[str, object], key: str) -> bool:
    value = response.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _optional_count(response: Mapping[str, object], key: str) -> int | None:
    value = response.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _optional_duration(response: Mapping[str, object]) -> float | None:
    value = response.get("total_duration")
    if value is None:
        return None
    if not isinstance(value, int) or value < 0:
        raise ValueError("total_duration must be non-negative nanoseconds")
    return value / 1_000_000_000
