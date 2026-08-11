from sqlalchemy.orm import Session
from models.user import SalesData
from datetime import datetime, timedelta, date as _date
import pandas as pd


def get_user_df(db: Session, user_id: int) -> pd.DataFrame:
    """Load all sales data for a user into a DataFrame."""
    rows = db.query(SalesData).filter(SalesData.user_id == user_id).all()
    if not rows:
        return pd.DataFrame()

    data = []
    for r in rows:
        data.append({
            "upload_date":    r.upload_date,
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
        })
    df = pd.DataFrame(data)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "upload_date" in df.columns:
        df["upload_date"] = pd.to_datetime(df["upload_date"], errors="coerce")
    return df


# ══════════════════════════════════════════════════════════════
# PERIOD FILTER — used by ALL dashboards
# ══════════════════════════════════════════════════════════════

def _filter_by_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    """
    Filter dataframe by period safely.
      today    → rows where upload_date == today, or fallback to date == today, or all data
      7days    → last 7 days of sale dates
      30days   → last 30 days of sale dates
      365days  → last 365 days of sale dates
      all      → no filter
    """
    if df.empty or period == "all":
        return df

    today = pd.Timestamp(_date.today())

    if period == "today":
        if "upload_date" in df.columns and not df["upload_date"].isna().all():
            todays_upload = df[df["upload_date"].dt.date == today.date()]
            if not todays_upload.empty:
                return todays_upload

        if "date" in df.columns and not df["date"].isna().all():
            todays_sales = df[df["date"].dt.date == today.date()]
            if not todays_sales.empty:
                return todays_sales

        # Fallback if no specific data for "today": return all uploaded data
        return df

    if "date" not in df.columns or df["date"].isna().all():
        return df

    filtered_df = df
    if period == "7days":
        filtered_df = df[df["date"] >= (today - timedelta(days=6))]
    elif period == "30days":
        filtered_df = df[df["date"] >= (today - timedelta(days=29))]
    elif period == "365days":
        filtered_df = df[df["date"] >= (today - timedelta(days=364))]

    # Fallback if range filter leaves empty dataframe (e.g. historical data)
    if filtered_df.empty:
        return df

    return filtered_df


def _no_data_response(period: str, msg: str = None) -> dict:
    if msg:
        return {"status": "no_data", "message": msg}
    if period == "today":
        return {"status": "no_data", "message": "No data for today — upload your file to see today's dashboard."}
    return {"status": "no_data", "message": f"No data found for the selected period ({period})."}


# ══════════════════════════════════════════════════════════════
# 1. SALES DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_sales_data(db: Session, user_id: int, period: str = "today") -> dict:
    df = get_user_df(db, user_id)
    if df.empty:
        return _no_data_response(period, "No sales data found. Upload a file first.")

    df = _filter_by_period(df, period)
    if df.empty:
        return _no_data_response(period)

    total_revenue    = float(df["total_amount"].fillna(0).sum())
    total_cost       = float(df["cost_price"].fillna(0).multiply(df["quantity"].fillna(0)).sum())
    total_profit     = total_revenue - total_cost
    profit_margin    = round((total_profit / total_revenue * 100), 2) if total_revenue > 0 else 0
    total_orders     = df["invoice_number"].nunique() if "invoice_number" in df.columns else len(df)
    avg_order_value  = round(total_revenue / total_orders, 2) if total_orders > 0 else 0

    df["cost_row"] = df["cost_price"].fillna(0) * df["quantity"].fillna(0)
    df_date = df[df["date"].notna()].copy() if "date" in df.columns else pd.DataFrame()

    if not df_date.empty:
        daily = (
            df_date.groupby(df_date["date"].dt.date).agg(
                revenue=("total_amount", "sum"),
                cost=("cost_row", "sum")
            ).reset_index().sort_values("date")
        )
        daily["revenue"] = daily["revenue"].round(2)
        daily["profit"]  = (daily["revenue"] - daily["cost"]).round(2)
        daily["date"]    = daily["date"].astype(str)

        monthly = (
            df_date.groupby(df_date["date"].dt.strftime("%Y-%m"))["total_amount"].sum().reset_index()
            .rename(columns={"date": "month", "total_amount": "revenue"}).sort_values("month")
        )

        day_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        dow = (
            df_date.groupby(df_date["date"].dt.day_name())["total_amount"].sum()
            .reindex(day_order, fill_value=0).round(2).to_dict()
        )
    else:
        daily = pd.DataFrame(columns=["date", "revenue", "profit"])
        monthly = pd.DataFrame(columns=["month", "revenue"])
        dow = {}

    category_revenue = {}
    if "category" in df.columns:
        category_revenue = df.groupby("category")["total_amount"].sum().round(2).to_dict()

    payment_split = {}
    if "payment_mode" in df.columns:
        payment_split = df.groupby("payment_mode")["total_amount"].sum().round(2).to_dict()

    return {
        "status": "success",
        "period": period,
        "kpis": {
            "total_revenue":   round(total_revenue, 2),
            "total_profit":    round(total_profit, 2),
            "profit_margin":   profit_margin,
            "total_orders":    total_orders,
            "avg_order_value": avg_order_value,
        },
        "daily_revenue":   daily.to_dict(orient="records"),
        "monthly_revenue": monthly.to_dict(orient="records"),
        "category_revenue": category_revenue,
        "payment_split":   payment_split,
        "revenue_by_day":  dow,
    }


# ══════════════════════════════════════════════════════════════
# 2. PRODUCTS DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_products_data(db: Session, user_id: int, period: str = "today") -> dict:
    df = get_user_df(db, user_id)
    if df.empty:
        return _no_data_response(period, "No data found. Upload a file first.")

    df = _filter_by_period(df, period)
    if df.empty or "product" not in df.columns:
        return _no_data_response(period)

    top_revenue = (
        df.groupby("product")["total_amount"].sum()
        .sort_values(ascending=False).head(10).round(2)
        .reset_index().rename(columns={"total_amount": "revenue"})
    )

    top_quantity = (
        df.groupby("product")["quantity"].sum()
        .sort_values(ascending=False).head(10).round(2).reset_index()
    )

    category_revenue = {}
    if "category" in df.columns:
        category_revenue = (
            df.groupby("category")["total_amount"].sum().round(2)
            .sort_values(ascending=False).to_dict()
        )

    margin_data = []
    if "cost_price" in df.columns:
        prod_df = df.groupby("product").agg(
            revenue=("total_amount", "sum"),
            cost=("cost_price", "mean"),
            qty=("quantity", "sum")
        ).reset_index()
        prod_df["total_cost"] = prod_df["cost"] * prod_df["qty"]
        prod_df["profit"]     = prod_df["revenue"] - prod_df["total_cost"]
        prod_df["margin_pct"] = (prod_df["profit"] / prod_df["revenue"] * 100).round(2)
        prod_df = prod_df.sort_values("margin_pct", ascending=False).head(10)
        margin_data = prod_df[["product","revenue","profit","margin_pct"]].round(2).to_dict(orient="records")

    category_qty = {}
    if "category" in df.columns:
        category_qty = (
            df.groupby("category")["quantity"].sum().round(2)
            .sort_values(ascending=False).to_dict()
        )

    combos_data = []
    txns = df[df["invoice_number"].notna() & (df["invoice_number"] != "")]
    if not txns.empty and "date" in df.columns and "product" in df.columns:
        df_date = df[df["date"].notna()]
        total_days = max(1, df_date["date"].dt.date.nunique()) if not df_date.empty else 1
        prod_prices = df.groupby("product")["unit_price"].mean().to_dict()
        invoice_prods = txns[["invoice_number","product"]].drop_duplicates()
        prod_counts = invoice_prods["product"].value_counts().to_dict()
        merged = pd.merge(invoice_prods, invoice_prods, on="invoice_number")
        pairs = merged[merged["product_x"] != merged["product_y"]]
        if not pairs.empty:
            pc = pairs.groupby(["product_x","product_y"]).size().reset_index(name="co_buy_count")
            pc["count_x"] = pc["product_x"].map(prod_counts)
            pc["rate"]    = (pc["co_buy_count"] / pc["count_x"] * 100).round(1)
            pc["price_y"] = pc["product_y"].map(prod_prices).fillna(0)
            pc["uplift"]  = (((pc["count_x"] - pc["co_buy_count"]) / total_days) * 0.10 * pc["price_y"]).round(0).astype(int)
            pc = pc.sort_values(by=["co_buy_count","rate"], ascending=[False, False])
            for _, row in pc.head(10).iterrows():
                combos_data.append({
                    "product_a":   str(row["product_x"]),
                    "product_b":   str(row["product_y"]),
                    "co_buy_rate": f"{int(round(row['rate']))}%",
                    "uplift":      f"₹{int(row['uplift']):,}/day uplift" if row["uplift"] > 0 else "₹0/day uplift"
                })

    return {
        "status":           "success",
        "period":           period,
        "top_by_revenue":   top_revenue.to_dict(orient="records"),
        "top_by_quantity":  top_quantity.to_dict(orient="records"),
        "category_revenue": category_revenue,
        "category_qty":     category_qty,
        "margin_analysis":  margin_data,
        "combos":           combos_data,
    }


# ══════════════════════════════════════════════════════════════
# 3. CUSTOMERS DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_customers_data(db: Session, user_id: int, period: str = "today") -> dict:
    df = get_user_df(db, user_id)
    if df.empty:
        return _no_data_response(period, "No data found. Upload a file first.")

    df = _filter_by_period(df, period)
    if df.empty:
        return _no_data_response(period)

    if "customer_id" in df.columns and df["customer_id"].notna().any():
        df_cust = df[df["customer_id"].notna()].copy()
    else:
        df_cust = df.copy()
        df_cust["customer_id"] = "Guest"

    total_customers = df_cust["customer_id"].nunique()

    top_customers = (
        df_cust.groupby("customer_id")["total_amount"].sum()
        .sort_values(ascending=False).head(10).round(2)
        .reset_index().rename(columns={"total_amount":"total_spend"})
    )

    df_date = df_cust[df_cust["date"].notna()] if "date" in df_cust.columns else pd.DataFrame()
    if not df_date.empty:
        visit_freq = (
            df_date.groupby("customer_id")["date"].nunique()
            .value_counts().sort_index().reset_index()
            .rename(columns={"date":"visits","count":"customers"})
        )
        cust_visits = df_date.groupby("customer_id")["date"].nunique()
        new_customers       = int((cust_visits == 1).sum())
        returning_customers = int((cust_visits > 1).sum())
    else:
        visit_freq = pd.DataFrame(columns=["visits", "customers"])
        new_customers = total_customers
        returning_customers = 0

    basket = df_cust.groupby("invoice_number")["total_amount"].sum() if "invoice_number" in df_cust.columns else df_cust.groupby("customer_id")["total_amount"].mean()
    avg_basket = round(float(basket.mean()), 2) if not basket.empty else 0

    cust_spend = df_cust.groupby("customer_id")["total_amount"].sum()
    high_value = int((cust_spend > cust_spend.quantile(0.75)).sum()) if len(cust_spend) > 0 else 0
    mid_value  = int(((cust_spend >= cust_spend.quantile(0.25)) & (cust_spend <= cust_spend.quantile(0.75))).sum()) if len(cust_spend) > 0 else 0
    low_value  = int((cust_spend < cust_spend.quantile(0.25)).sum()) if len(cust_spend) > 0 else 0

    return {
        "status":              "success",
        "period":              period,
        "total_customers":     total_customers,
        "avg_basket_size":     avg_basket,
        "new_customers":       new_customers,
        "returning_customers": returning_customers,
        "top_customers":       top_customers.to_dict(orient="records"),
        "visit_frequency":     visit_freq.to_dict(orient="records") if not visit_freq.empty else [],
        "segments": {"high_value": high_value, "mid_value": mid_value, "low_value": low_value}
    }


# ══════════════════════════════════════════════════════════════
# 4. INVENTORY DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_inventory_data(db: Session, user_id: int, period: str = "today") -> dict:
    df = get_user_df(db, user_id)
    if df.empty:
        return _no_data_response(period, "No data found. Upload a file first.")

    df = _filter_by_period(df, period)
    if df.empty:
        return _no_data_response(period)

    top_sold = (
        df.groupby("product")["quantity"].sum()
        .sort_values(ascending=False).head(10).round(2)
        .reset_index().rename(columns={"quantity":"units_sold"})
    ) if "product" in df.columns else pd.DataFrame(columns=["product", "units_sold"])

    category_movement = {}
    if "category" in df.columns:
        category_movement = (
            df.groupby("category")["quantity"].sum().round(2)
            .sort_values(ascending=False).to_dict()
        )

    slow_moving = (
        df.groupby("product")["quantity"].sum()
        .sort_values(ascending=True).head(10).round(2)
        .reset_index().rename(columns={"quantity":"units_sold"})
    ) if "product" in df.columns else pd.DataFrame(columns=["product", "units_sold"])

    df_date = df[df["date"].notna()].copy() if "date" in df.columns else pd.DataFrame()
    if not df_date.empty:
        daily_qty = (
            df_date.groupby(df_date["date"].dt.date)["quantity"].sum()
            .reset_index().rename(columns={"date":"date","quantity":"units_sold"})
            .sort_values("date")
        )
        daily_qty["date"] = daily_qty["date"].astype(str)
    else:
        daily_qty = pd.DataFrame(columns=["date", "units_sold"])

    capital_locked = 0
    if "cost_price" in df.columns:
        df["capital"] = df["cost_price"].fillna(0) * df["quantity"].fillna(0)
        capital_locked = round(float(df["capital"].sum()), 2)

    return {
        "status":            "success",
        "period":            period,
        "top_selling":       top_sold.to_dict(orient="records") if not top_sold.empty else [],
        "slow_moving":       slow_moving.to_dict(orient="records") if not slow_moving.empty else [],
        "category_movement": category_movement,
        "daily_qty_trend":   daily_qty.to_dict(orient="records") if not daily_qty.empty else [],
        "capital_locked":    capital_locked,
    }


# ══════════════════════════════════════════════════════════════
# 5. STAFF & OPS DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_staff_data(db: Session, user_id: int, period: str = "today") -> dict:
    df = get_user_df(db, user_id)
    if df.empty:
        return _no_data_response(period, "No data found. Upload a file first.")

    df = _filter_by_period(df, period)
    if df.empty:
        return _no_data_response(period)

    if "time" in df.columns and df["time"].notna().any():
        df_time = df[df["time"].notna()].copy()
        def extract_hour(t):
            try:    return int(str(t).split(":")[0])
            except: return None
        df_time["hour"] = df_time["time"].apply(extract_hour)
        df_time = df_time[df_time["hour"].notna()]
    else:
        df_time = pd.DataFrame()

    if not df_time.empty:
        txn_per_hour = (
            df_time.groupby("hour")["invoice_number"].nunique()
            .reindex(range(6,23), fill_value=0).reset_index()
            .rename(columns={"invoice_number":"transactions"})
        ) if "invoice_number" in df_time.columns else pd.DataFrame()

        rev_per_hour = (
            df_time.groupby("hour")["total_amount"].sum()
            .reindex(range(6,23), fill_value=0).round(2).reset_index()
            .rename(columns={"total_amount":"revenue"})
        )

        peak = rev_per_hour.sort_values("revenue", ascending=False).head(3)
        peak_hours = peak["hour"].tolist()

        df_date = df_time[df_time["date"].notna()] if "date" in df_time.columns else pd.DataFrame()
        if not df_date.empty:
            df_date["day_of_week"] = df_date["date"].dt.day_name()
            heatmap = (
                df_date.groupby(["day_of_week","hour"])["total_amount"].sum().round(2)
                .reset_index().rename(columns={"total_amount":"revenue"})
            )
        else:
            heatmap = pd.DataFrame(columns=["day_of_week", "hour", "revenue"])
    else:
        txn_per_hour = pd.DataFrame()
        rev_per_hour = pd.DataFrame(columns=["hour", "revenue"])
        peak_hours = []
        heatmap = pd.DataFrame()

    return {
        "status":           "success",
        "period":           period,
        "txn_per_hour":     txn_per_hour.to_dict(orient="records") if not txn_per_hour.empty else [],
        "revenue_per_hour": rev_per_hour.to_dict(orient="records") if not rev_per_hour.empty else [],
        "peak_hours":       peak_hours,
        "heatmap":          heatmap.to_dict(orient="records") if not heatmap.empty else [],
    }


# ══════════════════════════════════════════════════════════════
# 6. BUSINESS HEALTH DASHBOARD
# ══════════════════════════════════════════════════════════════

def get_health_data(db: Session, user_id: int, period: str = "today") -> dict:
    df = get_user_df(db, user_id)
    if df.empty:
        return _no_data_response(period, "No data found. Upload a file first.")

    df = _filter_by_period(df, period)
    if df.empty:
        return _no_data_response(period)

    df_date = df[df["date"].notna()].copy() if "date" in df.columns else pd.DataFrame()
    if not df_date.empty:
        monthly = (
            df_date.groupby(df_date["date"].dt.strftime("%Y-%m"))["total_amount"].sum().round(2).reset_index()
            .rename(columns={"date":"month", "total_amount":"revenue"}).sort_values("month")
        )
        monthly["prev_revenue"] = monthly["revenue"].shift(1)
        monthly["growth_pct"] = ((monthly["revenue"] - monthly["prev_revenue"]) / monthly["prev_revenue"] * 100).round(2)
        monthly = monthly.drop(columns=["prev_revenue"])
        monthly["growth_pct"] = monthly["growth_pct"].fillna(0)
    else:
        monthly = pd.DataFrame(columns=["month", "revenue", "growth_pct"])

    total_revenue = round(float(df["total_amount"].fillna(0).sum()), 2)
    total_cost = 0
    if "cost_price" in df.columns:
        total_cost = round(float(df["cost_price"].fillna(0).multiply(df["quantity"].fillna(0)).sum()), 2)
    gross_profit = round(total_revenue - total_cost, 2)

    best_month  = monthly.loc[monthly["revenue"].idxmax()].to_dict() if not monthly.empty else {}
    worst_month = monthly.loc[monthly["revenue"].idxmin()].to_dict() if not monthly.empty else {}

    category_health = {}
    if "category" in df.columns:
        category_health = (
            df.groupby("category")["total_amount"].sum().round(2)
            .sort_values(ascending=False).to_dict()
        )

    profit_margin = round((gross_profit / total_revenue * 100), 2) if total_revenue > 0 else 0
    if   profit_margin > 30: health_score = "Excellent 🟢"
    elif profit_margin > 20: health_score = "Good 🟡"
    elif profit_margin > 10: health_score = "Average 🟠"
    else:                    health_score = "Needs Attention 🔴"

    return {
        "status":          "success",
        "period":          period,
        "monthly_trend":   monthly.to_dict(orient="records") if not monthly.empty else [],
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
