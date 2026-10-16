# Created by Luke Purdy (GitHub: dublove16v). Copyright (c) 2026-2026 Luke Purdy. All rights reserved. See AUTHORSHIP.md.
"""Airsoft locker. Receipts load from Supabase after sign-in. Session edits stay in the browser."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).parent
PART_STATUSES = ("stock", "installed", "broken", "refunded", "returned")
GUN_STATUSES = ("active", "sold", "refunded", "returned")
PLATFORMS = ("aeg", "gbb", "hpa", "spring", "other")
CATEGORIES = (
    "motor",
    "hop",
    "barrel",
    "internal",
    "external",
    "mag",
    "optic",
    "gear",
    "clothing",
    "hpa",
    "other",
)


def money(amount: float) -> str:
    return f"${amount:,.2f}"


def cash_back(row: dict) -> float:
    if row.get("refund") is not None:
        return float(row["refund"])
    if row.get("status") in ("refunded", "returned"):
        return float(row.get("cost") or 0)
    return 0.0


def load_rows() -> list:
    """Receipts live in Supabase (table armory_receipts, RLS on, server key only).
    Called only after sign-in."""
    import requests

    url = str(st.secrets["SUPABASE_URL"]).rstrip("/")
    key = str(st.secrets["SUPABASE_KEY"])
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    rows, start = [], 0
    while True:
        r = requests.get(f"{url}/rest/v1/armory_receipts", params={"select": "data", "order": "pos"},
                         headers={**h, "Range": f"{start}-{start + 999}"}, timeout=20)
        r.raise_for_status()
        batch = r.json()
        rows.extend(b["data"] for b in batch)
        if len(batch) < 1000:
            return rows
        start += 1000


def seed() -> dict:
    rows = load_rows()
    replicas: list[dict] = []
    parts: list[dict] = []
    for row in rows:
        base = {
            "id": row["id"],
            "name": row.get("name") or "Untitled",
            "cost": float(row.get("cost") or 0),
            "refund": float(row["refund"]) if row.get("refund") not in (None, "") else None,
            "date": row.get("date") or "",
            "source": row.get("source") or "",
            "notes": row.get("notes") or "",
        }
        if row.get("kind") == "replica":
            status = row.get("status") or "active"
            if status not in GUN_STATUSES:
                status = "active"
            replicas.append(
                {
                    **base,
                    "platform": row.get("platform") or "",
                    "origin": row.get("origin") or "purchased",
                    "status": status,
                }
            )
        else:
            status = row.get("status") or "stock"
            if status not in PART_STATUSES:
                status = "stock"
            parts.append(
                {
                    **base,
                    "category": row.get("category") or "other",
                    "seller": row.get("seller") or "",
                    "order_ref": row.get("orderRef") or "",
                    "replica_id": None,
                    "status": status,
                }
            )
    replicas.sort(key=lambda r: (r["date"], r["name"]), reverse=True)
    parts.sort(key=lambda p: (p["date"], p["name"]), reverse=True)
    return {"replicas": replicas, "parts": parts}


def export_rows() -> str:
    locker = st.session_state.locker
    rows = []
    for gun in locker["replicas"]:
        rows.append(
            {
                "id": gun["id"],
                "kind": "replica",
                "name": gun["name"],
                "platform": gun["platform"],
                "cost": gun["cost"],
                "refund": gun["refund"],
                "date": gun["date"],
                "source": gun["source"],
                "origin": gun["origin"],
                "status": gun["status"],
                "notes": gun["notes"],
            }
        )
    for part in locker["parts"]:
        rows.append(
            {
                "id": part["id"],
                "kind": "part",
                "name": part["name"],
                "category": part["category"],
                "cost": part["cost"],
                "refund": part["refund"],
                "date": part["date"],
                "source": part["source"],
                "seller": part["seller"],
                "orderRef": part["order_ref"],
                "replica_id": part["replica_id"],
                "status": part["status"],
                "notes": part["notes"],
            }
        )
    return json.dumps(rows, indent=2)


def counts_on(parts: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for part in parts:
        if not part["replica_id"] or part["status"] in ("broken", "refunded", "returned"):
            continue
        counts[part["replica_id"]] = counts.get(part["replica_id"], 0) + 1
    return counts


def forget_mate_widget(part_id: str) -> None:
    st.session_state.pop(f"mate-{part_id}", None)


def mark_sold(gun_id: str) -> None:
    locker = st.session_state.locker
    for gun in locker["replicas"]:
        if gun["id"] == gun_id:
            gun["status"] = "sold"
    for part in locker["parts"]:
        if part["replica_id"] == gun_id and part["status"] == "installed":
            part["replica_id"] = None
            part["status"] = "stock"
            forget_mate_widget(part["id"])


def restore_gun(gun_id: str) -> None:
    for gun in st.session_state.locker["replicas"]:
        if gun["id"] == gun_id:
            gun["status"] = "active"


def mate(part_id: str, replica_id: str | None) -> None:
    for part in st.session_state.locker["parts"]:
        if part["id"] != part_id:
            continue
        part["replica_id"] = replica_id or None
        if part["status"] not in ("broken", "refunded", "returned"):
            part["status"] = "installed" if replica_id else "stock"
        return


def set_part_status(part_id: str, status: str) -> None:
    for part in st.session_state.locker["parts"]:
        if part["id"] == part_id:
            part["status"] = status
            return


st.set_page_config(page_title="Armory · Airsoft Locker", page_icon="🎯", layout="wide")

from armory_auth import require_login

require_login()
if "locker" not in st.session_state:
    st.session_state.locker = seed()

replicas = st.session_state.locker["replicas"]
parts = st.session_state.locker["parts"]
active = [gun for gun in replicas if gun["status"] == "active"]
sold = [gun for gun in replicas if gun["status"] == "sold"]
refunded_guns = [gun for gun in replicas if gun["status"] in ("refunded", "returned")]
live_parts = [part for part in parts if part["status"] not in ("broken", "refunded", "returned")]
archived_parts = [part for part in parts if part["status"] in ("broken", "refunded", "returned")]
charged = sum(row["cost"] for row in replicas) + sum(row["cost"] for row in parts)
dropped = sum(cash_back(row) for row in replicas) + sum(cash_back(row) for row in parts)
on_gun = counts_on(parts)
gun_by_id = {gun["id"]: gun for gun in replicas}

st.title("Armory")
st.caption(
    "Opened receipts are loaded. Mate a part to the gun it lives on. "
    "Refunded and returned cash drops out of the net. Sold guns and broken parts still count."
)
stat_net, stat_charged, stat_back = st.columns(3)
stat_net.metric("Net kept", money(charged - dropped))
stat_charged.metric("Charged", money(charged))
stat_back.metric("Refunded", money(dropped))

with st.sidebar:
    st.header("Locker")
    st.write(f"{len(active)} guns in the rack")
    st.write(f"{len(live_parts)} parts in the pile")
    st.write(f"{len(archived_parts) + len(sold) + len(refunded_guns)} archived")
    st.download_button(
        "Download this session",
        data=export_rows(),
        file_name="armory-session.json",
        mime="application/json",
    )
    if st.button("Reset to receipts"):
        for key in list(st.session_state):
            if key.startswith("mate-"):
                del st.session_state[key]
        st.session_state.locker = seed()
        st.rerun()

guns_tab, parts_tab, archive_tab = st.tabs(
    [
        f"Guns {len(active)}",
        f"Parts {len(live_parts)}",
        f"Archive {len(sold) + len(refunded_guns) + len(archived_parts)}",
    ]
)

with guns_tab:
    with st.form("add-gun", clear_on_submit=True):
        name_col, platform_col, cost_col = st.columns([3, 1, 1])
        gun_name = name_col.text_input("Street gun", placeholder="Name")
        gun_platform = platform_col.selectbox("Platform", PLATFORMS)
        gun_cost = cost_col.number_input("Cost", min_value=0.0, step=1.0, format="%.2f", key="new-gun-cost")
        add_gun = st.form_submit_button("Add gun")
    if add_gun:
        if not gun_name.strip():
            st.warning("Name the gun first.")
        else:
            replicas.insert(
                0,
                {
                    "id": f"street-{uuid.uuid4()}",
                    "name": gun_name.strip(),
                    "cost": float(gun_cost),
                    "refund": None,
                    "date": "",
                    "source": "street",
                    "notes": "Off the street",
                    "platform": gun_platform,
                    "origin": "street",
                    "status": "active",
                },
            )
            st.rerun()

    if not active:
        st.info("No active guns.")
    for gun in active:
        left, right = st.columns([5, 1])
        platform = gun["platform"].upper() if gun["platform"] else gun["source"]
        origin = "Street" if gun["origin"] == "street" else gun["source"]
        left.markdown(f"**{gun['name']}**")
        left.caption(
            f"{platform} · {origin} · {gun['date'] or 'no date'} · {on_gun.get(gun['id'], 0)} parts · {money(gun['cost'])}"
        )
        if right.button("Mark sold", key=f"sold-{gun['id']}"):
            mark_sold(gun["id"])
            st.rerun()

with parts_tab:
    with st.form("add-part", clear_on_submit=True):
        name_col, cat_col, cost_col, gun_col = st.columns([3, 1, 1, 2])
        part_name = name_col.text_input("Part", placeholder="Name")
        part_cat = cat_col.selectbox("Category", CATEGORIES)
        part_cost = cost_col.number_input("Cost", min_value=0.0, step=1.0, format="%.2f", key="new-part-cost")
        mate_choice = gun_col.selectbox(
            "Mate to",
            options=[""] + [gun["id"] for gun in active],
            format_func=lambda gun_id: "Unassigned" if not gun_id else gun_by_id[gun_id]["name"],
        )
        add_part = st.form_submit_button("Add part")
    if add_part:
        if not part_name.strip():
            st.warning("Name the part first.")
        else:
            parts.insert(
                0,
                {
                    "id": f"manual-{uuid.uuid4()}",
                    "name": part_name.strip(),
                    "cost": float(part_cost),
                    "refund": None,
                    "date": "",
                    "source": "other",
                    "notes": "",
                    "category": part_cat,
                    "seller": "",
                    "order_ref": "",
                    "replica_id": mate_choice or None,
                    "status": "installed" if mate_choice else "stock",
                },
            )
            st.rerun()

    filter_col, search_col = st.columns([1, 2])
    gun_filter = filter_col.selectbox(
        "On gun",
        options=["", * [gun["id"] for gun in active]],
        format_func=lambda gun_id: "All guns" if not gun_id else gun_by_id[gun_id]["name"],
    )
    query = search_col.text_input("Search parts", placeholder="motor, hop, evike…").strip().lower()
    shown = []
    for part in live_parts:
        if gun_filter and part["replica_id"] != gun_filter:
            continue
        haystack = " ".join(
            [
                part["name"],
                part["category"],
                part["source"],
                part["seller"],
                part["order_ref"],
                part["notes"],
            ]
        ).lower()
        if query and query not in haystack:
            continue
        shown.append(part)
    st.caption(f"{len(shown)} in this view")
    mate_options = [""] + [gun["id"] for gun in active]
    for part in shown[:40]:
        info, mate_col, action = st.columns([4, 2, 1])
        info.markdown(f"**{part['name']}**")
        bits = [part["category"], part["source"], part["date"] or "no date", money(part["cost"])]
        if part["order_ref"]:
            bits.append(part["order_ref"])
        info.caption(" · ".join(bits))
        mate_col.selectbox(
            "Gun",
            options=mate_options,
            index=mate_options.index(part["replica_id"]) if part["replica_id"] in mate_options else 0,
            format_func=lambda gun_id: "Not on a gun" if not gun_id else gun_by_id[gun_id]["name"],
            key=f"mate-{part['id']}",
            label_visibility="collapsed",
            on_change=lambda part_id: mate(part_id, st.session_state.get(f"mate-{part_id}") or None),
            args=(part["id"],),
        )
        if action.button("Broken", key=f"broken-{part['id']}"):
            set_part_status(part["id"], "broken")
            st.rerun()
    if len(shown) > 40:
        st.caption("Showing the first 40. Search to narrow the pile.")

with archive_tab:
    st.subheader("Sold guns")
    if not sold:
        st.caption("Nothing sold yet.")
    for gun in sold:
        left, right = st.columns([5, 1])
        left.markdown(f"**{gun['name']}**")
        left.caption(money(gun["cost"]))
        if right.button("Restore", key=f"restore-gun-{gun['id']}"):
            restore_gun(gun["id"])
            st.rerun()

    st.subheader("Refunded guns")
    if not refunded_guns:
        st.caption("No refunded guns.")
    for gun in refunded_guns:
        st.markdown(f"**{gun['name']}**")
        st.caption(
            f"{gun['status'].upper()} · charged {money(gun['cost'])} · back {money(cash_back(gun))}"
            + (f" · {gun['notes']}" if gun["notes"] else "")
        )

    st.subheader("Broken, refunded, returned")
    if not archived_parts:
        st.caption("No archived parts.")
    for part in archived_parts:
        left, right = st.columns([5, 1])
        left.markdown(f"**{part['name']}**")
        note = f" · {part['notes']}" if part["notes"] else ""
        back = ""
        if part["status"] in ("refunded", "returned"):
            back = f" · back {money(cash_back(part))}"
        left.caption(f"{part['status'].upper()} · {money(part['cost'])}{back}{note}")
        if part["status"] == "broken" and right.button("Restore", key=f"restore-part-{part['id']}"):
            set_part_status(part["id"], "installed" if part["replica_id"] else "stock")
            st.rerun()

__author__ = "Luke Purdy"
