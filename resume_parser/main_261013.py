"""261013 版简历解析服务入口。运行：uvicorn resume_parser.main_261013:app"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from resume_parser.config_261013 import settings_261013
from resume_parser.routers import internal_261013
from resume_parser.routers import job as job_router


app = FastAPI(title="Resume Parser Service", version="261013")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(internal_261013.router)
app.include_router(job_router.router)


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "resume_parser_version": "261013",
        "deepseek_configured": bool(settings_261013.deepseek_api_key.strip()),
        "log_actor_hash_configured": bool(
            settings_261013.resume_model_io_actor_hmac_secret.strip()
        ),
    }
