# RetailPulse Backend — Setup Guide

## Folder Structure
```
backend/
├── Database/
│   ├── __init__.py
│   └── database.py         ← DB connection, session, Base
├── models/
│   ├── __init__.py
│   ├── user.py             ← SQLAlchemy User model
│   └── schemas.py          ← Pydantic request/response schemas
├── routes/
│   ├── __init__.py
│   └── auth.py             ← Registration endpoints
├── services/
│   ├── __init__.py
│   └── auth_service.py     ← All business logic
├── utils/
│   ├── __init__.py
│   ├── password.py         ← bcrypt hashing
│   ├── jwt_handler.py      ← JWT create/verify
│   └── otp.py              ← OTP generate/send/mask
├── uploads/                ← Excel files uploaded by stores
├── main.py                 ← FastAPI app entry point
├── requirements.txt
└── .env.example
```

---

## Step 1 — Install PostgreSQL
Download from https://www.postgresql.org/download/
Create a database:
```sql
CREATE DATABASE retailpulse_db;
```

---

## Step 2 — Set up virtual environment
```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

---

## Step 3 — Install dependencies
```bash
pip install -r requirements.txt
```

---

## Step 4 — Configure environment
```bash
cp .env.example .env
```
Edit `.env` and fill in:
- `DATABASE_URL` with your PostgreSQL credentials
- `SECRET_KEY` with a random string (run: `python -c "import secrets; print(secrets.token_hex(32))"`)

---

## Step 5 — Run the server
```bash
uvicorn main:app --reload --port 8000
```

Server starts at: http://localhost:8000
Swagger docs at:  http://localhost:8000/docs
ReDoc at:         http://localhost:8000/redoc

---

## API Endpoints — Registration Flow

### Step 1 — Create account
```
POST /register/step1
Content-Type: application/json

{
  "first_name": "Arun",
  "last_name":  "Menon",
  "email":      "arun@srilakshmimart.com",
  "phone":      "+919876543210",
  "password":   "Secure@2025"
}
```
**Returns:** `user_id` — save this and pass to all next steps

---

### Step 2 — Verify OTP
```
POST /register/step2
Content-Type: application/json

{
  "user_id": 1,
  "otp":     "482910"
}
```
*In development: OTP is printed to the terminal where uvicorn is running*

---

### Step 3 — Store setup
```
POST /register/step3
Content-Type: application/json

{
  "user_id":          1,
  "store_name":       "Sri Lakshmi Mart",
  "store_city":       "Thiruvananthapuram",
  "store_state":      "KL",
  "billing_software": "Marg ERP",
  "monthly_revenue":  "₹5–15 lakh",
  "store_count":      "1 store"
}
```

---

### Step 4 — Choose plan (completes registration)
```
POST /register/step4
Content-Type: application/json

{
  "user_id": 1,
  "plan":    "growth"
}
```
**Returns:** `access_token` (JWT) — store this in frontend localStorage

---

### Resend OTP
```
POST /register/resend-otp
Content-Type: application/json

{ "user_id": 1 }
```

---

## Testing with Swagger UI
1. Run the server
2. Open http://localhost:8000/docs
3. Click any endpoint → "Try it out" → fill the body → "Execute"
4. You can see request/response, status codes, and errors

---

## Common Errors

| Code | Meaning |
|------|---------|
| 409  | Email or phone already registered |
| 400  | OTP expired or incorrect |
| 403  | Tried to skip a step |
| 404  | user_id not found |
| 422  | Validation error (bad input format) |
