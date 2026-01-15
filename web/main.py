from fastapi import FastAPI
from web.api.hello import router as hello_router

app = FastAPI(
    title="NSE Analytics API",
    description="Web-based analytics API (JSON only)",
    version="0.1.0"
)

app.include_router(hello_router, prefix="/api")

@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "NSE Analytics API is running"
    }
