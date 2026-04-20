"""AI provider abstraction and built-in prompts."""
from youtube_strataread.ai.base import LLMError, LLMProvider, get_provider

__all__ = ["LLMProvider", "LLMError", "get_provider"]
