from fastapi import FastAPI
from app.api import API_V1_PREFIX, router

print("MAIN.PY LOADED")

app = FastAPI(
    title="Power Schedule API",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "message": "Power Schedule API is running",
        "status_url": f"{API_V1_PREFIX}/status",
        "app_config_url": f"{API_V1_PREFIX}/app/config",
        "docs_url": "/docs",
    }


app.include_router(router)
app.include_router(router, prefix=API_V1_PREFIX)
