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


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"Starting {settings.PROJECT_NAME} backend service...")
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
