from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.base import Base
from app.db.session import engine

from app.api import auth, user
from app.api import contact


app = FastAPI(title="Contact Manager API")

app.include_router(contact.router)



# ✅ CORS FIX
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
app.include_router(user.router)

@app.get("/")
def root():
    return {"message": "Backend running 🚀"}