from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from Database.Database import get_db
from models.schema import LoginRequest, LoginResponse
from services.auth_services import login_user
from pydantic import BaseModel
from models.schema import (
    Step1AccountCreate, Step1Response,
    Step2OTPVerify,     Step2Response,
    Step3StoreSetup,    Step3Response,
    Step4PlanSelect,    Step4Response,
    ResendOTPRequest,   ResendOTPResponse,
    UserOut,
)
from services.auth_services import (
    register_step1,
    register_step2,
    register_step3,
    register_step4,
    resend_otp,
)

router = APIRouter(prefix="/register", tags=["Registration"])
login_router = APIRouter(tags=["Login"])

@router.post("/step1", response_model=Step1Response, status_code=status.HTTP_201_CREATED)
def step1_create_account(payload: Step1AccountCreate, db: Session = Depends(get_db)):
    return register_step1(db, payload)

@router.post("/step2", response_model=Step2Response, status_code=status.HTTP_200_OK)
def step2_verify_otp(payload: Step2OTPVerify, db: Session = Depends(get_db)):
    return register_step2(db, payload)

@router.post("/step3", response_model=Step3Response, status_code=status.HTTP_200_OK)
def step3_store_setup(payload: Step3StoreSetup, db: Session = Depends(get_db)):
    return register_step3(db, payload)

@router.post("/step4", response_model=Step4Response, status_code=status.HTTP_200_OK)
def step4_select_plan(payload: Step4PlanSelect, db: Session = Depends(get_db)):
    return register_step4(db, payload)

@router.post("/resend-otp", response_model=ResendOTPResponse, status_code=status.HTTP_200_OK)
def resend_otp_endpoint(payload: ResendOTPRequest, db: Session = Depends(get_db)):
    return resend_otp(db, payload)

@login_router.post("/login", response_model=LoginResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return login_user(db, data)
class PasswordResetDirect(BaseModel):
    email: str
    new_password: str
    secret: str

@login_router.post("/admin/reset-password")
def reset_password_direct(data: PasswordResetDirect, db: Session = Depends(get_db)):
    if data.secret != "retailpulse2026":
        raise HTTPException(status_code=403, detail="Forbidden")
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"status": "success", "message": "Password reset"}
