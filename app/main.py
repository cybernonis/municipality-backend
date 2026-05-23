from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import departments, auth, reports, ai

app = FastAPI(
    title="Municipality Reports API",
    description="Smart Municipality Issue Reporting System — Ηράκλειο",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,        prefix="/auth",        tags=["Auth"])
app.include_router(reports.router,     prefix="/reports",     tags=["Reports"])
app.include_router(ai.router,          prefix="/ai",          tags=["AI"])
app.include_router(departments.router, prefix="/departments", tags=["Departments"])

@app.get("/")
def root():
    return {
        "message": "Municipality Reports API",
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)