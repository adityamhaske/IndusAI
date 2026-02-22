from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.api import routes_logs, routes_history, routes_project
from app.api.routes_fault import router as fault_router
from app.api.routes_system import router as system_router
from app.api.routes_project_knowledge import router as project_knowledge_router
from app.api.routes_knowledge import router as knowledge_router
from app.api.routes_ingest_upload import router as ingest_upload_router
from app.api import routes_ai
from app.config.settings import settings
import os

app = FastAPI(title="Industrial AI Assistant", debug=settings.DEBUG)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(routes_logs.router, prefix="/api/system", tags=["Logs"])
app.include_router(routes_history.router, prefix="/api", tags=["History"])
app.include_router(routes_project.router, prefix="/api", tags=["Projects"])
app.include_router(fault_router, prefix="/api", tags=["PLC Faults"])
app.include_router(system_router, prefix="/api/system", tags=["System"])
app.include_router(project_knowledge_router, prefix="/api", tags=["Project Knowledge"])
app.include_router(knowledge_router, prefix="/api", tags=["Knowledge"])
app.include_router(ingest_upload_router, prefix="/api", tags=["Ingest Upload"])
app.include_router(routes_ai.router, prefix="/api/ai", tags=["AI Gateway"])

@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Industrial AI Assistant"}

# Serve Frontend
# Get the project root directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "client", "dist")

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    # Fallback to old frontend or just a warning
    OLD_FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
    if os.path.exists(OLD_FRONTEND_DIR):
        app.mount("/", StaticFiles(directory=OLD_FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
