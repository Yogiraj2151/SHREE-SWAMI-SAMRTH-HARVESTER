from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client

# ============================================================
# VARAD AGRO INDUSTRIES — ADVANCED BUSINESS MANAGEMENT SYSTEM
# Compatible with the existing Supabase table: land_records
# ============================================================

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
CSS_FILE = BASE_DIR / "style.css"

st.set_page_config(
    page_title="VARAD AGRO INDSTRIES/SHREE SWAMI SAMARTH HARVESTER",
    page_icon="🚜",
    layout="wide",
    initial_sidebar_state="collapsed",
)


import streamlit as st
from pathlib import Path

# Load custom CSS
css_path = Path(__file__).parent / "style.css"

if css_path.exists():
    st.markdown(
        f"<style>{css_path.read_text(encoding='utf-8')}</style>",
        unsafe_allow_html=True
    )

# Display your logo and brand name
logo_path = Path(__file__).parent / "logo.png"

col1, col2 = st.columns([1, 5], vertical_alignment="center")

with col1:
    if logo_path.exists():
        st.image(str(logo_path), width=500)
    else:
        st.warning("Please add logo.png to your project folder.")

with col2:
    st.markdown(
        """
        <div class="brand-header">
            <h1>VARAD AGRO INDUSTRIES</h1>
            <p>Agricultural Records & Payment Management</p>
        </div>
        """,
        unsafe_allow_html=True
    )



   
COLUMNS = [
    "Date", "Name", "Place", "Gunthe", "Price/Guntha", "Guntha Total",
    "Bags", "Price/Bag", "Bag Total", "Total Price",
    "Online", "Cash", "Total Paid", "Balance",
]
NUMERIC_COLUMNS = [
    "Gunthe", "Price/Guntha", "Guntha Total", "Bags", "Price/Bag",
    "Bag Total", "Total Price", "Online", "Cash", "Total Paid", "Balance",
]
TABLE_NAME = "land_records"
MONEY = ["Price/Guntha", "Guntha Total", "Price/Bag", "Bag Total",
         "Total Price", "Online", "Cash", "Total Paid", "Balance"]


def secret(name: str) -> str:
    """Read credentials from Streamlit secrets first, then .env."""
    try:
        value = st.secrets.get(name, "")
        if value:
            return str(value).strip()
    except Exception:
        pass
    return os.getenv(name, "").strip()


@st.cache_resource(show_spinner=False)
def get_client(url: str, key: str) -> Client:
    return create_client(url, key)


SUPABASE_URL = secret("SUPABASE_URL")
SUPABASE_KEY = secret("SUPABASE_KEY")
supabase: Client | None = None
DB_READY = False
DB_ERROR = ""

if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = get_client(SUPABASE_URL, SUPABASE_KEY)
        DB_READY = True
    except Exception as exc:
        DB_ERROR = str(exc)
else:
    DB_ERROR = "Add SUPABASE_URL and SUPABASE_KEY to .env or Streamlit Secrets."


def inject_css() -> None:
    if CSS_FILE.exists():
        st.markdown(f"<style>{CSS_FILE.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


inject_css()


def money(value: Any) -> str:
    try:
        return f"₹{float(value or 0):,.2f}"
    except (TypeError, ValueError):
        return "₹0.00"


def empty_data() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS + ["id"])


def normalise_data(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return empty_data()
    frame = pd.DataFrame(rows)
    for col in COLUMNS:
        if col not in frame.columns:
            frame[col] = "" if col in ("Date", "Name", "Place") else 0.0
    if "id" not in frame.columns:
        frame["id"] = None
    for col in NUMERIC_COLUMNS:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").fillna(0.0)
    frame["Name"] = frame["Name"].fillna("").astype(str).str.strip()
    frame["Place"] = frame["Place"].fillna("").astype(str).str.strip()
    frame["Date"] = frame["Date"].fillna("").astype(str)
    # Derived values are recalculated consistently rather than trusting stale totals.
    frame["Guntha Total"] = frame["Gunthe"] * frame["Price/Guntha"]
    frame["Bag Total"] = frame["Bags"] * frame["Price/Bag"]
    frame["Total Price"] = frame["Guntha Total"] + frame["Bag Total"]
    frame["Total Paid"] = frame["Online"] + frame["Cash"]
    frame["Balance"] = frame["Total Price"] - frame["Total Paid"]
    frame.loc[frame["Balance"].abs() < 0.01, "Balance"] = 0.0
    return frame[COLUMNS + ["id"]]


def load_data() -> pd.DataFrame:
    if not DB_READY or supabase is None:
        return empty_data()
    try:
        result = supabase.table(TABLE_NAME).select("*").order("id", desc=True).execute()
        return normalise_data(result.data or [])
    except Exception as exc:
        st.error(f"Could not load records from Supabase: {exc}")
        return empty_data()


def record_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for col in COLUMNS:
        value = record.get(col, "" if col in ("Date", "Name", "Place") else 0)
        if col in NUMERIC_COLUMNS:
            payload[col] = float(value or 0)
        else:
            payload[col] = str(value or "").strip()
    # Keep financial totals consistent.
    payload["Guntha Total"] = payload["Gunthe"] * payload["Price/Guntha"]
    payload["Bag Total"] = payload["Bags"] * payload["Price/Bag"]
    payload["Total Price"] = payload["Guntha Total"] + payload["Bag Total"]
    payload["Total Paid"] = payload["Online"] + payload["Cash"]
    payload["Balance"] = payload["Total Price"] - payload["Total Paid"]
    if abs(payload["Balance"]) < 0.01:
        payload["Balance"] = 0.0
    return payload


def insert_record(record: dict[str, Any]) -> tuple[bool, str]:
    if not DB_READY or supabase is None:
        return False, "Database is not connected. Check your Supabase credentials."
    try:
        supabase.table(TABLE_NAME).insert(record_payload(record)).execute()
        return True, "Record saved successfully."
    except Exception as exc:
        return False, f"Supabase insert failed: {exc}"


def update_record(record_id: Any, record: dict[str, Any]) -> tuple[bool, str]:
    if not DB_READY or supabase is None:
        return False, "Database is not connected."
    try:
        supabase.table(TABLE_NAME).update(record_payload(record)).eq("id", int(record_id)).execute()
        return True, "Record updated successfully."
    except Exception as exc:
        return False, f"Supabase update failed: {exc}"


def delete_record(record_id: Any) -> tuple[bool, str]:
    if not DB_READY or supabase is None:
        return False, "Database is not connected."
    try:
        supabase.table(TABLE_NAME).delete().eq("id", int(record_id)).execute()
        return True, "Record deleted successfully."
    except Exception as exc:
        return False, f"Supabase delete failed: {exc}"


def plot_layout(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#F8FAFC", family="Inter, sans-serif"),
        height=height,
        margin=dict(l=18, r=18, t=55, b=20),
        title_font=dict(size=18, color="#F8FAFC"),
        xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        legend=dict(font=dict(color="#F8FAFC")),
    )
    return fig


def filter_records(frame: pd.DataFrame, prefix: str = "global") -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    with st.expander("🔎 Search & filter records", expanded=False):
        a, b, c, d = st.columns([1.35, 1.15, 1, 1])
        query = a.text_input("Customer name contains", key=f"{prefix}_query")
        place_query = b.text_input("Place / village contains", key=f"{prefix}_place_query")
        dates = pd.to_datetime(frame["Date"], errors="coerce")
        min_d = dates.min().date() if dates.notna().any() else date.today()
        max_d = dates.max().date() if dates.notna().any() else date.today()
        start = c.date_input("From date", value=min_d, key=f"{prefix}_from")
        end = d.date_input("To date", value=max_d, key=f"{prefix}_to")
        if start > end:
            st.warning("The start date is after the end date.")
            return frame.iloc[0:0].copy()
        result = frame.copy()
        if query.strip():
            result = result[result["Name"].str.contains(query.strip(), case=False, na=False)]
        if place_query.strip():
            result = result[result["Place"].str.contains(place_query.strip(), case=False, na=False)]
        result_dates = pd.to_datetime(result["Date"], errors="coerce").dt.date
        result = result[(result_dates >= start) & (result_dates <= end)]
        d, e = st.columns(2)
        min_balance = d.checkbox("Only pending balances", key=f"{prefix}_pending")
        min_paid = e.checkbox("Only fully paid records", key=f"{prefix}_paid")
        if min_balance and min_paid:
            st.info("Choose either pending or fully paid records, not both.")
        elif min_balance:
            result = result[result["Balance"] > 0]
        elif min_paid:
            result = result[result["Balance"] <= 0]
        return result
    return frame.copy()


def business_answer(question: str, frame: pd.DataFrame) -> str:
    if frame.empty:
        return "There are no records yet. Add a land or bag record first."
    q = question.lower().strip()
    total_land = frame["Gunthe"].sum()
    total_bags = frame["Bags"].sum()
    total_price = frame["Total Price"].sum()
    total_paid = frame["Total Paid"].sum()
    balance = frame["Balance"].sum()
    online = frame["Online"].sum()
    cash = frame["Cash"].sum()
    customers = frame["Name"].nunique()
    valid_land = frame.loc[frame["Gunthe"] > 0, "Price/Guntha"]
    valid_bags = frame.loc[frame["Bags"] > 0, "Price/Bag"]

    if any(x in q for x in ("pending", "balance", "बाकी")):
        return f"**Total pending balance: {money(balance)}**"
    if any(x in q for x in ("online", "ऑनलाइन")):
        return f"**Online collection: {money(online)}**"
    if any(x in q for x in ("cash", "रोख", "कॅश")):
        return f"**Cash collection: {money(cash)}**"
    if any(x in q for x in ("collection", "total paid", "जमा")):
        return f"Online: {money(online)}  \nCash: {money(cash)}  \n**Total collected: {money(total_paid)}**"
    if any(x in q for x in ("per guntha", "price/guntha", "प्रति गुंठा")):
        avg = valid_land.mean() if not valid_land.empty else 0
        return f"**Average price per guntha: {money(avg)}**"
    if any(x in q for x in ("per bag", "price/bag", "प्रति बॅग")):
        avg = valid_bags.mean() if not valid_bags.empty else 0
        return f"**Average price per bag: {money(avg)}**"
    if "bag" in q or "बॅग" in q:
        return f"**Total bags: {total_bags:,.2f}**"
    if "guntha" in q or "gunthe" in q or "गुंठ" in q:
        return f"**Total land: {total_land:,.2f} guntha**"
    if any(x in q for x in ("customer", "ग्राहक")):
        return f"**Unique customers: {customers}**"
    if any(x in q for x in ("top", "highest", "best customer")):
        top = frame.groupby("Name")["Total Paid"].sum().sort_values(ascending=False)
        if not top.empty:
            return f"**Top customer by amount paid: {top.index[0]}**  \nPaid: {money(top.iloc[0])}"
    if any(x in q for x in ("summary", "report", "सारांश")):
        return (
            f"### Business summary\n"
            f"- Customers: **{customers}**\n"
            f"- Land: **{total_land:,.2f} guntha**\n"
            f"- Bags: **{total_bags:,.2f}**\n"
            f"- Total business value: **{money(total_price)}**\n"
            f"- Online: **{money(online)}**\n"
            f"- Cash: **{money(cash)}**\n"
            f"- Collected: **{money(total_paid)}**\n"
            f"- Pending: **{money(balance)}**"
        )
    if any(x in q for x in ("total price", "total amount", "business value", "किंमत")):
        return f"**Total business value: {money(total_price)}**"
    return (
        "I can answer questions about total price, pending balance, online payments, "
        "cash collection, total guntha, bags, average prices, top customer, and business summary."
    )


def show_db_status() -> None:
    """Show Supabase status and allow a live database connectivity test in the main page."""
    status_col, button_col = st.columns([3, 1])
    with status_col:
        if not DB_READY or supabase is None:
            st.error("Supabase disconnected — add SUPABASE_URL and SUPABASE_KEY to .env or Streamlit Secrets.")
            return
        st.success("Supabase credentials loaded")
    with button_col:
        if st.button("Test database connection", use_container_width=True, key="test_supabase_connection"):
            try:
                supabase.table(TABLE_NAME).select("id").limit(1).execute()
                st.success("Live database connection successful")
            except Exception as exc:
                st.error("Database connection test failed")
                st.caption(str(exc)[:500])
                st.info(
                    "Check that the land_records table exists, its column names match "
                    "supabase_setup.sql, and your key has the required database permissions."
                )


def render_kpis(frame: pd.DataFrame) -> None:
    total_value = frame["Total Price"].sum() if not frame.empty else 0
    paid = frame["Total Paid"].sum() if not frame.empty else 0
    pending = frame["Balance"].sum() if not frame.empty else 0
    land = frame["Gunthe"].sum() if not frame.empty else 0
    bags = frame["Bags"].sum() if not frame.empty else 0
    customers = frame["Name"].nunique() if not frame.empty else 0
    cols = st.columns(6)
    cols[0].metric("Business value", money(total_value))
    cols[1].metric("Collected", money(paid))
    cols[2].metric("Pending", money(pending), delta=f"{(pending / total_value * 100):.1f}% of value" if total_value else None, delta_color="inverse")
    cols[3].metric("Land (guntha)", f"{land:,.2f}")
    cols[4].metric("Total bags", f"{bags:,.0f}")
    cols[5].metric("Customers", f"{customers:,}")


# ------------------------------ HEADER / NAVIGATION ------------------------------


# ------------------------------ TOP NAVIGATION (NO SIDEBAR) ------------------------------
nav_options = [
    "📊 Dashboard", "➕ Add Record", "🤖 Business Assistant",
    "👥 Customers", "📈 Analytics", "💳 Pending Payments",
    "📝 Manage Records", "📥 Import / Export",
]
st.markdown('<div class="workspace-label">WORKSPACE NAVIGATION</div>', unsafe_allow_html=True)
page = st.radio(
    "WORKSPACE",
    nav_options,
    key="main_navigation",
    horizontal=True,
    label_visibility="collapsed",
)
st.markdown('<div class="nav-footnote">TODAY · ' + date.today().strftime('%d %b %Y') + ' &nbsp; • &nbsp; VARAD AGRO INDUSTRIES</div>', unsafe_allow_html=True)
show_db_status()
st.divider()

data = load_data()

# ------------------------------ DASHBOARD ------------------------------
if page == "📊 Dashboard":
    st.subheader("Business overview")
    st.caption("A live summary calculated from the records stored in Supabase.")
    view = filter_records(data, "dashboard")
    render_kpis(view)
    if view.empty:
        st.info("No matching records. Add a record or adjust your filters.")
    else:
        left, right = st.columns(2)
        with left:
            st.markdown("#### Payment collection")
            payment_df = pd.DataFrame({"Payment type": ["Online", "Cash"], "Amount": [view["Online"].sum(), view["Cash"].sum()]})
            fig = px.pie(payment_df, names="Payment type", values="Amount", hole=0.62,
                         color="Payment type", color_discrete_map={"Online": "#38C6A5", "Cash": "#F28B73"})
            fig.update_traces(textinfo="label+percent", hole=0.62)
            st.plotly_chart(plot_layout(fig), use_container_width=True)
        with right:
            st.markdown("#### Top customers by amount paid")
            top = view.groupby("Name", as_index=False)["Total Paid"].sum().nlargest(10, "Total Paid")
            fig = px.bar(top.sort_values("Total Paid"), x="Total Paid", y="Name", orientation="h",
                         text="Total Paid", color="Total Paid", color_continuous_scale=["#6A8D73", "#F0B35A"])
            fig.update_traces(texttemplate="₹%{text:,.0f}", textposition="outside")
            st.plotly_chart(plot_layout(fig), use_container_width=True)
        left, right = st.columns(2)
        with left:
            st.markdown("#### Monthly business value")
            temp = view.copy()
            temp["Date"] = pd.to_datetime(temp["Date"], errors="coerce")
            temp = temp.dropna(subset=["Date"])
            if not temp.empty:
                temp["Month"] = temp["Date"].dt.to_period("M").astype(str)
                monthly = temp.groupby("Month", as_index=False).agg(Value=("Total Price", "sum"), Paid=("Total Paid", "sum"))
                fig = px.line(monthly, x="Month", y=["Value", "Paid"], markers=True,
                              color_discrete_map={"Value": "#F0B35A", "Paid": "#38C6A5"})
                st.plotly_chart(plot_layout(fig), use_container_width=True)
            else:
                st.caption("Valid dates are needed for monthly trends.")
        with right:
            st.markdown("#### Pending payment watchlist")
            pending = view[view["Balance"] > 0].sort_values("Balance", ascending=False).head(8)
            if pending.empty:
                st.success("All visible records are fully paid.")
            else:
                st.dataframe(pending[["Date", "Name", "Total Price", "Total Paid", "Balance"]],
                             hide_index=True, use_container_width=True)
        st.markdown("#### Latest records")
        st.dataframe(view[COLUMNS].head(10), hide_index=True, use_container_width=True)

# ------------------------------ ADD RECORD ------------------------------
elif page == "➕ Add Record":
    st.subheader("Create a business record")
    st.caption("Enter customer, place/village, land or bag details. Totals and pending balance are calculated automatically.")
    with st.form("add_record_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            entry_date = st.date_input("Record date", value=date.today())
            name = st.text_input("Customer name", placeholder="Enter full customer name")
            place = st.text_input("📍 Place / Village", placeholder="Enter village, town or location")
            st.markdown("#### 🌾 Land details")
            land = st.number_input("Land area (guntha)", min_value=0.0, step=0.5, format="%.2f")
            land_rate = st.number_input("Price per guntha (₹)", min_value=0.0, step=500.0, format="%.2f")
        with c2:
            st.markdown("#### 🛍️ Bag details")
            bags = st.number_input("Number of bags", min_value=0.0, step=1.0, format="%.2f")
            bag_rate = st.number_input("Price per bag (₹)", min_value=0.0, step=100.0, format="%.2f")
            st.markdown("#### 💳 Payment details")
            online = st.number_input("Online payment (₹)", min_value=0.0, step=100.0, format="%.2f")
            cash = st.number_input("Cash payment (₹)", min_value=0.0, step=100.0, format="%.2f")
        total = land * land_rate + bags * bag_rate
        paid = online + cash
        pending = total - paid
        st.divider()
        k1, k2, k3 = st.columns(3)
        k1.metric("Total business value", money(total))
        k2.metric("Total received", money(paid))
        k3.metric("Pending balance", money(pending))
        submitted = st.form_submit_button("💾 Save record", use_container_width=True)
    if submitted:
        if not name.strip():
            st.error("Customer name is required.")
        elif not place.strip():
            st.error("Place / village is required.")
        elif land <= 0 and bags <= 0:
            st.error("Enter a land area or a number of bags.")
        elif land > 0 and land_rate <= 0:
            st.error("Price per guntha must be greater than zero.")
        elif bags > 0 and bag_rate <= 0:
            st.error("Price per bag must be greater than zero.")
        elif paid > total:
            st.error("Total payment cannot be greater than the total business value.")
        else:
            record = {
                "Date": entry_date.isoformat(), "Name": name.strip(), "Place": place.strip(),
                "Gunthe": land, "Price/Guntha": land_rate, "Guntha Total": land * land_rate,
                "Bags": bags, "Price/Bag": bag_rate, "Bag Total": bags * bag_rate,
                "Total Price": total, "Online": online, "Cash": cash,
                "Total Paid": paid, "Balance": pending,
            }
            ok, message = insert_record(record)
            if ok:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

# ------------------------------ ASSISTANT ------------------------------
elif page == "🤖 Business Assistant":
    st.subheader("🤖 Business intelligence assistant")
    st.write("Ask questions about the records currently stored in your business database.")
    examples = [
        "Give me a business summary", "How much payment is pending?",
        "What is the total online collection?", "Who is my top customer?",
        "How many guntha do I have in records?", "How many bags are recorded?",
    ]
    choice = st.selectbox("Try a sample question", ["Choose a question…"] + examples)
    question = st.text_input("Your question", value="" if choice == "Choose a question…" else choice,
                             placeholder="Example: Give me a business summary")
    if st.button("Get answer", type="primary", use_container_width=True):
        if not question.strip():
            st.warning("Enter a question first.")
        else:
            st.markdown(business_answer(question, data))

# ------------------------------ CUSTOMERS ------------------------------
elif page == "👥 Customers":
    st.subheader("Customer management")
    if data.empty:
        st.info("No customer records found yet.")
    else:
        summary = data.groupby("Name", as_index=False).agg(
            Places=("Place", lambda values: ", ".join(sorted({str(v).strip() for v in values if str(v).strip()}))),
            Land=("Gunthe", "sum"), Bags=("Bags", "sum"),
            Business_Value=("Total Price", "sum"), Online=("Online", "sum"),
            Cash=("Cash", "sum"), Paid=("Total Paid", "sum"),
            Pending=("Balance", "sum"), Records=("id", "count"),
        )
        query = st.text_input("Search customer", placeholder="Type a name…")
        if query.strip():
            summary = summary[summary["Name"].str.contains(query.strip(), case=False, na=False)]
        st.dataframe(summary.sort_values("Pending", ascending=False), hide_index=True, use_container_width=True)
        if not summary.empty:
            selected = st.selectbox("Customer profile", summary["Name"].tolist())
            customer_rows = data[data["Name"] == selected].copy()
            a, b, c, d = st.columns(4)
            a.metric("Business value", money(customer_rows["Total Price"].sum()))
            b.metric("Collected", money(customer_rows["Total Paid"].sum()))
            c.metric("Pending", money(customer_rows["Balance"].sum()))
            d.metric("Records", len(customer_rows))
            st.markdown("#### Transaction history")
            st.dataframe(customer_rows[COLUMNS], hide_index=True, use_container_width=True)

# ------------------------------ ANALYTICS ------------------------------
elif page == "📈 Analytics":
    st.subheader("Advanced analytics")
    view = filter_records(data, "analytics")
    if view.empty:
        st.info("No data available for these filters.")
    else:
        render_kpis(view)
        a, b = st.columns(2)
        with a:
            st.markdown("#### Business value by customer")
            customer_value = view.groupby("Name", as_index=False)["Total Price"].sum().nlargest(12, "Total Price")
            fig = px.bar(customer_value.sort_values("Total Price"), x="Total Price", y="Name",
                         orientation="h", text="Total Price", color="Total Price",
                         color_continuous_scale=["#6A8D73", "#F0B35A"])
            fig.update_traces(texttemplate="₹%{text:,.0f}", textposition="outside")
            st.plotly_chart(plot_layout(fig), use_container_width=True)
        with b:
            st.markdown("#### Land area vs bags")
            mix = view.groupby("Name", as_index=False).agg(Land=("Gunthe", "sum"), Bags=("Bags", "sum"))
            fig = px.scatter(mix, x="Land", y="Bags", hover_name="Name", size="Bags",
                             color="Land", color_continuous_scale="Teal")
            st.plotly_chart(plot_layout(fig), use_container_width=True)
        temp = view.copy()
        temp["Date"] = pd.to_datetime(temp["Date"], errors="coerce")
        temp = temp.dropna(subset=["Date"])
        if not temp.empty:
            temp["Month"] = temp["Date"].dt.to_period("M").astype(str)
            monthly = temp.groupby("Month", as_index=False).agg(
                Business_Value=("Total Price", "sum"), Collected=("Total Paid", "sum"), Pending=("Balance", "sum"))
            st.markdown("#### Monthly performance")
            fig = go.Figure()
            for col, color in [("Business_Value", "#F0B35A"), ("Collected", "#38C6A5"), ("Pending", "#F28B73")]:
                fig.add_trace(go.Scatter(x=monthly["Month"], y=monthly[col], mode="lines+markers", name=col.replace("_", " "), line=dict(width=3, color=color)))
            st.plotly_chart(plot_layout(fig, 400), use_container_width=True)
            st.dataframe(monthly, hide_index=True, use_container_width=True)

# ------------------------------ PENDING PAYMENTS ------------------------------
elif page == "💳 Pending Payments":
    st.subheader("Pending payments")
    pending = data[data["Balance"] > 0].copy() if not data.empty else empty_data()
    st.metric("Total outstanding amount", money(pending["Balance"].sum() if not pending.empty else 0))
    if pending.empty:
        st.success("No pending payments. All recorded accounts are settled.")
    else:
        pending = pending.sort_values("Balance", ascending=False)
        st.dataframe(pending[["id", "Date", "Name", "Place", "Total Price", "Total Paid", "Balance"]],
                     hide_index=True, use_container_width=True)
        options = pending["id"].tolist()
        selected_id = st.selectbox(
            "Select a record to receive a payment",
            options,
            format_func=lambda rid: f"#{rid} · {pending.loc[pending['id'] == rid, 'Name'].iloc[0]} · {money(pending.loc[pending['id'] == rid, 'Balance'].iloc[0])}",
        )
        row = pending[pending["id"] == selected_id].iloc[0]
        st.info(f"{row['Name']} · {row['Place'] or 'Place not specified'} · Current pending balance: {money(row['Balance'])}")
        with st.form("receive_payment_form"):
            c1, c2 = st.columns(2)
            online_add = c1.number_input("Online received (₹)", min_value=0.0, max_value=float(row["Balance"]), step=100.0, format="%.2f")
            cash_add = c2.number_input("Cash received (₹)", min_value=0.0, max_value=float(row["Balance"]), step=100.0, format="%.2f")
            submit_payment = st.form_submit_button("Confirm payment & update record", use_container_width=True)
        if submit_payment:
            amount = float(online_add + cash_add)
            if amount <= 0:
                st.warning("Enter a payment amount greater than zero.")
            elif amount > float(row["Balance"]) + 0.001:
                st.error("Payment cannot exceed the pending balance.")
            else:
                updated = row.to_dict()
                updated["Online"] = float(row["Online"]) + float(online_add)
                updated["Cash"] = float(row["Cash"]) + float(cash_add)
                ok, message = update_record(selected_id, updated)
                if ok:
                    st.success(f"{message} Payment received: {money(amount)}")
                    st.rerun()
                else:
                    st.error(message)

# ------------------------------ MANAGE RECORDS ------------------------------
elif page == "📝 Manage Records":
    st.subheader("Manage business records")
    st.warning("Editing or deleting a record changes the live Supabase database. Verify the record ID before saving.")
    view = filter_records(data, "manage")
    if view.empty:
        st.info("No matching records.")
    else:
        display = view.copy()
        display["id"] = display["id"].astype(str)
        st.dataframe(display[["id"] + COLUMNS], hide_index=True, use_container_width=True)
        valid_ids = view["id"].dropna().tolist()
        if valid_ids:
            selected_id = st.selectbox(
                "Choose a record to edit or delete",
                valid_ids,
                format_func=lambda rid: f"#{rid} · {view.loc[view['id'] == rid, 'Name'].iloc[0]} · {view.loc[view['id'] == rid, 'Date'].iloc[0]}",
            )
            row = view[view["id"] == selected_id].iloc[0]
            with st.expander("✏️ Edit selected record", expanded=False):
                with st.form(f"edit_record_{selected_id}"):
                    a, b = st.columns(2)
                    with a:
                        edit_date = st.date_input("Date", value=pd.to_datetime(row["Date"], errors="coerce").date() if pd.notna(pd.to_datetime(row["Date"], errors="coerce")) else date.today())
                        edit_name = st.text_input("Customer name", value=str(row["Name"]))
                        edit_place = st.text_input("📍 Place / Village", value=str(row["Place"] or ""))
                        edit_land = st.number_input("Land area (guntha)", min_value=0.0, value=float(row["Gunthe"]), step=0.5)
                        edit_land_rate = st.number_input("Price per guntha (₹)", min_value=0.0, value=float(row["Price/Guntha"]), step=500.0)
                    with b:
                        edit_bags = st.number_input("Number of bags", min_value=0.0, value=float(row["Bags"]), step=1.0)
                        edit_bag_rate = st.number_input("Price per bag (₹)", min_value=0.0, value=float(row["Price/Bag"]), step=100.0)
                        edit_online = st.number_input("Online paid (₹)", min_value=0.0, value=float(row["Online"]), step=100.0)
                        edit_cash = st.number_input("Cash paid (₹)", min_value=0.0, value=float(row["Cash"]), step=100.0)
                    edit_total = edit_land * edit_land_rate + edit_bags * edit_bag_rate
                    edit_paid = edit_online + edit_cash
                    st.caption(f"Calculated total: {money(edit_total)} · Paid: {money(edit_paid)} · Balance: {money(edit_total - edit_paid)}")
                    save_edit = st.form_submit_button("Save changes", use_container_width=True)
                if save_edit:
                    if not edit_name.strip() or not edit_place.strip() or (edit_land <= 0 and edit_bags <= 0):
                        st.error("Enter a customer name, place/village and at least one land/bag quantity.")
                    elif (edit_land > 0 and edit_land_rate <= 0) or (edit_bags > 0 and edit_bag_rate <= 0):
                        st.error("A used land/bag quantity must have a price greater than zero.")
                    elif edit_paid > edit_total:
                        st.error("Total paid cannot exceed the calculated business value.")
                    else:
                        edited = {
                            "Date": edit_date.isoformat(), "Name": edit_name.strip(), "Place": edit_place.strip(),
                            "Gunthe": edit_land, "Price/Guntha": edit_land_rate,
                            "Bags": edit_bags, "Price/Bag": edit_bag_rate,
                            "Online": edit_online, "Cash": edit_cash,
                        }
                        ok, message = update_record(selected_id, edited)
                        if ok:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
            with st.expander("🗑️ Delete selected record", expanded=False):
                st.error(f"This permanently deletes record #{selected_id} for {row['Name']}.")
                confirm = st.checkbox("I understand this action cannot be undone.", key=f"confirm_delete_{selected_id}")
                if st.button("Permanently delete record", disabled=not confirm, key=f"delete_{selected_id}"):
                    ok, message = delete_record(selected_id)
                    if ok:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

# ------------------------------ IMPORT / EXPORT ------------------------------
elif page == "📥 Import / Export":
    st.subheader("Import and export records")
    st.markdown("#### 📤 Export")
    if data.empty:
        st.info("There are no records to export.")
    else:
        export_csv = data[COLUMNS].to_csv(index=False).encode("utf-8-sig")
        st.download_button("Download CSV", export_csv, file_name=f"varad_agro_records_{date.today().isoformat()}.csv",
                           mime="text/csv", use_container_width=True)
        try:
            from io import BytesIO
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                data[COLUMNS].to_excel(writer, index=False, sheet_name="Land Records")
                data.groupby("Name", as_index=False).agg(
                    Business_Value=("Total Price", "sum"), Paid=("Total Paid", "sum"), Pending=("Balance", "sum")
                ).to_excel(writer, index=False, sheet_name="Customer Summary")
            st.download_button("Download Excel report", buffer.getvalue(),
                               file_name=f"varad_agro_report_{date.today().isoformat()}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
        except Exception:
            st.caption("Install openpyxl to enable Excel export: pip install openpyxl")
    st.divider()
    st.markdown("#### 📥 Import CSV")
    st.caption("CSV import expects the same column names as the table. Preview and validate before inserting.")
    uploaded = st.file_uploader("Upload a CSV file", type=["csv"])
    if uploaded is not None:
        try:
            incoming = pd.read_csv(uploaded)
            missing = [col for col in COLUMNS if col not in incoming.columns]
            if missing:
                st.error("Missing required columns: " + ", ".join(missing))
            else:
                incoming = incoming[COLUMNS].copy()
                st.dataframe(incoming.head(20), hide_index=True, use_container_width=True)
                st.warning("Import inserts new rows; it does not update existing rows. Avoid uploading the same file twice.")
                if st.button("Import previewed rows into Supabase", type="primary"):
                    inserted, failed = 0, []
                    for index, record in incoming.iterrows():
                        try:
                            payload = record_payload(record.to_dict())
                            if not payload["Name"].strip():
                                failed.append(f"Row {index + 2}: customer name is empty")
                                continue
                            if not payload["Place"].strip():
                                failed.append(f"Row {index + 2}: place/village is empty")
                                continue
                            if payload["Online"] + payload["Cash"] > payload["Total Price"] + 0.001:
                                failed.append(f"Row {index + 2}: payment exceeds total price")
                                continue
                            if not DB_READY or supabase is None:
                                raise RuntimeError("Supabase is not connected")
                            supabase.table(TABLE_NAME).insert(payload).execute()
                            inserted += 1
                        except Exception as exc:
                            failed.append(f"Row {index + 2}: {exc}")
                    st.success(f"Imported {inserted} row(s).")
                    if failed:
                        st.error("Some rows could not be imported:\n\n" + "\n".join(failed[:10]))
                    st.rerun()
        except Exception as exc:
            st.error(f"Could not read CSV: {exc}")

st.markdown(
    '<div class="app-footer">VARAD AGRO INDUSTRIES · ADVANCED BUSINESS HUB &nbsp; • &nbsp; Keep a regular CSV/Excel backup of your business records.</div>',
    unsafe_allow_html=True,
)
