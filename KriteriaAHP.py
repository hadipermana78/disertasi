# =========================================================
# AHP FLAT (NO SUB-CRITERIA) — SUPABASE MULTI USER
# FINAL CLEAN VERSION — STABLE
# =========================================================

import streamlit as st
import json
import itertools
import numpy as np
import pandas as pd
from io import BytesIO
from datetime import datetime
import hashlib
import os

from supabase import create_client

# =========================
# OPTIONAL PDF (reportlab)
# =========================
try:
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    PDF_AVAILABLE = True
except Exception:
    PDF_AVAILABLE = False

from openpyxl import Workbook

# =========================================================
# STREAMLIT CONFIG
# =========================================================
st.set_page_config(page_title="AHP Flat Multi-User", layout="wide")

# =========================================================
# SUPABASE SETUP
# =========================================================
if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
    st.error("Supabase secrets belum dikonfigurasi.")
    st.stop()

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)

# =========================================================
# AHP CRITERIA (FLAT)
# =========================================================
CRITERIA = [
    "Image Title — Kejelasan judul gambar",
    "Comparison Scale — Skala perbandingan ukuran",
    "Dimension — Informasi dimensi fisik",
    "Notation — Konsistensi simbol grafis",
    "Description — Teks penjelas gambar",
    "Virtual Line — Garis imajiner relasi",
    "Dotted Line — Garis putus non-fisik",
    "Main Wind Direction — Arah angin utama",
    "Circulation Path — Jalur sirkulasi",
    "Qibla Direction — Orientasi kiblat",
    "Building & Environmental Standards — Standar bangunan",
    "Land Use Patterns — Pola tata guna lahan"
]

RI_DICT = {1:0,2:0,3:0.58,4:0.90,5:1.12,6:1.24,7:1.32,8:1.41,9:1.45,10:1.49}

# =========================================================
# AHP FUNCTIONS
# =========================================================
def build_matrix(items, pairs):
    n = len(items)
    M = np.ones((n, n))
    idx = {k:i for i,k in enumerate(items)}
    for (a,b), v in pairs.items():
        i,j = idx[a], idx[b]
        M[i,j] = v
        M[j,i] = 1/v
    return M

def ahp_weights(M):
    gm = np.prod(M, axis=1) ** (1/M.shape[0])
    return gm / gm.sum()

def consistency(M, w):
    n = M.shape[0]
    lamda = np.mean((M @ w) / w)
    CI = (lamda-n)/(n-1) if n>1 else 0
    CR = CI / RI_DICT.get(n,1.49) if n>2 else 0
    return CI, CR

# =========================================================
# AUTH HELPERS
# =========================================================
def hash_pw(pw, salt=None):
    salt = os.urandom(16) if salt is None else bytes.fromhex(salt)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200000)
    return salt.hex(), h.hex()

def verify_pw(pw, salt, h):
    return hash_pw(pw, salt)[1] == h

# =========================================================
# FILE EXPORT
# =========================================================
def to_excel(sheets:dict):
    wb = Workbook()
    wb.remove(wb.active)
    for name, df in sheets.items():
        ws = wb.create_sheet(name[:31])
        ws.append(df.columns.tolist())
        for r in df.itertuples(index=False):
            ws.append(list(r))
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio

def to_pdf(meta, df):
    if not PDF_AVAILABLE:
        return None
    bio = BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=A4)
    styles = getSampleStyleSheet()
    elems = []

    elems.append(Paragraph("<b>Laporan Hasil AHP</b>", styles["Title"]))
    elems.append(Spacer(1,12))

    for k,v in meta.items():
        elems.append(Paragraph(f"<b>{k}:</b> {v}", styles["Normal"]))

    elems.append(Spacer(1,12))

    table = Table(
        [["No","Kriteria","Bobot"]] +
        [[i+1,r.Kriteria,f"{r.Bobot:.4f}"] for i,r in df.iterrows()],
        colWidths=[30,350,80]
    )
    table.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.5,colors.black),
        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey)
    ]))

    elems.append(table)
    doc.build(elems)
    bio.seek(0)
    return bio

# =========================================================
# SESSION
# =========================================================
if "user" not in st.session_state:
    st.session_state.user = None

# =========================================================
# SIDEBAR AUTH
# =========================================================
st.sidebar.title("Akses")
mode = st.sidebar.selectbox("Mode", ["Login","Register","Logout"])

if mode == "Register":
    u = st.sidebar.text_input("Username")
    p = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Daftar"):
        salt,h = hash_pw(p)
        supabase.table("users").insert({
            "username":u,"pw_salt":salt,"pw_hash":h
        }).execute()
        st.sidebar.success("Registrasi berhasil")

elif mode == "Login":
    u = st.sidebar.text_input("Username")
    p = st.sidebar.text_input("Password", type="password")
    if st.sidebar.button("Masuk"):
        r = supabase.table("users").select("*").eq("username",u).execute().data
        if r and verify_pw(p, r[0]["pw_salt"], r[0]["pw_hash"]):
            st.session_state.user = r[0]
            st.sidebar.success("Login berhasil")
        else:
            st.sidebar.error("Login gagal")

else:
    st.session_state.user = None

if not st.session_state.user:
    st.title("AHP Flat Multi-User")
    st.info("Silakan login")
    st.stop()

# =========================================================
# MAIN PAGE
# =========================================================
st.title("Kuesioner AHP (Tanpa Sub-Kriteria)")

pairs = {}
for a,b in itertools.combinations(CRITERIA,2):
    c1,c2,c3,c4 = st.columns([6,1,6,2])
    c1.write(a)
    c3.write(b)
    d = c2.radio("",["A","B"],horizontal=True)
    v = c4.selectbox("",range(1,10))
    pairs[(a,b)] = v if d=="A" else 1/v

if st.button("Simpan & Hitung"):
    M = build_matrix(CRITERIA,pairs)
    w = ahp_weights(M)
    CI,CR = consistency(M,w)

    df = pd.DataFrame({
        "Kriteria":CRITERIA,
        "Bobot":w
    })

    supabase.table("submissions").insert({
        "user_id":st.session_state.user["id"],
        "timestamp":datetime.now().isoformat(),
        "result_json":{
            "weights":w.tolist(),
            "CI":CI,
            "CR":CR
        }
    }).execute()

    st.success("Data tersimpan")

    st.subheader("Hasil")
    st.table(df)
    st.write(f"CI = {CI:.4f} | CR = {CR:.4f}")

    st.download_button(
        "📊 Download Excel",
        to_excel({"AHP":df}),
        "hasil_ahp.xlsx"
    )

    if PDF_AVAILABLE:
        pdf = to_pdf(
            {"User":st.session_state.user["username"],"CR":f"{CR:.4f}"},
            df
        )
        st.download_button("📄 Download PDF", pdf, "hasil_ahp.pdf")

# ======================= EOF =======================
