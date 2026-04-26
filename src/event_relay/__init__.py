"""Event relay package — MySQL ingest, analysis pipeline, HTTP service.

Public surface intentionally narrow: callers import ``config``,
``http_server``, and ``service``. Other submodules (analysis_stages,
bls_macro, tw_close_context, …) are imported by name where needed."""

# Event relay package exports.
__all__ = [
    "config",
    "http_server",
    "service",
]
