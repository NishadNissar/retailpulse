from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Date
from sqlalchemy.sql import func
from Database.Database import Base
import enum


# ── Enums ─────────────────────────────────────────────────────────────────────

class PlanType(str, enum.Enum):
    starter = "starter"
    growth  = "growth"
    chain   = "chain"


class BillingSoftware(str, enum.Enum):
    marg      = "Marg ERP"
    busy      = "Busy Accounting"
    vyapar    = "Vyapar"
    tally     = "Tally"
    gofrugal  = "GoFrugal"
    other     = "Custom / Other"


class StoreState(str, enum.Enum):
    KL    = "Kerala"
    TN    = "Tamil Nadu"
    KA    = "Karnataka"
    AP    = "Andhra Pradesh"
    TS    = "Telangana"
    MH    = "Maharashtra"
    DL    = "Delhi"
    GJ    = "Gujarat"
    other = "Other"


# ── User model ────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    # ── Primary key ──────────────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # ── Step 1: Account details ───────────────────────────────────────────────
    first_name    = Column(String(100), nullable=False)
    last_name     = Column(String(100), nullable=False)
    email         = Column(String(255), unique=True, index=True, nullable=False)
    phone         = Column(String(20),  unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)  # bcrypt hash

    # ── Step 2: OTP verification ──────────────────────────────────────────────
    is_phone_verified = Column(Boolean, default=False, nullable=False)
    otp_code          = Column(String(6),  nullable=True)   # temp OTP
    otp_expires_at    = Column(DateTime(timezone=True), nullable=True)

    # ── Step 3: Store details ─────────────────────────────────────────────────
    store_name      = Column(String(200), nullable=True)
    store_city      = Column(String(100), nullable=True)
    store_state     = Column(String(50),  nullable=True)
    billing_software= Column(String(100), nullable=True)
    monthly_revenue = Column(String(50),  nullable=True)  # e.g. "₹5–15 lakh"
    store_count     = Column(String(20),  nullable=True)  # e.g. "1 store"

    # ── Step 4: Plan ──────────────────────────────────────────────────────────
    plan = Column(
        String(20),
        default="growth",
        nullable=False
    )

    # ── Account status ────────────────────────────────────────────────────────
    is_active         = Column(Boolean, default=True,  nullable=False)
    is_email_verified = Column(Boolean, default=False, nullable=False)
    trial_ends_at     = Column(DateTime(timezone=True), nullable=True)

    # ── Password Reset ────────────────────────────────────────────────────────
    reset_token       = Column(String(255), nullable=True)
    reset_expires_at  = Column(DateTime(timezone=True), nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    def __repr__(self):
        return (
            f"<User id={self.id} email={self.email} "
            f"store={self.store_name} plan={self.plan}>"
        )
# ══════════════════════════════════════════════════════════════
# SALES DATA TABLE
# ══════════════════════════════════════════════════════════════

class SalesData(Base):
    __tablename__ = "sales_data"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, nullable=False, index=True)

    # Core fields
    date           = Column(Date, nullable=True)
    time           = Column(String, nullable=True)
    invoice_number = Column(String, nullable=True)
    product        = Column(String, nullable=True)
    category       = Column(String, nullable=True)
    quantity       = Column(Float, nullable=True)
    unit_price     = Column(Float, nullable=True)
    total_amount   = Column(Float, nullable=True)
    cost_price     = Column(Float, nullable=True)
    customer_id    = Column(String, nullable=True)
    payment_mode   = Column(String, nullable=True)

    # Optional fields
    stock_qty      = Column(Float, nullable=True)
    reorder_point  = Column(Float, nullable=True)
    expiry_date    = Column(Date, nullable=True)
    staff_count    = Column(Float, nullable=True)
    counter_id     = Column(String, nullable=True)
    expense_type   = Column(String, nullable=True)
    expense_amount = Column(Float, nullable=True)
    cost_amount    = Column(Float, nullable=True)

    # Metadata
    upload_id      = Column(Integer, nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════
# UPLOAD HISTORY TABLE
# ══════════════════════════════════════════════════════════════

class UploadHistory(Base):
    __tablename__ = "upload_history"

    id             = Column(Integer, primary_key=True, index=True)
    user_id        = Column(Integer, nullable=False, index=True)
    file_name      = Column(String, nullable=False)
    original_rows  = Column(Integer, nullable=True)
    cleaned_rows   = Column(Integer, nullable=True)
    removed_rows   = Column(Integer, nullable=True)
    status         = Column(String, default="success")
    cleaning_log   = Column(String, nullable=True)  # stored as JSON string
    uploaded_at    = Column(DateTime(timezone=True), server_default=func.now())