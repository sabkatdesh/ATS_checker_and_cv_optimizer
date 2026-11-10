from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.middleware import RequestIdMiddleware
from app.api.routers import (
    billing,
    cover_letters,
    health,
    profiles,
    sessions,
    templates,
    user_settings,
)
from app.container import Container, build_container
from app.observability.logging import configure_logging
from app.observability.sentry import init_sentry


def create_app(container: Container | None = None) -> FastAPI:
    container = container or build_container()
    configure_logging(container.settings.obs)
    init_sentry(container.settings)
    app = FastAPI(title="CV Optimizer API")
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.api.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIdMiddleware)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(profiles.router)
    app.include_router(templates.router)
    app.include_router(user_settings.router)
    app.include_router(billing.router)
    app.include_router(sessions.router)
    app.include_router(cover_letters.router)
    if container.settings.dev_tools_enabled:
        app.include_router(billing.dev_router)
    return app


app = create_app()
