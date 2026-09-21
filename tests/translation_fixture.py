"""Plain-text protocol fixture. Never used as evidence of translation quality."""

import re

from coworker.providers.base import AssistantTurn, TokenUsage


def source_from_prompt(prompt):
    if "完整译文：\n" in prompt:
        return prompt.split("完整译文：\n", 1)[1]
    # Upstream repeats the target in multichunk prompts; choose the last explicit
    # target, not the instructional mention of an XML tag in the introduction.
    targets = re.findall(r"<TRANSLATE_THIS>\n(.*?)\n</TRANSLATE_THIS>", prompt, re.S)
    if targets:
        return targets[-1]
    sources = re.findall(r"<SOURCE_TEXT>\n(.*?)\n</SOURCE_TEXT>", prompt, re.S)
    if sources:
        return sources[-1]
    match = re.search(r"\n[^:\n]+: (.*)\n\n[^:\n]+:$", prompt, re.S)
    if match:
        return match[1]
    raise AssertionError("Unexpected upstream prompt")


class EchoModel:
    def __init__(self):
        self.calls = []
        self.fail_at = None
        self.error = TimeoutError()
        self.truncate_at = None
        self.usage = TokenUsage(input=100, output=100)

    def __call__(self, model, messages, **kwargs):
        self.calls.append((model, messages, kwargs))
        n = len(self.calls)
        if n == self.fail_at:
            raise self.error
        return AssistantTurn(
            text=source_from_prompt(messages[-1]["content"]),
            finish_reason="length" if n == self.truncate_at else "stop",
            usage=self.usage,
        )
