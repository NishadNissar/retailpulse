import pandas as pd
import numpy as np
import os
import re
import json
from datetime import datetime
from sqlalchemy.orm import Session
from models.user import SalesData, UploadHistory


# ══════════════════════════════════════════════════════════════
# SAFE STRING HELPER — prevents all float/NaN errors
# ══════════════════════════════════════════════════════════════

def safe_str(val):
    """Convert to string safely. Returns None if NaN/None/empty."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    return None if s.lower() in ("nan", "none", "null", "") else s

# ══════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

def process_upload(file_path: str, original_name: str, user_id: int = None, db: Session = None, max_rows: int = None) -> dict:
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            try:
                df = pd.read_csv(file_path, encoding="utf-8", on_bad_lines="skip")
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, encoding="latin-1", on_bad_lines="skip")
        else:
            df = pd.read_excel(file_path)

        original_rows = len(df)
        original_cols = list(df.columns)

        df, cleaning_log = clean_data(df)
        cleaned_rows = len(df)
        
        if max_rows and cleaned_rows > max_rows:
            df = df.head(max_rows)
            cleaned_rows = len(df)
            cleaning_log.append(f"⚠️ Plan Limit: Only the first {max_rows} rows were processed.")

        # ── Save to Supabase if user_id and db provided ───────
        upload_id = None
        if user_id and db:
            upload_id = save_to_database(
                db=db,
                user_id=user_id,
                df=df.copy(),
                file_name=original_name,
                original_rows=original_rows,
                cleaned_rows=cleaned_rows,
                removed_rows=original_rows - cleaned_rows,
                cleaning_log=cleaning_log
            )

        # Convert timestamps to strings for JSON
        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%d")

        return {
            "status":        "success",
            "file_name":     original_name,
            "original_rows": original_rows,
            "cleaned_rows":  cleaned_rows,
            "removed_rows":  original_rows - cleaned_rows,
            "original_cols": original_cols,
            "final_cols":    list(df.columns),
            "cleaning_log":  cleaning_log,
            "upload_id":     upload_id,
            "preview":       df.head(5).to_dict(orient="records"),
        }

    except Exception as e:
        return {
            "status":    "error",
            "message":   str(e),
            "file_name": original_name,
        }

# ══════════════════════════════════════════════════════════════
# MASTER CLEAN FUNCTION
# ══════════════════════════════════════════════════════════════

def clean_data(df: pd.DataFrame):
    log = []

    import traceback

    steps = [
        ("step1_clean_column_names",    step1_clean_column_names),
        ("step2_remove_empty_rows",     step2_remove_empty_rows),
        ("step3_remove_duplicates",     step3_remove_duplicates),
        ("step4_clean_date_column",     step4_clean_date_column),
        ("step5_clean_time_column",     step5_clean_time_column),
        ("step6_clean_invoice_number",  step6_clean_invoice_number),
        ("step7_clean_product_column",  step7_clean_product_column),
        ("step8_clean_category_column", step8_clean_category_column),
        ("step9_clean_quantity_column", step9_clean_quantity_column),
        ("step10_clean_price_columns",  step10_clean_price_columns),
        ("step11_clean_amount_columns", step11_clean_amount_columns),
        ("step12_clean_customer_id",    step12_clean_customer_id),
        ("step13_clean_payment_mode",   step13_clean_payment_mode),
        ("step14_clean_stock_columns",  step14_clean_stock_columns),
        ("step15_clean_expiry_date",    step15_clean_expiry_date),
        ("step16_remove_invalid_rows",  step16_remove_invalid_rows),
    ]

    for step_name, step_func in steps:
        try:
            df, log = step_func(df, log)
        except Exception as e:
            raise Exception(f"FAILED AT {step_name}: {str(e)}")

    if not log:
        log.append("✅ Data is already clean — no issues found!")

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 1 — STANDARDIZE COLUMN NAMES
# ══════════════════════════════════════════════════════════════

def step1_clean_column_names(df, log):
    original = list(df.columns)

    # Normalize: lowercase, strip, replace special chars with _
    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"[^a-z0-9]", "_", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
    )

    # Map every possible variation to standard column name
    rename_map = {
        # ── DATE ──────────────────────────────────────────────
        "dt":               "date",
        "bill_date":        "date",
        "invoice_date":     "date",
        "trans_date":       "date",
        "transaction_date": "date",
        "sale_date":        "date",
        "sales_date":       "date",
        "dated":            "date",
        "txn_date":         "date",
        "order_date":       "date",

        # ── TIME ──────────────────────────────────────────────
        "transaction_time": "time",
        "bill_time":        "time",
        "sale_time":        "time",
        "txn_time":         "time",
        "timestamp":        "time",

        # ── INVOICE NUMBER ────────────────────────────────────
        "invoice_no":       "invoice_number",
        "invoice_num":      "invoice_number",
        "bill_no":          "invoice_number",
        "bill_number":      "invoice_number",
        "receipt_no":       "invoice_number",
        "receipt_number":   "invoice_number",
        "voucher_no":       "invoice_number",
        "txn_id":           "invoice_number",
        "transaction_id":   "invoice_number",
        "order_no":         "invoice_number",
        "order_id":         "invoice_number",
        "inv_no":           "invoice_number",
        "inv":              "invoice_number",

        # ── PRODUCT ───────────────────────────────────────────
        "item":             "product",
        "item_name":        "product",
        "product_name":     "product",
        "item_desc":        "product",
        "description":      "product",
        "particulars":      "product",
        "goods":            "product",
        "product_desc":     "product",
        "prod_name":        "product",
        "sku_name":         "product",
        "name":             "product",

        # ── CATEGORY ──────────────────────────────────────────
        "cat":              "category",
        "dept":             "category",
        "department":       "category",
        "section":          "category",
        "product_category": "category",
        "item_category":    "category",
        "group":            "category",
        "item_group":       "category",
        "product_group":    "category",

        # ── QUANTITY ──────────────────────────────────────────
        "qty":              "quantity",
        "units":            "quantity",
        "unit":             "quantity",
        "no_of_items":      "quantity",
        "pieces":           "quantity",
        "pcs":              "quantity",
        "nos":              "quantity",
        "count":            "quantity",
        "sold_qty":         "quantity",
        "sale_qty":         "quantity",

        # ── UNIT PRICE ────────────────────────────────────────
        "price":            "unit_price",
        "rate":             "unit_price",
        "mrp":              "unit_price",
        "selling_price":    "unit_price",
        "sale_price":       "unit_price",
        "sp":               "unit_price",
        "unit_rate":        "unit_price",
        "price_per_unit":   "unit_price",
        "item_price":       "unit_price",

        # ── TOTAL AMOUNT ──────────────────────────────────────
        "amount":           "total_amount",
        "total":            "total_amount",
        "net_amount":       "total_amount",
        "bill_amount":      "total_amount",
        "invoice_amount":   "total_amount",
        "invoice_amt":      "total_amount",
        "value":            "total_amount",
        "sales":            "total_amount",
        "net_total":        "total_amount",
        "gross_amount":     "total_amount",
        "subtotal":         "total_amount",
        "sub_total":        "total_amount",
        "final_amount":     "total_amount",

        # ── COST PRICE ────────────────────────────────────────
        "cost":             "cost_price",
        "purchase_price":   "cost_price",
        "buying_price":     "cost_price",
        "cp":               "cost_price",
        "landed_cost":      "cost_price",
        "purchase_rate":    "cost_price",

        # ── COST AMOUNT ───────────────────────────────────────
        "cost_amount":      "cost_amount",
        "purchase_amount":  "cost_amount",
        "cogs":             "cost_amount",

        # ── CUSTOMER ID ───────────────────────────────────────
        "customer_id":      "customer_id",
        "cust_id":          "customer_id",
        "customer_code":    "customer_id",
        "member_id":        "customer_id",
        "loyalty_id":       "customer_id",
        "phone":            "customer_id",
        "mobile":           "customer_id",
        "mobile_no":        "customer_id",
        "contact":          "customer_id",

        # ── CUSTOMER NAME ─────────────────────────────────────
        "customer":         "customer_name",
        "cust_name":        "customer_name",
        "buyer":            "customer_name",
        "client":           "customer_name",

        # ── PAYMENT MODE ──────────────────────────────────────
        "payment_method":   "payment_mode",
        "payment_type":     "payment_mode",
        "mode_of_payment":  "payment_mode",
        "pay_mode":         "payment_mode",
        "pay_type":         "payment_mode",
        "tender_type":      "payment_mode",

        # ── STOCK ─────────────────────────────────────────────
        "stock":            "stock_qty",
        "stock_quantity":   "stock_qty",
        "closing_stock":    "stock_qty",
        "balance_qty":      "stock_qty",
        "available_stock":  "stock_qty",
        "on_hand":          "stock_qty",

        # ── REORDER POINT ─────────────────────────────────────
        "reorder_level":    "reorder_point",
        "min_stock":        "reorder_point",
        "minimum_qty":      "reorder_point",
        "safety_stock":     "reorder_point",

        # ── EXPIRY DATE ───────────────────────────────────────
        "expiry":           "expiry_date",
        "exp_date":         "expiry_date",
        "best_before":      "expiry_date",
        "use_by":           "expiry_date",
        "mfg_date":         "expiry_date",

        # ── STAFF / COUNTER ───────────────────────────────────
        "staff":            "staff_count",
        "employee_count":   "staff_count",
        "cashier":          "counter_id",
        "counter":          "counter_id",
        "terminal":         "counter_id",
        "pos_id":           "counter_id",

        # ── EXPENSE ───────────────────────────────────────────
        "expense":          "expense_type",
        "expense_name":     "expense_type",
        "head":             "expense_type",
        "expense_head":     "expense_type",
        "exp_amount":       "expense_amount",
        "expense_value":    "expense_amount",
    }

    df.rename(columns=rename_map, inplace=True)

    changed = [
        f"'{o}' → '{n}'"
        for o, n in zip(original, df.columns)
        if str(o).lower().strip() != n
    ]
    if changed:
        log.append(f"Renamed columns: {', '.join(changed)}")

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 2 — REMOVE EMPTY / MEANINGLESS ROWS
# ══════════════════════════════════════════════════════════════

def step2_remove_empty_rows(df, log):
    before = len(df)
    df = df.dropna(how="all")

    def is_meaningless(row):
        for val in row:
            v = str(val).strip().lower()
            if v not in ("", "nan", "none", "null", "n/a", "na", "-", "0", "0.0"):
                return False
        return True

    mask = df.apply(is_meaningless, axis=1)
    df = df[~mask]

    removed = before - len(df)
    if removed > 0:
        log.append(f"Removed {removed} empty/meaningless rows")

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 3 — REMOVE DUPLICATES
# ══════════════════════════════════════════════════════════════

def step3_remove_duplicates(df, log):
    before = len(df)
    df = df.drop_duplicates()
    removed = before - len(df)
    if removed > 0:
        log.append(f"Removed {removed} duplicate rows")

    if "invoice_number" in df.columns:
        dup_inv = df["invoice_number"].duplicated().sum()
        if dup_inv > 0:
            log.append(
                f"⚠️ {dup_inv} duplicate invoice numbers found "
                f"(kept — multiple items on same bill is normal)"
            )

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 4 — CLEAN DATE COLUMN
# ══════════════════════════════════════════════════════════════

def step4_clean_date_column(df, log):
    if "date" not in df.columns:
        log.append("⚠️ 'date' column not found — Sales/Business Health dashboards need it")
        return df, log

    before_nulls = df["date"].isna().sum()
    df["date"] = df["date"].apply(parse_any_date)
    after_nulls  = df["date"].isna().sum()
    new_nulls    = after_nulls - before_nulls

    log.append("Parsed 'date' column — all formats handled")

    if new_nulls > 0:
        log.append(f"⚠️ {new_nulls} dates could not be parsed → set to NaT (will be excluded from charts)")

    today = pd.Timestamp(datetime.today().date())

    if pd.api.types.is_datetime64_any_dtype(df["date"]):
        future = (df["date"] > today).sum()
        if future > 0:
            log.append(f"⚠️ {future} future dates found — verify these rows")

        old = (df["date"] < pd.Timestamp("2000-01-01")).sum()
        if old > 0:
            log.append(f"⚠️ {old} dates before year 2000 — likely entry errors")

    return df, log


def parse_any_date(value):
    if pd.isna(value):
        return pd.NaT

    if isinstance(value, (pd.Timestamp, datetime)):
        return pd.Timestamp(value)

    val = str(value).strip()

    # Remove time portion if combined
    val = re.sub(
        r"\s+\d{1,2}:\d{2}(:\d{2})?(\s*(AM|PM|am|pm))?$", "", val
    ).strip()

    # All date formats
    formats = [
        # d/m/y
        "%d/%m/%Y", "%d/%m/%y",
        "%d-%m-%Y", "%d-%m-%y",
        "%d.%m.%Y", "%d.%m.%y",
        "%d %m %Y", "%d %m %y",

        # m/d/y (US)
        "%m/%d/%Y", "%m/%d/%y",
        "%m-%d-%Y", "%m-%d-%y",
        "%m.%d.%Y", "%m.%d.%y",

        # y/m/d (ISO)
        "%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d",

        # y/d/m
        "%Y/%d/%m", "%Y-%d-%m",

        # Written month — day first
        "%d %b %Y",  "%d %B %Y",
        "%d-%b-%Y",  "%d-%B-%Y",
        "%d/%b/%Y",  "%d/%B/%Y",
        "%d %b, %Y", "%d %B, %Y",
        "%d %b %y",  "%d-%b-%y",

        # Written month — month first
        "%b %d %Y",   "%B %d %Y",
        "%b-%d-%Y",   "%B-%d-%Y",
        "%b/%d/%Y",   "%B/%d/%Y",
        "%b %d, %Y",  "%B %d, %Y",
        "%b %d %y",   "%b-%d-%y",

        # No separator
        "%d%m%Y", "%Y%m%d",
    ]

    for fmt in formats:
        try:
            return pd.Timestamp(datetime.strptime(val, fmt))
        except ValueError:
            continue

    try:
        return pd.to_datetime(val, infer_datetime_format=True)
    except Exception:
        return pd.NaT


# ══════════════════════════════════════════════════════════════
# STEP 5 — CLEAN TIME COLUMN
# ══════════════════════════════════════════════════════════════

def step5_clean_time_column(df, log):
    if "time" not in df.columns:
        return df, log

    def parse_time(val):
        if pd.isna(val):
            return None

        val = str(val).strip()

        # Already HH:MM or HH:MM:SS
        if re.match(r"^\d{1,2}:\d{2}(:\d{2})?$", val):
            return val[:5]  # keep HH:MM only

        # 12-hour format: 9:30 AM, 09:30AM
        match = re.match(
            r"(\d{1,2}):(\d{2})(?::\d{2})?\s*(AM|PM|am|pm)", val
        )
        if match:
            h, m, period = int(match.group(1)), int(match.group(2)), match.group(3).upper()
            if period == "PM" and h != 12:
                h += 12
            if period == "AM" and h == 12:
                h = 0
            return f"{h:02d}:{m:02d}"

        # Numeric like 930 → 09:30, 1430 → 14:30
        if re.match(r"^\d{3,4}$", val):
            val = val.zfill(4)
            return f"{val[:2]}:{val[2:]}"

        # Timestamp with date — extract time part
        match = re.search(r"(\d{1,2}:\d{2}(:\d{2})?)", val)
        if match:
            return match.group(1)[:5]

        return None

    df["time"] = df["time"].apply(parse_time)
    nulls = df["time"].isna().sum()
    if nulls > 0:
        log.append(f"⚠️ {nulls} time values could not be parsed in 'time' column")
    else:
        log.append("Parsed 'time' column — all formats handled (Staff & Customer dashboards)")

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 6 — CLEAN INVOICE NUMBER
# ══════════════════════════════════════════════════════════════

def step6_clean_invoice_number(df, log):
    if "invoice_number" not in df.columns:
        log.append("⚠️ 'invoice_number' column not found — Combo analysis won't work")
        return df, log

    df["invoice_number"] = (
        df["invoice_number"]
        .astype(str)
        .str.strip()
        .str.upper()
        .str.replace(r"\s+", "", regex=True)
    )

    # Replace blanks
    df["invoice_number"] = df["invoice_number"].replace(
        ["", "NAN", "NONE", "NULL", "N/A", "NA", "-"],
        np.nan
    )

    nulls = df["invoice_number"].isna().sum()
    if nulls > 0:
        log.append(f"⚠️ {nulls} missing invoice numbers found")

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 7 — CLEAN PRODUCT COLUMN
# ══════════════════════════════════════════════════════════════

def step7_clean_product_column(df, log):
    if "product" not in df.columns:
        log.append("⚠️ 'product' column not found — Product dashboard needs it")
        return df, log

    df["product"] = (
        df["product"]
        .astype(str)
        .str.strip()
        # Remove multiple spaces
        .str.replace(r"\s+", " ", regex=True)
        # Title case
        .str.title()
    )

    # Standardize common product name variations
    product_fixes = {
        # Milk
        r"(?i)amul\s*milk\s*1\s*l(itre|iter|tr)?": "Amul Milk 1L",
        r"(?i)amul\s*milk\s*500\s*m(l|illilitre)?": "Amul Milk 500ml",

        # Atta
        r"(?i)aashirvaad\s*atta\s*5\s*kg": "Aashirvaad Atta 5kg",
        r"(?i)aashirvaad\s*atta\s*10\s*kg": "Aashirvaad Atta 10kg",

        # Common short forms
        r"(?i)^bread$": "Bread",
        r"(?i)^eggs?\s*\(?\s*12\s*\)?$": "Eggs (12)",
        r"(?i)^eggs?\s*\(?\s*6\s*\)?$": "Eggs (6)",
    }

    for pattern, replacement in product_fixes.items():
        df["product"] = df["product"].str.replace(
            pattern, replacement, regex=True
        )

    # Replace blanks
    df["product"] = df["product"].replace(
        ["", "Nan", "None", "Null", "N/A", "Na", "-"],
        np.nan
    )

    nulls = df["product"].isna().sum()
    if nulls > 0:
        log.append(f"⚠️ {nulls} rows have missing product name")

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 8 — CLEAN CATEGORY COLUMN
# ══════════════════════════════════════════════════════════════

def step8_clean_category_column(df, log):
    if "category" not in df.columns:
        return df, log

    category_map = {
        # Grains & Staples
        "grains":          "Grains & Staples",
        "grain":           "Grains & Staples",
        "staples":         "Grains & Staples",
        "staple":          "Grains & Staples",
        "rice":            "Grains & Staples",
        "wheat":           "Grains & Staples",
        "pulses":          "Grains & Staples",
        "dal":             "Grains & Staples",
        "flour":           "Grains & Staples",
        "atta":            "Grains & Staples",
        "cereals":         "Grains & Staples",

        # Dairy
        "dairy":           "Dairy",
        "milk":            "Dairy",
        "milk products":   "Dairy",
        "dairy products":  "Dairy",
        "curd":            "Dairy",
        "paneer":          "Dairy",
        "butter":          "Dairy",
        "cheese":          "Dairy",

        # Beverages
        "beverages":       "Beverages",
        "beverage":        "Beverages",
        "drinks":          "Beverages",
        "drink":           "Beverages",
        "cold drink":      "Beverages",
        "soft drink":      "Beverages",
        "soft drinks":     "Beverages",
        "juice":           "Beverages",
        "juices":          "Beverages",
        "water":           "Beverages",

        # Snacks
        "snacks":          "Snacks",
        "snack":           "Snacks",
        "biscuits":        "Snacks",
        "biscuit":         "Snacks",
        "chips":           "Snacks",
        "namkeen":         "Snacks",
        "wafers":          "Snacks",
        "cookies":         "Snacks",
        "chocolate":       "Snacks",
        "sweets":          "Snacks",
        "confectionery":   "Snacks",

        # Fresh Produce
        "vegetables":      "Fresh Produce",
        "vegetable":       "Fresh Produce",
        "fruits":          "Fresh Produce",
        "fruit":           "Fresh Produce",
        "fresh":           "Fresh Produce",
        "fresh produce":   "Fresh Produce",
        "produce":         "Fresh Produce",
        "greens":          "Fresh Produce",

        # Bakery
        "bakery":          "Bakery",
        "bread":           "Bakery",
        "buns":            "Bakery",
        "cakes":           "Bakery",
        "rusk":            "Bakery",

        # Personal Care
        "personal care":   "Personal Care",
        "toiletries":      "Personal Care",
        "soap":            "Personal Care",
        "shampoo":         "Personal Care",
        "hair care":       "Personal Care",
        "skin care":       "Personal Care",
        "beauty":          "Personal Care",
        "cosmetics":       "Personal Care",
        "hygiene":         "Personal Care",
        "sanitary":        "Personal Care",

        # Cleaning
        "cleaning":        "Cleaning Products",
        "household":       "Cleaning Products",
        "detergent":       "Cleaning Products",
        "cleaning products": "Cleaning Products",
        "floor cleaner":   "Cleaning Products",
        "phenyl":          "Cleaning Products",
        "dishwash":        "Cleaning Products",

        # Baby Care
        "baby":            "Baby Care",
        "baby care":       "Baby Care",
        "diapers":         "Baby Care",
        "baby food":       "Baby Care",

        # Frozen Food
        "frozen":          "Frozen Food",
        "frozen food":     "Frozen Food",
        "ice cream":       "Frozen Food",

        # Oils & Condiments
        "oil":             "Oils & Condiments",
        "oils":            "Oils & Condiments",
        "cooking oil":     "Oils & Condiments",
        "condiments":      "Oils & Condiments",
        "spices":          "Oils & Condiments",
        "masala":          "Oils & Condiments",
        "pickle":          "Oils & Condiments",
        "sauce":           "Oils & Condiments",
        "ketchup":         "Oils & Condiments",

        # Eggs & Meat
        "eggs":            "Eggs & Meat",
        "egg":             "Eggs & Meat",
        "meat":            "Eggs & Meat",
        "chicken":         "Eggs & Meat",
        "fish":            "Eggs & Meat",
        "seafood":         "Eggs & Meat",

        # Stationery
        "stationery":      "Stationery",
        "stationary":      "Stationery",
        "books":           "Stationery",
        "notebooks":       "Stationery",
    }

    before = df["category"].nunique()

    df["category"] = (
        df["category"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map(lambda x: category_map.get(x, x.title() if isinstance(x, str) else "Uncategorized"))
    )

    # Replace blanks
    df["category"] = df["category"].replace(
        ["", "Nan", "None", "Null", "N/A", "Na", "-"],
        "Uncategorized"
    )

    after = df["category"].nunique()
    log.append(
        f"Standardized 'category' column: {before} → {after} unique categories"
    )

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 9 — CLEAN QUANTITY COLUMN
# ══════════════════════════════════════════════════════════════

def step9_clean_quantity_column(df, log):
    if "quantity" not in df.columns:
        log.append("⚠️ 'quantity' column not found — Product dashboard needs it")
        return df, log

    df["quantity"] = (
        df["quantity"]
        .astype(str)
        .str.strip()
        # Remove units like "5 pcs", "3 kg", "2 nos"
        .str.replace(r"(?i)\s*(pcs|pieces|units|nos|kg|gm|g|ltr|l|ml|dozen|dz)$", "", regex=True)
        .str.strip()
        # Remove commas
        .str.replace(",", "", regex=False)
    )

    df["quantity"] = df["quantity"].replace(
        ["", "nan", "none", "null", "n/a", "na", "-", "--", "nil"],
        np.nan
    )

    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")

    # Negative quantity → positive (return entries)
    neg = (df["quantity"] < 0).sum()
    if neg > 0:
        df["quantity"] = df["quantity"].abs()
        log.append(f"Converted {neg} negative quantities to positive")

    # Fractional quantities — round to 3 decimal places
    df["quantity"] = df["quantity"].round(3)

    nulls = df["quantity"].isna().sum()
    if nulls > 0:
        df["quantity"] = df["quantity"].fillna(0)
        log.append(f"Fixed {nulls} invalid quantity values → set to 0")

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 10 — CLEAN PRICE COLUMNS (unit_price, cost_price)
# ══════════════════════════════════════════════════════════════

def step10_clean_price_columns(df, log):
    price_cols = [c for c in ["unit_price", "cost_price"] if c in df.columns]

    for col in price_cols:
        df[col] = clean_currency_field(df[col])

        # Negative price → make positive
        neg = (df[col] < 0).sum()
        if neg > 0:
            df[col] = df[col].abs()
            log.append(f"Converted {neg} negative values in '{col}' to positive")

        # Price of 0 — flag it
        zeros = (df[col] == 0).sum()
        if zeros > 0:
            log.append(
                f"⚠️ {zeros} zero prices in '{col}' — "
                f"may be free samples or entry errors"
            )

        nulls = df[col].isna().sum()
        if nulls > 0:
            df[col] = df[col].fillna(0)
            log.append(f"Fixed {nulls} invalid values in '{col}' → set to 0")

    if price_cols:
        log.append(f"Cleaned price columns: {', '.join(price_cols)}")

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 11 — CLEAN AMOUNT COLUMNS (total_amount, cost_amount, expense_amount)
# ══════════════════════════════════════════════════════════════

def step11_clean_amount_columns(df, log):
    amount_cols = [
        c for c in ["total_amount", "cost_amount", "expense_amount"]
        if c in df.columns
    ]

    for col in amount_cols:
        df[col] = clean_currency_field(df[col])

        # Negative total_amount = return/refund — keep but flag
        if col == "total_amount":
            neg = (df[col] < 0).sum()
            if neg > 0:
                log.append(
                    f"⚠️ {neg} negative values in 'total_amount' — "
                    f"possible returns/refunds (kept as-is)"
                )
        else:
            neg = (df[col] < 0).sum()
            if neg > 0:
                df[col] = df[col].abs()
                log.append(f"Converted {neg} negative values in '{col}' to positive")

        nulls = df[col].isna().sum()
        if nulls > 0:
            df[col] = df[col].fillna(0)
            log.append(f"Fixed {nulls} invalid values in '{col}' → set to 0")

    if amount_cols:
        log.append(f"Cleaned amount columns: {', '.join(amount_cols)}")

    return df, log


def clean_currency_field(series):
    """Remove all currency symbols, words, formatting from a price/amount column."""
    s = series.astype(str).str.strip()

    # Remove currency words (case-insensitive)
    currency_words = [
        r"(?i)rupees?\s*",
        r"(?i)rs\.?\s*",
        r"(?i)inr\.?\s*",
        r"(?i)usd\.?\s*",
        r"(?i)eur\.?\s*",
        r"(?i)gbp\.?\s*",
        r"(?i)dollar\s*",
        r"(?i)euro\s*",
    ]
    for pattern in currency_words:
        s = s.str.replace(pattern, "", regex=True)

    # Remove currency symbols
    s = s.str.replace(r"[₹$€£¥₩]", "", regex=True)

    # Remove Indian/international comma formatting
    s = s.str.replace(",", "", regex=False)

    # Remove trailing /- (Indian style: 150/-)
    s = s.str.replace(r"/-$", "", regex=True)
    s = s.str.replace(r"/", "", regex=False)

    # Convert (500) → -500 (accounting format)
    s = s.str.replace(r"^\((\d+\.?\d*)\)$", r"-\1", regex=True)

    # Strip leftover spaces
    s = s.str.strip()

    # Replace non-numeric text
    s = s.replace(
        ["", "nan", "none", "null", "n/a", "na",
         "-", "--", "nil", "Nil", "NIL",
         "free", "Free", "FREE",
         "complimentary", "Complimentary"],
        np.nan
    )

    return pd.to_numeric(s, errors="coerce")


# ══════════════════════════════════════════════════════════════
# STEP 12 — CLEAN CUSTOMER ID
# ══════════════════════════════════════════════════════════════

def step12_clean_customer_id(df, log):
    if "customer_id" not in df.columns:
        return df, log

    def clean_cust_id(val):
        s = safe_str(val)
        if s is None:
            return np.nan

        # Remove formatting from phone numbers
        s = re.sub(r"[\s\-\(\)\+\.]", "", s).upper()

        # Must be a non-empty string before regex matching
        if not s:
            return np.nan

        # Strip Indian country code 91
        if re.match(r"^91\d{10}$", s):
            s = s[2:]

        # Strip leading 0
        if re.match(r"^0\d{10}$", s):
            s = s[1:]

        if s in ("", "NAN", "NONE", "NULL", "N/A", "NA", "-", "0"):
            return np.nan

        return s

    df["customer_id"] = df["customer_id"].apply(clean_cust_id)

    nulls = df["customer_id"].isna().sum()
    if nulls > 0:
        log.append(f"⚠️ {nulls} missing customer IDs")
    else:
        log.append("Cleaned 'customer_id' column — Customer dashboard ready")

    return df, log

# ══════════════════════════════════════════════════════════════
# STEP 13 — CLEAN PAYMENT MODE
# ══════════════════════════════════════════════════════════════

def step13_clean_payment_mode(df, log):
    if "payment_mode" not in df.columns:
        return df, log

    payment_map = {
        # UPI variants
        "upi":             "UPI",
        "gpay":            "UPI",
        "google pay":      "UPI",
        "phonepe":         "UPI",
        "phone pe":        "UPI",
        "paytm":           "UPI",
        "bhim":            "UPI",
        "bhim upi":        "UPI",
        "qr":              "UPI",
        "qr code":         "UPI",
        "scan & pay":      "UPI",
        "scan and pay":    "UPI",

        # Cash variants
        "cash":            "Cash",
        "c":               "Cash",
        "csh":             "Cash",
        "by cash":         "Cash",
        "hand cash":       "Cash",
        "currency":        "Cash",

        # Card variants
        "card":            "Card",
        "debit card":      "Card",
        "credit card":     "Card",
        "debit":           "Card",
        "credit":          "Card",
        "swipe":           "Card",
        "pos":             "Card",
        "netbanking":      "Card",
        "net banking":     "Card",
        "neft":            "Card",
        "imps":            "Card",
        "visa":            "Card",
        "mastercard":      "Card",
        "rupay":           "Card",

        # EMI
        "emi":             "EMI",
        "no cost emi":     "EMI",

        # Wallet
        "wallet":          "Wallet",
        "mobikwik":        "Wallet",
        "freecharge":      "Wallet",
        "amazon pay":      "Wallet",
    }

    before = df["payment_mode"].nunique()

    df["payment_mode"] = (
        df["payment_mode"]
        .astype(str)
        .str.strip()
        .str.lower()
        .map(lambda x: payment_map.get(x, x.title() if isinstance(x, str) else "Unknown"))
    )

    df["payment_mode"] = df["payment_mode"].replace(
        ["", "Nan", "None", "Null", "N/A", "Na", "-"],
        "Unknown"
    )

    after = df["payment_mode"].nunique()
    log.append(
        f"Standardized 'payment_mode': {before} → {after} unique payment types"
    )

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 14 — CLEAN STOCK COLUMNS
# ══════════════════════════════════════════════════════════════

def step14_clean_stock_columns(df, log):
    stock_cols = [c for c in ["stock_qty", "reorder_point"] if c in df.columns]

    for col in stock_cols:
        df[col] = (
            df[col].astype(str)
            .str.replace(r"(?i)\s*(pcs|pieces|units|nos|kg|gm|g|ltr|l|ml)$", "", regex=True)
            .str.replace(",", "", regex=False)
            .str.strip()
        )

        df[col] = df[col].replace(
            ["", "nan", "none", "null", "n/a", "na", "-"],
            np.nan
        )

        df[col] = pd.to_numeric(df[col], errors="coerce")

        # Negative stock — flag it
        if col == "stock_qty":
            neg = (df[col] < 0).sum()
            if neg > 0:
                log.append(
                    f"⚠️ {neg} negative stock quantities — "
                    f"possible overselling or data entry errors"
                )

        nulls = df[col].isna().sum()
        if nulls > 0:
            df[col] = df[col].fillna(0)
            log.append(f"Fixed {nulls} invalid values in '{col}' → set to 0")

    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 15 — CLEAN EXPIRY DATE
# ══════════════════════════════════════════════════════════════

def step15_clean_expiry_date(df, log):
    if "expiry_date" not in df.columns:
        return df, log

    df["expiry_date"] = df["expiry_date"].apply(parse_any_date)

    today = pd.Timestamp(datetime.today().date())

    if pd.api.types.is_datetime64_any_dtype(df["expiry_date"]):
        expired = (df["expiry_date"] < today).sum()
        if expired > 0:
            log.append(
                f"⚠️ {expired} products already EXPIRED — "
                f"check Inventory dashboard immediately!"
            )

        expiring_soon = (
            (df["expiry_date"] >= today) &
            (df["expiry_date"] <= today + pd.Timedelta(days=30))
        ).sum()
        if expiring_soon > 0:
            log.append(
                f"⚠️ {expiring_soon} products expiring within 30 days"
            )

    log.append("Parsed 'expiry_date' column — Inventory dashboard ready")
    return df, log


# ══════════════════════════════════════════════════════════════
# STEP 16 — REMOVE INVALID ROWS (final pass)
# ══════════════════════════════════════════════════════════════

def step16_remove_invalid_rows(df, log):
    before = len(df)

    # Remove rows with no product name
    if "product" in df.columns:
        df = df[~df["product"].isin([np.nan, "", "Unknown", "Nan", "None"])]

    # Remove rows with zero quantity
    if "quantity" in df.columns:
        zero_qty = (df["quantity"] == 0).sum()
        if zero_qty > 0:
            df = df[df["quantity"] != 0]
            log.append(f"Removed {zero_qty} rows with zero quantity")

    # Remove rows with zero total_amount
    if "total_amount" in df.columns:
        zero_amt = (df["total_amount"] == 0).sum()
        if zero_amt > 0:
            df = df[df["total_amount"] != 0]
            log.append(f"Removed {zero_amt} rows with zero total amount")

    # Remove rows with no date
    if "date" in df.columns:
        no_date = df["date"].isna().sum()
        if no_date > 0:
            df = df[df["date"].notna()]
            log.append(f"Removed {no_date} rows with unparseable dates")

    removed = before - len(df)
    if removed > 0:
        log.append(f"Total invalid rows removed in final cleanup: {removed}")

    return df, log
# ══════════════════════════════════════════════════════════════
# SAVE TO DATABASE
# ══════════════════════════════════════════════════════════════

def save_to_database(
    db: Session,
    user_id: int,
    df: pd.DataFrame,
    file_name: str,
    original_rows: int,
    cleaned_rows: int,
    removed_rows: int,
    cleaning_log: list
) -> int:
    try:
        # ── Save upload history first ─────────────────────────
        upload = UploadHistory(
            user_id       = user_id,
            file_name     = file_name,
            original_rows = original_rows,
            cleaned_rows  = cleaned_rows,
            removed_rows  = removed_rows,
            status        = "success",
            cleaning_log  = json.dumps(cleaning_log)
        )
        db.add(upload)
        db.flush()

        # ── Save each row to sales_data ───────────────────────
        rows_to_insert = []
        for _, row in df.iterrows():
            def get_float(col):
                val = row.get(col)
                try:
                    return float(val) if val is not None and pd.notna(val) else None
                except:
                    return None

            def get_str(col):
                val = row.get(col)
                try:
                    return str(val) if val is not None and pd.notna(val) else None
                except:
                    return None

            def get_date(col):
                val = row.get(col)
                if val is None:
                    return None
                try:
                    if pd.isna(val):
                        return None
                    return pd.Timestamp(val).date()
                except:
                    return None

            sales_row = SalesData(
                user_id        = user_id,
                upload_id      = upload.id,
                date           = get_date("date"),
                time           = get_str("time"),
                invoice_number = get_str("invoice_number"),
                product        = get_str("product"),
                category       = get_str("category"),
                quantity       = get_float("quantity"),
                unit_price     = get_float("unit_price"),
                total_amount   = get_float("total_amount"),
                cost_price     = get_float("cost_price"),
                customer_id    = get_str("customer_id"),
                payment_mode   = get_str("payment_mode"),
                stock_qty      = get_float("stock_qty"),
                expense_type   = get_str("expense_type"),
                expense_amount = get_float("expense_amount"),
            )
            rows_to_insert.append(sales_row)

        db.bulk_save_objects(rows_to_insert)
        db.commit()
        print(f"✅ Saved {len(rows_to_insert)} rows to Supabase for user {user_id}")
        return upload.id

    except Exception as e:
        db.rollback()
        print(f"❌ Database save error: {e}")
        return None