# ============================================================
# app_ahp_supabase_FINAL_CLEAN.py
# AHP Multi-User (FLAT) — Supabase
# FINAL CLEAN — READY TO DEPLOY
# ============================================================

import streamlit as st
import json
import itertools
import numpy as np
import pandas as pd
from io import BytesIO
from datetime import datetime
import hashlib
import os
import zipfile

from supabase import create_client
from openpyxl import Workbook

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AHP Multi-User (Final Clean)",
    layout="wide"
)

# ============================================================
# SUPABASE
# ============================================================

if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
    st.error("SUPABASE_URL dan SUPABASE_KEY belum dikonfigurasi.")
    st.stop()

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

# ============================================================
# DATA AHP
# ============================================================

CRITERIA = [
    "Image Title",
    "Comparison Scale",
    "Dimension",
    "Notation",
    "Description",
    "Virtual Line",
    "Dotted Line",
    "Main Wind Direction",
    "Circulation Path",
    "Qibla Direction",
    "Building and Environmental Standards",
    "Land Use Patterns"
]

RI_DICT = {
    1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24,
    7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49, 11: 1.51, 12: 1.48
}

# ============================================================
# AUTH (PBKDF2)
# ============================================================

def hash_password(password, salt=None):
    salt = os.urandom(16) if salt is None else bytes.fromhex(salt)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200000)
    return salt.hex(), dk.hex()

def verify_password(password, salt_hex, hash_hex):
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200000)
    return dk.hex() == hash_hex

# ============================================================
# AHP CORE
# ============================================================

def build_matrix(items, pairs):
    n = len(items)
    M = np.ones((n, n))
    idx = {k: i for i, k in enumerate(items)}
    for (a, b), v in pairs.items():
        i, j = idx[a], idx[b]
        M[i, j] = v
        M[j, i] = 1 / v
    return M

def ahp_weights(M):
    gm = np.prod(M, axis=1) ** (1 / M.shape[0])
    return gm / gm.sum()

def consistency(M, w):
    n = M.shape[0]
    lam = np.mean((M @ w) / w)
    CI = (lam - n) / (n - 1)
    CR = CI / RI_DICT.get(n, 1.49)
    return CI, CR

# ============================================================
# EXCEL
# ============================================================

def to_excel(sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for name, df in sheets.items():
        ws = wb.create_sheet(name[:31])
        ws.append(list(df.columns))
        for r in df.itertuples(index=False):
            ws.append(list(r))
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio

# ============================================================
# DB FUNCTIONS
# ============================================================

def register_user(username, password, is_admin, job_items):
    salt, h = hash_password(password)
    supabase.table("users").insert({
        "username": username,
        "pw_salt": salt,
        "pw_hash": h,
        "is_admin": is_admin,
        "job_items": job_items
    }).execute()

def login(username, password):
    res = supabase.table("users").select("*").eq("username", username).execute().data
    if not res:
        return None
    u = res[0]
    if verify_password(password, u["pw_salt"], u["pw_hash"]):
        return u
    return None

def save_submission(uid, main_pairs, result):
    supabase.table("submissions").insert({
        "user_id": uid,
        "timestamp": datetime.now().isoformat(),
        "main_pairs": main_pairs,
        "result_json": result
    }).execute()

def latest_submission(uid):
    r = supabase.table("submissions").select("*").eq("user_id", uid).order("id", desc=True).limit(1).execute().data
    return r[0] if r else None

def latest_all():
    users = supabase.table("users").select("*").execute().data
    out = []
    for u in users:
        s = latest_submission(u["id"])
        if s:
            out.append((u, s))
    return out

# ============================================================
# SESSION
# ============================================================

if "user" not in st.session_state:
    st.session_state.user = None

# ============================================================
# SIDEBAR AUTH
# ============================================================

st.sidebar.title("Akses")

mode = st.sidebar.selectbox("Mode", ["Login", "Register", "Logout"])

if mode == "Register":
    u = st.sidebar.text_input("Username")
    p = st.sidebar.text_input("Password", type="password")
    j = st.sidebar.text_input("Job Items")
    a = st.sidebar.checkbox("Admin")
    if st.sidebar.button("Daftar"):
        register_user(u, p, a, j)
        st.sidebar.success("Registrasi berhasil")

elif mode == "Login":
    u = st.sidebar.text_input("Username")
    p = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Login"):
        user = login(u, p)
        if user:
            st.session_state.user = user
            st.sidebar.success("Login berhasil")
        else:
            st.sidebar.error("Login gagal")

elif mode == "Logout":
    st.session_state.user = None
    st.sidebar.info("Logout")

if not st.session_state.user:
    st.title("AHP Multi-User")
    st.stop()

user = st.session_state.user

# ============================================================
# PAGE SELECT
# ============================================================

pages = ["Isi Kuesioner", "Hasil Saya"]
if user["is_admin"]:
    pages.append("Admin – Gabungan Pakar")

page = st.sidebar.selectbox("Halaman", pages)

# ============================================================
# PAIRWISE INPUT
# ============================================================

def pairwise_ui(items):
    pairs = {}
    for a, b in itertools.combinations(items, 2):
        c1, c2, c3 = st.columns([5, 2, 5])
        c1.write(a)
        key = hashlib.md5(f"{a}-{b}".encode()).hexdigest()
        dir_ = c2.radio("",
                        ["←", "→"],
                        key=f"d_{key}",
                        horizontal=True,
                        label_visibility="collapsed")
        scale = c3.selectbox(b, list(range(1, 10)), key=f"s_{key}")
        pairs[(a, b)] = scale if dir_ == "←" else 1 / scale
    return pairs

# ============================================================
# PAGE: KUESIONER
# ============================================================

if page == "Isi Kuesioner":
    st.header("Kuesioner AHP (Kriteria Utama)")
    main_pairs = pairwise_ui(CRITERIA)

    if st.button("Simpan"):
        M = build_matrix(CRITERIA, main_pairs)
        w = ahp_weights(M)
        CI, CR = consistency(M, w)

        result = {
            "main": {
                "keys": CRITERIA,
                "weights": list(map(float, w)),
                "CI": CI,
                "CR": CR
            },
            "global": [
                {"Kriteria": k, "GlobalWeight": float(v)}
                for k, v in zip(CRITERIA, w)
            ]
        }

        save_submission(
            user["id"],
            {f"{a}|||{b}": v for (a, b), v in main_pairs.items()},
            result
        )

        st.success("Tersimpan")
        st.rerun()

# ============================================================
# PAGE: HASIL SAYA
# ============================================================

elif page == "Hasil Saya":
    sub = latest_submission(user["id"])
    if not sub:
        st.info("Belum ada data")
        st.stop()

    res = sub["result_json"]
    if isinstance(res, str):
        res = json.loads(res)

    df = pd.DataFrame(res["global"]).sort_values("GlobalWeight", ascending=False)
    st.table(df)
    st.write(f"CI={res['main']['CI']:.4f} | CR={res['main']['CR']:.4f}")

    excel = to_excel({
        "Global": df
    })

    st.download_button(
        "Download Excel",
        excel,
        "hasil_ahp.xlsx"
    )

# ============================================================
# ADMIN: GABUNGAN
# ============================================================

elif page == "Admin – Gabungan Pakar":
    rows = latest_all()
    mats = []

    for u, s in rows:
        mp = {
            tuple(k.split("|||")): v
            for k, v in s["main_pairs"].items()
        }
        mats.append(build_matrix(CRITERIA, mp))

    GM = np.exp(np.mean(np.log(mats), axis=0))
    w = ahp_weights(GM)
    CI, CR = consistency(GM, w)

    df = pd.DataFrame({
        "Kriteria": CRITERIA,
        "Bobot_AI J": w
    })

    st.table(df)
    st.write(f"CI={CI:.4f} | CR={CR:.4f}")

# ============================================================
# EOF
# ============================================================
