from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from Database.Database import get_db
from utils.jwt_handler import get_user_id_from_token
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
        if user.trial_ends_at and datetime.now(timezone.utc) > user.trial_ends_at:
            raise HTTPException(status_code=403, detail="TRIAL_EXPIRED")
            
        # Check plan enforcement
        if user.plan == "starter" and dashboard_name in ["staff", "customers", "health"]:
            raise HTTPException(status_code=403, detail="UPGRADE_REQUIRED")
            
        return user_id
    return _checker


@router.get("/sales", summary="Sales dashboard data")
def sales_dashboard(
    period: str = "all",
    user_id: int = Depends(get_current_user_and_check_access("sales")),
    db: Session = Depends(get_db)
):
    return get_sales_data(db, user_id, period)


@router.get("/products", summary="Products dashboard data")
def products_dashboard(
    user_id: int = Depends(get_current_user_and_check_access("products")),
    db: Session = Depends(get_db)
):
    return get_products_data(db, user_id)


@router.get("/customers", summary="Customers dashboard data")
def customers_dashboard(
    user_id: int = Depends(get_current_user_and_check_access("customers")),
    db: Session = Depends(get_db)
):
    return get_customers_data(db, user_id)


@router.get("/inventory", summary="Inventory dashboard data")
def inventory_dashboard(
    user_id: int = Depends(get_current_user_and_check_access("inventory")),
    db: Session = Depends(get_db)
):
    return get_inventory_data(db, user_id)


@router.get("/staff", summary="Staff & Ops dashboard data")
def staff_dashboard(
    user_id: int = Depends(get_current_user_and_check_access("staff")),
    db: Session = Depends(get_db)
):
    return get_staff_data(db, user_id)


@router.get("/health", summary="Business Health dashboard data")
def health_dashboard(
    user_id: int = Depends(get_current_user_and_check_access("health")),
    db: Session = Depends(get_db)
):
    return get_health_data(db, user_id)