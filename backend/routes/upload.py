from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from Database.Database import get_db
from utils.jwt_handler import get_user_id_from_token
from services.upload_service import process_upload
import os, shutil, uuid

router = APIRouter(prefix="/upload", tags=["Upload"])
security = HTTPBearer()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv"}

@router.post("/", summary="Upload daily sales Excel or CSV file")
async def upload_file(
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    user_id = get_user_id_from_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    from models.user import User
    from datetime import datetime, timezone
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    if user.trial_ends_at and datetime.now(timezone.utc) > user.trial_ends_at:
        raise HTTPException(status_code=403, detail="TRIAL_EXPIRED")
        
    max_rows = 500 if user.plan == "starter" else None

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Only .xlsx, .xls, .csv allowed."
        )

    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path   = os.path.join(UPLOAD_DIR, unique_name)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    result = process_upload(
        file_path=file_path,
        original_name=file.filename,
        user_id=user_id,
        db=db,
        max_rows=max_rows
    )

    return JSONResponse(content=result)