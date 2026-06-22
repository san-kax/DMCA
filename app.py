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
    page_icon="shield",
    layout="wide",
    initial_sidebar_state="expanded",
)

from checker import check_single_url          # noqa: E402
from counter_notice import generate_counter_notice  # noqa: E402

# ── Sidebar – company info ────────────────────────────────────────────────────
with st.sidebar:
    st.header("Company Info")
    st.caption("Pre-filled into counter-notice PDFs")
    company_name    = st.text_input("Company Name",  value="GDC Group")
    company_address = st.text_input("Address",       value="Fitzwilliam Court 3rd Floor, Leeson Cl, Dublin 2, Ireland")
    company_phone   = st.text_input("Phone",         value="+353 1 903 8375")
    company_email   = st.text_input("Email",         value="sandeep.kumar@gdcgroup.com")
    st.divider()
    st.caption("Powered by SerpAPI & Lumen Database")

# ── Header ────────────────────────────────────────────────────────────────────
st.title("DMCA Monitor")
st.caption("URL Index & Takedown Checker — powered by SerpAPI & Lumen Database")

st.divider()

# ── URL input ─────────────────────────────────────────────────────────────────
col_upload, col_paste = st.columns([1, 1])

with col_upload:
    uploaded_file = st.file_uploader(
        "Upload CSV",
        type=["csv"],
        help="Any column named url, URL, link, or the first column is used.",
    )

with col_paste:
    manual_urls = st.text_area("Or paste URLs (one per line)", height=120)

# Parse URLs from both sources
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

# Deduplicate preserving order
seen: set = set()
urls = [u for u in urls if not (u in seen or seen.add(u))]

if urls:
    st.info(f"**{len(urls)} URLs** loaded — estimated time: ~{len(urls) * 2 // 60} min {(len(urls) * 2) % 60} sec")

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
        box_total.metric("Checked",       len(results))
        box_indexed.metric("Indexed",     indexed)
        box_notices.metric("DMCA Notices", notices)

    def refresh_table():
        rows = []
        for idx, r in enumerate(results, 1):
            notice_ids = ", ".join(
                str(n["id"]) for n in r["notices"] if n.get("id")
            ) or ("Yes" if r["notices"] else "—")
            # If indexed AND has DMCA, notice likely targets a sub-page
            dmca_scope = " (sub-page)" if r["indexed"] and r["notices"] else ""
            rows.append({
                "#":            idx,
                "URL":          r["url"],
                "Indexed":      "Yes" if r["indexed"] else "No",
                "DMCA Notices": (notice_ids + dmca_scope) if notice_ids != "—" else "—",
                "Error":        (r.get("indexed_error") or "")[:80],
            })
        table_placeholder.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

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

    # ── Summary ───────────────────────────────────────────────────────────────
    notices_found = [r for r in results if r["notices"]]

    if notices_found:
        st.error(f"{len(notices_found)} URL(s) have DMCA notices — counter-notices available below.")
        for r in notices_found:
            with st.expander(f"DMCA: {r['url']}"):
                if r["indexed"]:
                    st.info("This URL is still indexed — the DMCA notice likely targets a sub-page under this path, not this exact URL.")
                for notice in r["notices"]:
                    st.write(f"**Lumen Notice ID:** {notice.get('id') or 'N/A'}")
                    if notice.get("lumen_url"):
                        st.write(f"**Lumen Record:** {notice['lumen_url']}")
                    if notice.get("content"):
                        st.write(f"**Notice title:** {notice['content']}")

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
