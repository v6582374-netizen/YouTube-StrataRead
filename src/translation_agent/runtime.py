"""Optional host binding. Upstream algorithms and standalone entry points stay intact."""
from contextlib import contextmanager
from contextvars import ContextVar

_binding = ContextVar("translation_agent_host", default=None)


@contextmanager
def bind(completion):
    token = _binding.set(completion)
    try:
        yield
    finally:
        _binding.reset(token)


def complete(function, variables, standalone, *args, **kwargs):
    host = _binding.get()
    if host is None:
        # Preserve positional/keyword conventions, including upstream mock contracts.
        return standalone(*args, **kwargs)
    return host(*args, **kwargs, function=function, variables=variables)
