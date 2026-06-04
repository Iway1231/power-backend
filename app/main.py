from fastapi import FastAPI
from app.api import router

print("🔥 MAIN.PY LOADED 🔥")

app = FastAPI(
    title="Power Schedule API",
    version="1.0.0"
)

app.include_router(router)
