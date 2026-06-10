from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from Database.Database import get_db
from models.user import User
from models.schema import AdminStatsResponse, UserOut

admin_router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)

# Add this model
class AdminLoginRequest(BaseModel):
    password: str

# ── Admin Login ───────────────────────────────────────────────
@admin_router.post("/login")
def admin_login(data: AdminLoginRequest):
    if data.password == "admin@retailpulse2024":
        return {"status": "success"}
    raise HTTPException(
        status_code=401,
        detail="Incorrect password."
    )

@admin_router.get("/users", response_model=AdminStatsResponse)
def get_admin_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return {
        "status": "success",
        "users": [UserOut.model_validate(user) for user in users]
    }