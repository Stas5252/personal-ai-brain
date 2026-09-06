"""
FastAPI Application for Personal AI Brain Service.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.brain.api.routes.brain_routes import router as brain_router
from src.brain.api.routes.openai_routes import router as openai_router

app = FastAPI(
    title="Personal AI Brain API",
    description="Central Intelligence Layer for Photographer/Creator AI Assistant",
    version="2.0.0"
)

# Enable CORS for local web interfaces and development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(brain_router)
app.include_router(openai_router)

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "Personal AI Brain",
        "version": "2.0.0"
    }
