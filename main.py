import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl, EmailStr
from datetime import datetime, timezone

# Database helpers
try:
    from database import db, create_document, get_documents
except Exception:
    db = None
    def create_document(*args, **kwargs):
        raise Exception("Database is not configured. Set DATABASE_URL and DATABASE_NAME.")
    def get_documents(*args, **kwargs):
        raise Exception("Database is not configured. Set DATABASE_URL and DATABASE_NAME.")

app = FastAPI(title="Song Pengsawang API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================
# Pydantic Schemas
# ==========================
class Metric(BaseModel):
    platform: str = Field(..., description="Platform name, e.g., Instagram")
    followers: int = Field(..., ge=0)
    avg_views: int = Field(..., ge=0, description="Average views per reel")
    engagement_rate: float = Field(..., ge=0)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Reel(BaseModel):
    id: Optional[str] = None
    title: str
    thumbnail_url: HttpUrl
    video_url: Optional[HttpUrl] = None
    views: int = 0
    likes: int = 0
    hashtags: List[str] = []
    posted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ContactMessage(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    message: str
    topic: Optional[str] = None

# ==========================
# Utility
# ==========================
COL_METRIC = "metric"
COL_REEL = "reel"
COL_CONTACT = "contactmessage"


def ensure_indexes():
    if db is None:
        return
    db[COL_REEL].create_index("posted_at")
    db[COL_REEL].create_index([("views", -1)])
    db[COL_CONTACT].create_index("email")


SEED_METRICS = [
    {
        "platform": "Instagram",
        "followers": 1250000,
        "avg_views": 1500000,
        "engagement_rate": 8.7,
        "last_updated": datetime.now(timezone.utc),
    }
]

SEED_REELS = [
    {
        "title": "Pad work with a twist",
        "thumbnail_url": "https://images.unsplash.com/photo-1605296867304-46d5465a13f1?q=80&w=1200&auto=format&fit=crop",
        "video_url": "https://www.example.com/reel1.mp4",
        "views": 2300000,
        "likes": 340000,
        "hashtags": ["#muaythai", "#twerk", "#funnytraining"],
    },
    {
        "title": "Elbows, knees & giggles",
        "thumbnail_url": "https://images.unsplash.com/photo-1544916601-0aa3f82a1f2d?q=80&w=1200&auto=format&fit=crop",
        "video_url": "https://www.example.com/reel2.mp4",
        "views": 1800000,
        "likes": 280000,
        "hashtags": ["#muaythai", "#reels", "#songpengsawang"],
    },
]


def seed_data():
    if db is None:
        return
    if db[COL_METRIC].count_documents({}) == 0:
        for m in SEED_METRICS:
            create_document(COL_METRIC, m)
    if db[COL_REEL].count_documents({}) == 0:
        for r in SEED_REELS:
            create_document(COL_REEL, r)


@app.on_event("startup")
async def on_startup():
    try:
        ensure_indexes()
        seed_data()
    except Exception:
        # Database might not be configured; ignore to allow server start
        pass


# ==========================
# Routes
# ==========================
@app.get("/health")
async def health():
    status = {
        "backend": "ok",
        "database": "connected" if db is not None else "not_configured",
    }
    return status


@app.get("/metrics", response_model=List[Metric])
async def get_metrics():
    try:
        docs = get_documents(COL_METRIC)
        # Normalize keys for Pydantic
        items = []
        for d in docs:
            d.pop("_id", None)
            items.append(Metric(**d))
        return items
    except Exception as e:
        # Fallback: return seed data for preview when DB isn't configured
        return [Metric(**m) for m in SEED_METRICS]


@app.get("/reels", response_model=List[Reel])
async def get_reels(limit: int = 20):
    try:
        docs = get_documents(COL_REEL, {}, min(limit, 50))
        items = []
        for d in docs:
            rid = str(d.get("_id")) if d.get("_id") else None
            d.pop("_id", None)
            items.append(Reel(id=rid, **d))
        return items
    except Exception:
        return [Reel(**r) for r in SEED_REELS][:limit]


@app.post("/contact")
async def submit_contact(payload: ContactMessage):
    data = payload.model_dump()
    data["received_at"] = datetime.now(timezone.utc)
    try:
        if db is not None:
            doc_id = create_document(COL_CONTACT, data)
            return {"status": "ok", "id": doc_id}
        else:
            return {"status": "ok", "id": None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    return {"message": "Song Pengsawang API running"}


@app.get("/test")
async def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        from database import db as _db
        if _db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set"
            response["database_name"] = getattr(_db, 'name', '✅ Connected')
            response["connection_status"] = "Connected"
            try:
                response["collections"] = _db.list_collection_names()[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
