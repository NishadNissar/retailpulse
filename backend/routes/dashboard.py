from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from Database.Database import get_db
from utils.jwt_handler import get_user_id_from_token
from fastapi import APIRouter, Depends, Query
from services.dashboard_service import (
    get_sales_data,
    get_products_data,
    get_customers_data,
    get_inventory_data,
    get_staff_data,
    get_health_data,
)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])
security = HTTPBearer()

from models.user import User
from datetime import datetime, timezone

def get_current_user_and_check_access(dashboard_name: str):
    def _checker(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
    ) -> int:
        user_id = get_user_id_from_token(credentials.credentials)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
            
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
            
        # Check trial expiry
        if user.trial_ends_at and datetime.now(timezone.utc) > user.trial_ends_at.replace(tzinfo=timezone.utc):
            raise HTTPException(status_code=403, detail="TRIAL_EXPIRED")
            
        # Check plan enforcement
        if user.plan == "starter" and dashboard_name in ["staff", "customers", "health"]:
            raise HTTPException(status_code=403, detail="UPGRADE_REQUIRED")
            
        return user_id
    return _checker


@router.get("/sales")
def sales(period: str = Query("today"), credentials = Depends(security), db = Depends(get_db)):
    user_id = get_user_id_from_token(credentials.credentials)
    return get_sales_data(db, user_id, period)

@router.get("/products")
def products(period: str = Query("today"), credentials = Depends(security), db = Depends(get_db)):
    user_id = get_user_id_from_token(credentials.credentials)
    return get_products_data(db, user_id, period)

@router.get("/customers")
def customers(period: str = Query("today"), credentials = Depends(security), db = Depends(get_db)):
    user_id = get_user_id_from_token(credentials.credentials)
    return get_customers_data(db, user_id, period)

@router.get("/inventory")
def inventory(period: str = Query("today"), credentials = Depends(security), db = Depends(get_db)):
    user_id = get_user_id_from_token(credentials.credentials)
    return get_inventory_data(db, user_id, period)

@router.get("/staff")
def staff(period: str = Query("today"), credentials = Depends(security), db = Depends(get_db)):
    user_id = get_user_id_from_token(credentials.credentials)
    return get_staff_data(db, user_id, period)

@router.get("/health")
def health(period: str = Query("today"), credentials = Depends(security), db = Depends(get_db)):
    user_id = get_user_id_from_token(credentials.credentials)
    return get_health_data(db, user_id, period)