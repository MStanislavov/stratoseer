import logging
import os
import uvicorn
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import profiles, runs, audit, results, cover_letters, policies, auth, admin
from app.auth.rate_limit import limiter
from app.config import settings as _settings
from app.db import engine, Base
from app.services.run_service import recover_orphaned_runs

# Import all models so Base.metadata knows about them
from app import models  # noqa: F401

# LangSmith tracing
if _settings.langsmith_tracing and _settings.langsmith_api_key:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = _settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = _settings.langsmith_project
else:
    os.environ.pop("LANGCHAIN_TRACING_V2", None)

# Configure logging from settings
_log_level = getattr(logging, _settings.log_level.upper(), logging.INFO)
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s:%(name)s:%(message)s",
)
# Let app loggers use the configured level; keep third-party libs at WARNING
logging.getLogger("app").setLevel(_log_level)


async def _ensure_admin():
    """Promote the configured admin_email user to admin role on startup."""
    if not _settings.admin_email:
        return
    from sqlalchemy import select, update
    from app.models.user import User
    from app.db import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == _settings.admin_email)
        )
        user = result.scalar_one_or_none()
        if user:
            if user.role != "admin":
                await session.execute(
                    update(User)
                    .where(User.email == _settings.admin_email)
                    .values(role="admin")
                )
                await session.commit()
                logging.getLogger("app").info("Promoted %s to admin", _settings.admin_email)
        else:
            session.add(User(
                email=_settings.admin_email,
                first_name="Admin",
                last_name="",
                role="admin",
                email_verified=True,
            ))
            await session.commit()
            logging.getLogger("app").info("Created admin user %s", _settings.admin_email)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create database tables on startup, then yield to the application."""
    # Create tables on startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _ensure_admin()
    await recover_orphaned_runs()
    yield


app = FastAPI(title="AI Executive Assistant Network", lifespan=lifespan)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        _settings.app_base_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
spa_dir = Path(__file__).parent.parent / "static" / "spa"
spa_assets = spa_dir / "assets"

# Mount SPA assets (JS/CSS bundles)
if spa_assets.is_dir():
    app.mount("/assets", StaticFiles(directory=str(spa_assets)), name="spa-assets")

# JSON API routers (registered BEFORE the SPA catch-all)
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(profiles.router, prefix="/api")
app.include_router(runs.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(cover_letters.router, prefix="/api")
app.include_router(policies.router, prefix="/api")


# SPA catch-all: serve static files if they exist, otherwise index.html
@app.get("/{full_path:path}")
async def spa_catch_all(full_path: str):
    """Serve SPA static files or fall back to index.html for client-side routing."""
    # Serve static files (e.g. favicon.svg) directly if present
    if full_path:
        static_file = spa_dir / full_path
        if static_file.is_file() and spa_dir in static_file.resolve().parents:
            return FileResponse(str(static_file))
    index = spa_dir / "index.html"
    if not index.is_file():
        return JSONResponse(
            status_code=404,
            content={"detail": "SPA not built. Run: cd frontend && npm run build"},
        )
    return FileResponse(str(index))


if __name__ == "__main__":
    import asyncio

    config = uvicorn.Config(
        "app.main:app",
        host=_settings.app_host,
        port=_settings.app_port,
    )
    asyncio.run(uvicorn.Server(config).serve())