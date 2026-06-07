from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import internal
from config import settings

app = FastAPI(title="Resume Parser Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(internal.router)

@app.get("/health")
async def health():
    return {"status": "ok"}