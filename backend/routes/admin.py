from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from Database.Database import get_db
from models.user import User, SalesData, UploadHistory
from models.schema import AdminStatsResponse, UserOut
from utils.password import hash_password
from utils.jwt_handler import verify_token
from datetime import datetime, timedelta, timezone
import pandas as pd

admin_router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)

# ── Schemas ───────────────────────────────────────────────────
class AdminLoginRequest(BaseModel):
    password: str

class AdminUserCreateRequest(BaseModel):
    first_name: str
    last_name: str
    email: str
    phone: str
    password: str
    store_name: Optional[str] = None
    store_city: Optional[str] = None
    store_state: Optional[str] = None
    billing_software: Optional[str] = None
    monthly_revenue: Optional[str] = None
    store_count: Optional[str] = None
    plan: Optional[str] = "starter"

class AdminUserPlanUpdateRequest(BaseModel):
    plan: str

class AdminUserStatusUpdateRequest(BaseModel):
    is_active: bool

# ── Admin Login ───────────────────────────────────────────────
@admin_router.post("/login")
def admin_login(data: AdminLoginRequest):
    if data.password == "admin@retailpulse2024" or data.password == "admin123":
        return {"status": "success"}
    raise HTTPException(status_code=401, detail="Incorrect password.")

# ── Get Live Plan (called by frontend on every page load) ─────
@admin_router.get("/me")
def get_me(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.replace("Bearer ", "")
    try:
        payload = verify_token(token)
        if not payload:
            raise ValueError("Invalid token")
        user_id = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    PLAN_LABELS = {
        "starter":  "Starter (Free)",
        "silver":   "Silver — ₹499/mo",
        "platinum": "Platinum — ₹999/mo",
    }
    valid_plans = ["starter", "silver", "platinum"]
    live_plan = user.plan if user.plan in valid_plans else "starter"
    return {
        "status":        "success",
        "user_id":       user.id,
        "first_name":    user.first_name,
        "email":         user.email,
        "store_name":    user.store_name or "",
        "plan":          live_plan,
        "plan_label":    PLAN_LABELS.get(live_plan, live_plan),
        "trial_ends_at": user.trial_ends_at.isoformat() if user.trial_ends_at else None,
        "is_active":     user.is_active,
    }

# ── Get All Users ─────────────────────────────────────────────
@admin_router.get("/users", response_model=AdminStatsResponse)
def get_admin_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return {
        "status": "success",
        "users": [UserOut.model_validate(user) for user in users]
    }

# ── Add User Manually ─────────────────────────────────────────
@admin_router.post("/users", status_code=status.HTTP_201_CREATED)
def admin_create_user(data: AdminUserCreateRequest, db: Session = Depends(get_db)):
    existing_email = db.query(User).filter(User.email == data.email.lower().strip()).first()
    if existing_email:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    existing_phone = db.query(User).filter(User.phone == data.phone.strip()).first()
    if existing_phone:
        raise HTTPException(status_code=409, detail="This phone number is already registered.")
    trial_ends = None
    if data.plan in ["silver", "platinum", "growth"]:
        trial_ends = datetime.now(timezone.utc) + timedelta(days=30)
    user = User(
        first_name       = data.first_name.strip(),
        last_name        = data.last_name.strip(),
        email            = data.email.lower().strip(),
        phone            = data.phone.strip(),
        password_hash    = hash_password(data.password),
        is_phone_verified= True,
        is_email_verified= True,
        store_name       = data.store_name.strip() if data.store_name else None,
        store_city       = data.store_city.strip() if data.store_city else None,
        store_state      = data.store_state,
        billing_software = data.billing_software,
        monthly_revenue  = data.monthly_revenue,
        store_count      = data.store_count,
        plan             = data.plan,
        trial_ends_at    = trial_ends,
        is_active        = True
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"status": "success", "message": "User created manually", "user_id": user.id}

# ── Get User Details, History & Stats ────────────────────────
@admin_router.get("/users/{user_id}/details")
def admin_user_details(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    uploads = db.query(UploadHistory).filter(UploadHistory.user_id == user_id).order_by(UploadHistory.uploaded_at.desc()).all()
    upload_list = []
    for u in uploads:
        upload_list.append({
            "id":           u.id,
            "file_name":    u.file_name,
            "original_rows":u.original_rows,
            "cleaned_rows": u.cleaned_rows,
            "removed_rows": u.removed_rows,
            "status":       u.status,
            "cleaning_log": u.cleaning_log,
            "uploaded_at":  u.uploaded_at.isoformat() if u.uploaded_at else None
        })
    sales_rows = db.query(SalesData).filter(SalesData.user_id == user_id).all()
    total_revenue = 0.0
    total_cost    = 0.0
    total_orders  = 0
    if sales_rows:
        df = pd.DataFrame([{
            "total_amount":   r.total_amount,
            "cost_price":     r.cost_price,
            "quantity":       r.quantity,
            "invoice_number": r.invoice_number
        } for r in sales_rows])
        total_revenue = float(df["total_amount"].sum())
        total_cost    = float(df["cost_price"].fillna(0).multiply(df["quantity"].fillna(0)).sum())
        total_orders  = df["invoice_number"].nunique() if "invoice_number" in df.columns else len(df)
    total_profit    = total_revenue - total_cost
    avg_order_value = round(total_revenue / total_orders, 2) if total_orders > 0 else 0.0
    return {
        "status":         "success",
        "user":           UserOut.model_validate(user),
        "upload_history": upload_list,
        "kpis": {
            "total_revenue":   round(total_revenue, 2),
            "total_profit":    round(total_profit, 2),
            "total_orders":    total_orders,
            "avg_order_value": avg_order_value
        }
    }

# ── Update User Plan ──────────────────────────────────────────
@admin_router.put("/users/{user_id}/plan")
def admin_update_user_plan(user_id: int, data: AdminUserPlanUpdateRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.plan not in ["starter", "silver", "platinum", "growth"]:
        raise HTTPException(status_code=400, detail="Invalid plan name")
    user.plan = data.plan
    if data.plan == "starter":
        user.trial_ends_at = None
    elif not user.trial_ends_at:
        user.trial_ends_at = datetime.now(timezone.utc) + timedelta(days=30)
    db.commit()
    return {"status": "success", "message": f"Plan updated to {data.plan}"}

# ── Toggle User Status ────────────────────────────────────────
@admin_router.put("/users/{user_id}/status")
def admin_update_user_status(user_id: int, data: AdminUserStatusUpdateRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = data.is_active
    db.commit()
    return {"status": "success", "message": "User status updated"}

# ── Extend Trial ──────────────────────────────────────────────
@admin_router.post("/users/{user_id}/extend-trial")
def admin_extend_user_trial(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    current_end = user.trial_ends_at or datetime.now(timezone.utc)
    user.trial_ends_at = current_end + timedelta(days=30)
    db.commit()
    return {"status": "success", "message": "Trial extended by 30 days", "trial_ends_at": user.trial_ends_at}

# ── Delete User ───────────────────────────────────────────────
@admin_router.delete("/users/{user_id}")
def admin_delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.query(SalesData).filter(SalesData.user_id == user_id).delete(synchronize_session=False)
    db.query(UploadHistory).filter(UploadHistory.user_id == user_id).delete(synchronize_session=False)
    db.delete(user)
    db.commit()
    return {"status": "success", "message": "User and associated data permanently deleted"}