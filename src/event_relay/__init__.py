"""Event relay package for MySQL ingest, context storage, and HTTP service.

Public surface intentionally stays narrow: callers import ``config``,
``http_server``, and ``service``. Data collectors import their specific
submodules by name where needed.
"""

__all__ = [
    "config",
    "http_server",
    "service",
]
