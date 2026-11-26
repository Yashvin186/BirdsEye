from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.api import health, capabilities, projects, jobs, files
from app.core.environment import check_colmap, check_colmap_dense_capable

app = FastAPI(
    title="Birds Eye 3D Reconstruction API",
    description="Photogrammetry and 3D terrain reconstruction from single-pass continuous drone videos",
    version="1.0.0"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow frontend client in local development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(health.router)
app.include_router(capabilities.router)
app.include_router(projects.router)
app.include_router(jobs.router)
app.include_router(files.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": str(exc),
                "type": type(exc).__name__
            }
        }
    )


@app.on_event("startup")
def on_startup():
    colmap_info = check_colmap()
    dense_ok, dense_reason = check_colmap_dense_capable()
    print("=" * 60)
    print("Birds Eye Backend Initialized")
    print(f"COLMAP Exe: {colmap_info.path}")
    print(f"COLMAP Version: {colmap_info.version}")
    print(f"Dense MVS Status: {'ENABLED (CUDA)' if dense_ok else 'UNSUPPORTED: ' + dense_reason}")
    print("=" * 60)


@app.get("/")
def root():
    return {
        "service": "Birds Eye 3D Reconstruction System",
        "docs": "/docs",
        "health": "/api/health",
        "capabilities": "/api/capabilities"
    }
