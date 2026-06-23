import asyncio
import os
from datetime import date

import nest_asyncio
import pandas as pd
import streamlit as st

nest_asyncio.apply()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="DMCA Monitor",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── Hide sidebar entirely ─────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] { display: none; }
[data-testid="collapsedControl"] { display: none; }
.block-container { padding-top: 2rem; max-width: 900px; }
</style>
""", unsafe_allow_html=True)

# ── Password gate ─────────────────────────────────────────────────────────────
try:
    APP_PASSWORD = st.secrets["APP_PASSWORD"]
except (KeyError, FileNotFoundError):
    APP_PASSWORD = ""

if APP_PASSWORD and not st.session_state.get("authenticated"):
    st.markdown("<h2 style='text-align:center;margin-top:4rem'>🛡️ DMCA Monitor</h2>", unsafe_allow_html=True)
    col = st.columns([1, 2, 1])[1]
    with col:
        pwd = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Enter password")
        if st.button("Login", use_container_width=True, type="primary"):
            if pwd == APP_PASSWORD:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password")
    st.stop()

# ── Load secrets ──────────────────────────────────────────────────────────────
try:
    os.environ["SERPAPI_KEY"] = st.secrets["SERPAPI_KEY"]
except (KeyError, FileNotFoundError):
    pass

from checker import check_single_url            # noqa: E402
from counter_notice import generate_counter_notice  # noqa: E402

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## 🛡️ DMCA Monitor")
st.caption("Check if your URLs are indexed in Google and flag any DMCA takedown notices.")

st.divider()

# ── URL input ─────────────────────────────────────────────────────────────────
col_upload, col_paste = st.columns([1, 1], gap="large")

with col_upload:
    st.markdown("**Upload CSV**")
    uploaded_file = st.file_uploader(
        "Upload CSV",
        type=["csv"],
        help="Any column named url, URL, link, or the first column is used.",
        label_visibility="collapsed",
    )

with col_paste:
    st.markdown("**Or paste URLs**")
    manual_urls = st.text_area(
        "Paste URLs",
        height=120,
        placeholder="https://example.com/page-1\nhttps://example.com/page-2",
        label_visibility="collapsed",
    )

# ── Parse URLs ────────────────────────────────────────────────────────────────
urls: list[str] = []

if uploaded_file:
    try:
        df_csv = pd.read_csv(uploaded_file)
        url_col = next(
            (c for c in df_csv.columns if c.lower() in ["url", "urls", "link", "links"]),
            df_csv.columns[0],
        )
        urls += df_csv[url_col].dropna().str.strip().tolist()
    except Exception as exc:
        st.error(f"Could not read CSV: {exc}")

if manual_urls.strip():
    urls += [u.strip() for u in manual_urls.strip().splitlines() if u.strip()]

seen: set = set()
urls = [u for u in urls if not (u in seen or seen.add(u))]

if urls:
    mins, secs = divmod(len(urls) * 5, 60)
    st.info(f"**{len(urls)} URLs** ready — estimated time: ~{mins} min {secs} sec")

st.divider()

# ── Company info (for counter-notice PDFs) ────────────────────────────────────
with st.expander("Company info for counter-notice PDFs", expanded=False):
    ci1, ci2 = st.columns(2)
    with ci1:
        company_name  = st.text_input("Company Name",  value="GDC Group")
        company_phone = st.text_input("Phone",         value="+353 1 903 8375")
    with ci2:
        company_address = st.text_input("Address", value="Fitzwilliam Court 3rd Floor, Leeson Cl, Dublin 2, Ireland")
        company_email   = st.text_input("Email",   value="sandeep.kumar@gdcgroup.com")

st.divider()

# ── Check button ──────────────────────────────────────────────────────────────
if st.button("Check URLs", type="primary", disabled=not bool(urls), use_container_width=True):

    results: list[dict] = []

    progress_bar = st.progress(0, text="Starting...")
    status_text  = st.empty()

    c1, c2, c3 = st.columns(3)
    box_total   = c1.empty()
    box_indexed = c2.empty()
    box_notices = c3.empty()

    table_placeholder = st.empty()

    def refresh_stats():
        indexed = sum(1 for r in results if r["indexed"])
        notices = sum(1 for r in results if r["notices"])
        box_total.metric("Checked",        len(results))
        box_indexed.metric("Indexed",      indexed)
        box_notices.metric("DMCA Notices", notices)

    def refresh_table():
        rows = []
        for idx, r in enumerate(results, 1):
            notice_ids = ", ".join(
                str(n["id"]) + ("" if n.get("geo_confirmed", True) else " ⚠️ geo-specific")
                for n in r["notices"] if n.get("id")
            ) or ("Yes" if r["notices"] else "—")
            lumen_link = next(
                (n["lumen_url"] for n in r["notices"] if n.get("lumen_url")), ""
            )
            rows.append({
                "#":            idx,
                "URL":          r["url"],
                "Indexed":      "Yes" if r["indexed"] else "No",
                "DMCA Notice":  notice_ids,
                "Lumen Link":   lumen_link,
                "Error":        (r.get("indexed_error") or "")[:80],
            })
        table_placeholder.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Lumen Link": st.column_config.LinkColumn("Lumen Link", display_text="View Notice"),
            },
        )

    total = len(urls)
    for i, url in enumerate(urls):
        status_text.caption(f"Checking: {url}")
        result = check_single_url(url)
        results.append(result)
        pct = len(results) / total
        progress_bar.progress(pct, text=f"Checking {len(results)} / {total}...")
        refresh_stats()
        refresh_table()

    progress_bar.progress(1.0, text="Complete!")
    status_text.empty()

    st.divider()

    # ── DMCA summary ─────────────────────────────────────────────────────────
    notices_found = [r for r in results if r["notices"]]

    if notices_found:
        st.error(f"**{len(notices_found)} URL(s) have DMCA notices** — generate counter-notices below.")
        for r in notices_found:
            with st.expander(f"📋 {r['url']}"):
                for notice in r["notices"]:
                    cols = st.columns([1, 1])
                    with cols[0]:
                        st.markdown(f"**Notice ID:** {notice.get('id') or 'N/A'}")
                        if not notice.get("geo_confirmed", True):
                            st.warning("⚠️ Geo-specific notice — page may be indexed globally but removed in a specific region. Verify manually.")
                        if notice.get("content"):
                            st.markdown(f"**Title:** {notice['content']}")
                    with cols[1]:
                        if notice.get("lumen_url"):
                            st.link_button("View on Lumen Database", notice["lumen_url"])
                        company_info = {
                            "name":    company_name,
                            "address": company_address,
                            "phone":   company_phone,
                            "email":   company_email,
                        }
                        pdf_bytes = generate_counter_notice(notice, company_info)
                        st.download_button(
                            label="Download Counter-Notice PDF",
                            data=pdf_bytes,
                            file_name=f"counter_notice_{notice.get('id', 'notice')}.pdf",
                            mime="application/pdf",
                            key=f"pdf_{r['url']}_{notice.get('id')}",
                        )
    else:
        st.success("No DMCA notices found across all URLs.")

    # ── Export CSV ────────────────────────────────────────────────────────────
    df_export = pd.DataFrame([
        {
            "URL":        r["url"],
            "Indexed":    "Yes" if r["indexed"] else "No",
            "Notices":    len(r["notices"]),
            "Notice IDs": ", ".join(str(n.get("id", "")) for n in r["notices"]),
            "Lumen URLs": ", ".join(n.get("lumen_url") or "" for n in r["notices"]),
            "Error":      r.get("indexed_error") or "",
        }
        for r in results
    ])

    st.download_button(
        label="Export Results as CSV",
        data=df_export.to_csv(index=False),
        file_name=f"dmca_check_{date.today()}.csv",
        mime="text/csv",
        use_container_width=True,
    )

    st.caption("Powered by SerpAPI & Lumen Database")
