from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.routers import health, legacy, templates
from app.container import Container, build_container


def create_app(container: Container | None = None) -> FastAPI:
    container = container or build_container()
    app = FastAPI(title="CV Optimizer API")
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.api.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(templates.router)
    app.include_router(legacy.router)
    return app


app = create_app()
