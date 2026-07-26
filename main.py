import os
import uvicorn
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
import shutil, uuid
from pathlib import Path

from routers import video_router, drone_router, location_router, cctv_router, tracking_router

app = FastAPI(
    title="AEGIS — AI Disaster Response System",
    description="Video analysis · CCTV suspicious detection · Drone dispatch · Mobile tracking",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="../frontend/static"), name="static")
templates = Jinja2Templates(directory="../frontend/templates")

# Routers
app.include_router(video_router.router,    prefix="/api/video",    tags=["Disaster Video"])
app.include_router(drone_router.router,    prefix="/api/drone",    tags=["Drone Fleet"])
app.include_router(location_router.router, prefix="/api/location", tags=["Location"])
app.include_router(cctv_router.router,     prefix="/api/cctv",     tags=["CCTV Analysis"])
app.include_router(tracking_router.router, prefix="/api/tracking", tags=["Mobile Tracking"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "online", "version": "2.0.0", "features": ["video", "cctv", "drone", "tracking"]}

@app.post("/api/upload")
async def upload_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Only video files are accepted")
    file_id = str(uuid.uuid4())
    file_ext = Path(file.filename).suffix
    file_path = UPLOAD_DIR / f"{file_id}{file_ext}"
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {
        "file_id": file_id, "filename": file.filename,
        "file_path": str(file_path), "status": "uploaded"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)