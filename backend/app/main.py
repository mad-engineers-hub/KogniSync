from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.api.routes.health import router as health_router
from app.api.routes.ai import router as ai_router
from app.api.routes.xr import router as xr_router
from app.api.routes.maps import router as maps_router
from app.api.routes.optimizer import router as optimizer_router
from app.api.routes.booking import router as booking_router
from app.api.routes.auth import router as auth_router
from app.api.routes.journeys import router as journeys_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"Starting {settings.PROJECT_NAME} backend service...")
    
    # Startup readiness gate: fail closed in production if security prerequisites are absent
    if settings.ENVIRONMENT == "production":
        if not settings.JWT_SECRET_KEY or len(settings.JWT_SECRET_KEY.strip()) < 32:
            logger.critical("Startup aborted: JWT_SECRET_KEY must be configured with >= 32 characters in production.")
            raise RuntimeError("Startup aborted: JWT_SECRET_KEY must be configured with >= 32 characters in production.")
        if not settings.INTERNAL_API_KEY or len(settings.INTERNAL_API_KEY.strip()) < 16:
            logger.critical("Startup aborted: INTERNAL_API_KEY must be configured in production.")
            raise RuntimeError("Startup aborted: INTERNAL_API_KEY must be configured in production.")

    yield
    logger.info(f"Shutting down {settings.PROJECT_NAME} backend service...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(ai_router)
app.include_router(xr_router)
app.include_router(maps_router)
app.include_router(optimizer_router)
app.include_router(booking_router)
app.include_router(auth_router)
app.include_router(journeys_router)
