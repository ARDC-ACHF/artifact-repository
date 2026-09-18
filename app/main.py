"""FastAPI application entrypoint.

Run locally with::

    uvicorn app.main:app --reload
"""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__


def create_app() -> FastAPI:
    app = FastAPI(
        title="Linked Art Interoperability Repository",
        version=__version__,
        description=(
            "API foundation for a Linked Art interoperability repository. "
            "Artifact publication, validation and search are not implemented yet."
        ),
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        """Report application liveness, not storage or index readiness."""
        return {"status": "ok"}

    return app


app = create_app()