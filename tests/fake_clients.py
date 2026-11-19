"""Fake SDK clients for tests. They record their kwargs and never touch the network."""

from types import SimpleNamespace
from typing import Any

from natter.schema import Dossier


def claude_response(text: str | None, stop_reason: str = "end_turn") -> SimpleNamespace:
    """Shape of an anthropic Message: stop_reason plus a list of content blocks."""
    content = [] if text is None else [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(stop_reason=stop_reason, content=content)


def groq_response(text: str | None, finish_reason: str = "stop") -> SimpleNamespace:
    """Shape of a Groq chat completion: choices[0].message.content plus finish_reason."""
    message = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


class FakeFactory:
    """Stands in for anthropic.Anthropic / groq.Groq. Records how it was called."""

    def __init__(self, kind: str, reply: Any = None) -> None:
        self.factory_kwargs: dict[str, Any] = {}  # what the provider passed to the SDK client
        self.create_calls: list[dict[str, Any]] = []  # what the provider passed to create()
        if reply is None:
            reply = (
                claude_response(Dossier().model_dump_json())
                if kind == "claude"
                else groq_response("Oh hello dear, hold on a moment.")
            )
        self.reply = reply
        create = SimpleNamespace(create=self._create)
        self.client = (
            SimpleNamespace(messages=create)
            if kind == "claude"
            else SimpleNamespace(chat=SimpleNamespace(completions=create))
        )

    def _create(self, **kwargs: Any) -> Any:
        self.create_calls.append(kwargs)
        return self.reply

    def __call__(self, **kwargs: Any) -> Any:
        self.factory_kwargs = kwargs
        return self.client
