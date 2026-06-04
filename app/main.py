from fastapi import FastAPI
from app.api import router

print("MAIN.PY LOADED")

app = FastAPI(
    title="Power Schedule API",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "message": "Power Schedule API is running",
        "status_url": "/status",
        "docs_url": "/docs",
    }


app.include_router(router)
