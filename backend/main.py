from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from routes.admin import admin_router
from Database.Database import engine, Base
from routes.auth import router as auth_router
from routes.auth import login_router
from routes.upload import router as upload_router
from routes.dashboard import router as dashboard_router
import os, sys, io

# ── Force UTF-8 encoding for stdout/stderr on Windows ──────────────────────
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── Create all tables on startup ──────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

from sqlalchemy import text
try:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE sales_data ADD COLUMN upload_date DATE"))
except Exception:
    pass

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "RetailPulse API",
    description = "Backend for RetailPulse — Supermarket Analytics Platform",
    version     = "1.0.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(login_router)
app.include_router(upload_router)
app.include_router(dashboard_router)
app.include_router(admin_router)

# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def home():
    return {
        "status":  "running",
        "message": "RetailPulse Backend is live 🚀",
        "docs":    "/docs"
    }

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}

# ── Frontend ──────────────────────────────────────────────────────────────────
@app.get("/app")
def serve_frontend():
    file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html")
    return FileResponse(file_path)
