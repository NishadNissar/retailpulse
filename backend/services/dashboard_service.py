from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case
from models.user import SalesData
from datetime import datetime, timedelta
import pandas as pd


def get_user_df(db: Session, user_id: int) -> pd.DataFrame:
    """Load all sales data for a user into a DataFrame."""
    rows = db.query(SalesData).filter(SalesData.user_id == user_id).all()
    if not rows:
        return pd.DataFrame()

    data = []
    for r in rows:
        data.append({
            "date":           r.date,
            "time":           r.time,
            "invoice_number": r.invoice_number,
            "product":        r.product,
            "category":       r.category,
            "quantity":       r.quantity,
            "unit_price":     r.unit_price,
            "total_amount":   r.total_amount,
            "cost_price":     r.cost_price,
            "customer_id":    r.customer_id,
            "payment_mode":   r.payment_mode,
            "stock_qty":      r.stock_qty,
            "expense_amount": r.expense_amount,
            "cost_amount":    r.cost_amount,
        })
    df = pd.DataFrame(data)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


# ══════════════════════════════════════════════════════════════
# 1. SALES DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_sales_data(db: Session, user_id: int, period: str = "all") -> dict:
    df = get_user_df(db, user_id)

    if df.empty:
        return {"status": "no_data", "message": "No sales data found. Upload a file first."}

    # ── Filter by Period ──────────────────────────────────────
    if period != "all" and "date" in df.columns and not df["date"].isna().all():
        max_date = df["date"].max()
        if period == "today":
            df = df[df["date"].dt.date == max_date.date()]
        elif period == "7days":
            df = df[df["date"] >= (max_date - timedelta(days=6))]
        elif period == "30days":
            df = df[df["date"] >= (max_date - timedelta(days=29))]
        elif period == "365days":
            df = df[df["date"] >= (max_date - timedelta(days=364))]

    if df.empty:
        return {"status": "no_data", "message": f"No sales data found for the selected period ({period})."}

    # ── KPIs ──────────────────────────────────────────────────
    total_revenue    = float(df["total_amount"].sum())
    total_cost       = float(df["cost_price"].fillna(0).multiply(df["quantity"].fillna(0)).sum())
    total_profit     = total_revenue - total_cost
    profit_margin    = round((total_profit / total_revenue * 100), 2) if total_revenue > 0 else 0
    total_orders     = df["invoice_number"].nunique() if "invoice_number" in df.columns else len(df)
    avg_order_value  = round(total_revenue / total_orders, 2) if total_orders > 0 else 0

    # ── Revenue by date ───────────────────────────────────────
    daily = (
        df.groupby(df["date"].dt.date)["total_amount"]
        .sum()
        .reset_index()
        .rename(columns={"date": "date", "total_amount": "revenue"})
        .sort_values("date")
    )
    daily["date"] = daily["date"].astype(str)

    # ── Revenue by month ──────────────────────────────────────
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = (
        df.groupby("month")["total_amount"]
        .sum()
        .reset_index()
        .rename(columns={"total_amount": "revenue"})
        .sort_values("month")
    )

    # ── Payment mode split ────────────────────────────────────
    payment_split = {}
    if "payment_mode" in df.columns:
        payment_split = (
            df.groupby("payment_mode")["total_amount"]
            .sum()
            .round(2)
            .to_dict()
        )

    # ── Revenue by day of week ────────────────────────────────
    df["day_of_week"] = df["date"].dt.day_name()
    day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    dow = (
        df.groupby("day_of_week")["total_amount"]
        .sum()
        .reindex(day_order, fill_value=0)
        .round(2)
        .to_dict()
    )

    return {
        "status": "success",
        "kpis": {
            "total_revenue":   round(total_revenue, 2),
            "total_profit":    round(total_profit, 2),
            "profit_margin":   profit_margin,
            "total_orders":    total_orders,
            "avg_order_value": avg_order_value,
        },
        "daily_revenue":   daily.to_dict(orient="records"),
        "monthly_revenue": monthly.to_dict(orient="records"),
        "payment_split":   payment_split,
        "revenue_by_day":  dow,
    }


# ══════════════════════════════════════════════════════════════
# 2. PRODUCTS DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_products_data(db: Session, user_id: int) -> dict:
    df = get_user_df(db, user_id)

    if df.empty:
        return {"status": "no_data", "message": "No data found. Upload a file first."}

    if "product" not in df.columns:
        return {"status": "no_data", "message": "No product column found in your data."}

    # ── Top 10 products by revenue ────────────────────────────
    top_revenue = (
        df.groupby("product")["total_amount"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .round(2)
        .reset_index()
        .rename(columns={"total_amount": "revenue"})
    )

    # ── Top 10 products by quantity ───────────────────────────
    top_quantity = (
        df.groupby("product")["quantity"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .round(2)
        .reset_index()
    )

    # ── Revenue by category ───────────────────────────────────
    category_revenue = {}
    if "category" in df.columns:
        category_revenue = (
            df.groupby("category")["total_amount"]
            .sum()
            .round(2)
            .sort_values(ascending=False)
            .to_dict()
        )

    # ── Profit margin per product ─────────────────────────────
    margin_data = []
    if "cost_price" in df.columns:
        prod_df = df.groupby("product").agg(
            revenue=("total_amount", "sum"),
            cost=("cost_price", "mean"),
            qty=("quantity", "sum")
        ).reset_index()
        prod_df["total_cost"]  = prod_df["cost"] * prod_df["qty"]
        prod_df["profit"]      = prod_df["revenue"] - prod_df["total_cost"]
        prod_df["margin_pct"]  = (prod_df["profit"] / prod_df["revenue"] * 100).round(2)
        prod_df = prod_df.sort_values("margin_pct", ascending=False).head(10)
        margin_data = prod_df[["product", "revenue", "profit", "margin_pct"]].round(2).to_dict(orient="records")

    # ── Category quantity ─────────────────────────────────────
    category_qty = {}
    if "category" in df.columns:
        category_qty = (
            df.groupby("category")["quantity"]
            .sum()
            .round(2)
            .sort_values(ascending=False)
            .to_dict()
        )

    return {
        "status":           "success",
        "top_by_revenue":   top_revenue.to_dict(orient="records"),
        "top_by_quantity":  top_quantity.to_dict(orient="records"),
        "category_revenue": category_revenue,
        "category_qty":     category_qty,
        "margin_analysis":  margin_data,
    }


# ══════════════════════════════════════════════════════════════
# 3. CUSTOMERS DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_customers_data(db: Session, user_id: int) -> dict:
    df = get_user_df(db, user_id)

    if df.empty:
        return {"status": "no_data", "message": "No data found. Upload a file first."}

    if "customer_id" not in df.columns:
        return {"status": "no_data", "message": "No customer_id column found."}

    df = df[df["customer_id"].notna()]

    # ── Total unique customers ────────────────────────────────
    total_customers = df["customer_id"].nunique()

    # ── Top customers by spend ────────────────────────────────
    top_customers = (
        df.groupby("customer_id")["total_amount"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .round(2)
        .reset_index()
        .rename(columns={"total_amount": "total_spend"})
    )

    # ── Visit frequency ───────────────────────────────────────
    visit_freq = (
        df.groupby("customer_id")["date"]
        .nunique()
        .value_counts()
        .sort_index()
        .reset_index()
        .rename(columns={"date": "visits", "count": "customers"})
    )

    # ── Average basket size ───────────────────────────────────
    basket = df.groupby("invoice_number")["total_amount"].sum() if "invoice_number" in df.columns else df.groupby("customer_id")["total_amount"].mean()
    avg_basket = round(float(basket.mean()), 2)

    # ── New vs returning ──────────────────────────────────────
    cust_visits = df.groupby("customer_id")["date"].nunique()
    new_customers      = int((cust_visits == 1).sum())
    returning_customers = int((cust_visits > 1).sum())

    # ── Revenue by customer segment ───────────────────────────
    cust_spend = df.groupby("customer_id")["total_amount"].sum()
    high_value  = int((cust_spend > cust_spend.quantile(0.75)).sum())
    mid_value   = int(((cust_spend >= cust_spend.quantile(0.25)) & (cust_spend <= cust_spend.quantile(0.75))).sum())
    low_value   = int((cust_spend < cust_spend.quantile(0.25)).sum())

    return {
        "status":              "success",
        "total_customers":     total_customers,
        "avg_basket_size":     avg_basket,
        "new_customers":       new_customers,
        "returning_customers": returning_customers,
        "top_customers":       top_customers.to_dict(orient="records"),
        "visit_frequency":     visit_freq.to_dict(orient="records"),
        "segments": {
            "high_value": high_value,
            "mid_value":  mid_value,
            "low_value":  low_value,
        }
    }


# ══════════════════════════════════════════════════════════════
# 4. INVENTORY DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_inventory_data(db: Session, user_id: int) -> dict:
    df = get_user_df(db, user_id)

    if df.empty:
        return {"status": "no_data", "message": "No data found. Upload a file first."}

    # ── Most sold products (need restock) ─────────────────────
    top_sold = (
        df.groupby("product")["quantity"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
        .round(2)
        .reset_index()
        .rename(columns={"quantity": "units_sold"})
    )

    # ── Category stock movement ───────────────────────────────
    category_movement = {}
    if "category" in df.columns:
        category_movement = (
            df.groupby("category")["quantity"]
            .sum()
            .round(2)
            .sort_values(ascending=False)
            .to_dict()
        )

    # ── Products with low sales (slow moving) ─────────────────
    slow_moving = (
        df.groupby("product")["quantity"]
        .sum()
        .sort_values(ascending=True)
        .head(10)
        .round(2)
        .reset_index()
        .rename(columns={"quantity": "units_sold"})
    )

    # ── Daily quantity sold trend ─────────────────────────────
    daily_qty = (
        df.groupby(df["date"].dt.date)["quantity"]
        .sum()
        .reset_index()
        .rename(columns={"date": "date", "quantity": "units_sold"})
        .sort_values("date")
    )
    daily_qty["date"] = daily_qty["date"].astype(str)

    # ── Capital locked (cost * qty) ───────────────────────────
    capital_locked = 0
    if "cost_price" in df.columns:
        df["capital"] = df["cost_price"].fillna(0) * df["quantity"].fillna(0)
        capital_locked = round(float(df["capital"].sum()), 2)

    return {
        "status":             "success",
        "top_selling":        top_sold.to_dict(orient="records"),
        "slow_moving":        slow_moving.to_dict(orient="records"),
        "category_movement":  category_movement,
        "daily_qty_trend":    daily_qty.to_dict(orient="records"),
        "capital_locked":     capital_locked,
    }


# ══════════════════════════════════════════════════════════════
# 5. STAFF & OPS DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_staff_data(db: Session, user_id: int) -> dict:
    df = get_user_df(db, user_id)

    if df.empty:
        return {"status": "no_data", "message": "No data found. Upload a file first."}

    if "time" not in df.columns:
        return {"status": "no_data", "message": "No time column found. Add Time to your Excel."}

    df = df[df["time"].notna()]

    # ── Extract hour ──────────────────────────────────────────
    def extract_hour(t):
        try:
            return int(str(t).split(":")[0])
        except Exception:
            return None

    df["hour"] = df["time"].apply(extract_hour)
    df = df[df["hour"].notna()]

    # ── Transactions per hour ─────────────────────────────────
    txn_per_hour = (
        df.groupby("hour")["invoice_number"]
        .nunique()
        .reindex(range(6, 23), fill_value=0)
        .reset_index()
        .rename(columns={"invoice_number": "transactions"})
    ) if "invoice_number" in df.columns else pd.DataFrame()

    # ── Revenue per hour ──────────────────────────────────────
    rev_per_hour = (
        df.groupby("hour")["total_amount"]
        .sum()
        .reindex(range(6, 23), fill_value=0)
        .round(2)
        .reset_index()
        .rename(columns={"total_amount": "revenue"})
    )

    # ── Peak hours ────────────────────────────────────────────
    peak = rev_per_hour.sort_values("revenue", ascending=False).head(3)
    peak_hours = peak["hour"].tolist()

    # ── Day × Hour heatmap ────────────────────────────────────
    df["day_of_week"] = df["date"].dt.day_name()
    heatmap = (
        df.groupby(["day_of_week", "hour"])["total_amount"]
        .sum()
        .round(2)
        .reset_index()
        .rename(columns={"total_amount": "revenue"})
    )

    return {
        "status":           "success",
        "txn_per_hour":     txn_per_hour.to_dict(orient="records") if not txn_per_hour.empty else [],
        "revenue_per_hour": rev_per_hour.to_dict(orient="records"),
        "peak_hours":       peak_hours,
        "heatmap":          heatmap.to_dict(orient="records"),
    }


# ══════════════════════════════════════════════════════════════
# 6. BUSINESS HEALTH DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_health_data(db: Session, user_id: int) -> dict:
    df = get_user_df(db, user_id)

    if df.empty:
        return {"status": "no_data", "message": "No data found. Upload a file first."}

    # ── Monthly revenue trend ─────────────────────────────────
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = (
        df.groupby("month")["total_amount"]
        .sum()
        .round(2)
        .reset_index()
        .rename(columns={"total_amount": "revenue"})
        .sort_values("month")
    )

    # ── Month over month growth ───────────────────────────────
    monthly["prev_revenue"] = monthly["revenue"].shift(1)
    monthly["growth_pct"] = (
        (monthly["revenue"] - monthly["prev_revenue"])
        / monthly["prev_revenue"] * 100
    ).round(2)
    monthly = monthly.drop(columns=["prev_revenue"])
    monthly["growth_pct"] = monthly["growth_pct"].fillna(0)

    # ── Revenue vs Cost waterfall ─────────────────────────────
    total_revenue = round(float(df["total_amount"].sum()), 2)
    total_cost    = 0
    if "cost_price" in df.columns:
        total_cost = round(
            float(df["cost_price"].fillna(0).multiply(df["quantity"].fillna(0)).sum()), 2
        )
    gross_profit  = round(total_revenue - total_cost, 2)

    # ── Best and worst months ─────────────────────────────────
    best_month  = monthly.loc[monthly["revenue"].idxmax()].to_dict() if not monthly.empty else {}
    worst_month = monthly.loc[monthly["revenue"].idxmin()].to_dict() if not monthly.empty else {}

    # ── Category health ───────────────────────────────────────
    category_health = {}
    if "category" in df.columns:
        category_health = (
            df.groupby("category")["total_amount"]
            .sum()
            .round(2)
            .sort_values(ascending=False)
            .to_dict()
        )

    # ── Overall health score (simple) ─────────────────────────
    profit_margin = round((gross_profit / total_revenue * 100), 2) if total_revenue > 0 else 0
    if profit_margin > 30:
        health_score = "Excellent 🟢"
    elif profit_margin > 20:
        health_score = "Good 🟡"
    elif profit_margin > 10:
        health_score = "Average 🟠"
    else:
        health_score = "Needs Attention 🔴"

    return {
        "status":          "success",
        "monthly_trend":   monthly.to_dict(orient="records"),
        "waterfall": {
            "total_revenue": total_revenue,
            "total_cost":    total_cost,
            "gross_profit":  gross_profit,
            "profit_margin": profit_margin,
        },
        "best_month":      best_month,
        "worst_month":     worst_month,
        "category_health": category_health,
        "health_score":    health_score,
    }