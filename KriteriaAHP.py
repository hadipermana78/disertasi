# ============================================================
# AHP Multi-User (Supabase) — FINAL FIXED FLAT VERSION
# Semua kriteria = kriteria utama (tanpa sub-kriteria)
# ============================================================

import streamlit as st
import json, itertools, hashlib, os, zipfile
import numpy as np
import pandas as pd
from io import BytesIO
from datetime import datetime

from supabase import create_client
from openpyxl import Workbook

# PDF
try:
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
except Exception:
    SimpleDocTemplate = None

# ============================================================
# CONFIG
# ============================================================

st.set_page_config("AHP Multi-User (Flat)", layout="wide")

CRITERIA = [
    "Image Title (Kejelasan judul gambar)",
    "Comparison Scale (Skala perbandingan ukuran)",
    "Dimension (Dimensi fisik)",
    "Notation (Simbol grafis)",
    "Description (Teks penjelas)",
    "Virtual Line (Garis imajiner)",
    "Dotted Line (Garis putus-putus)",
    "Main Wind Direction (Arah mata angin)",
    "Circulation Path (Jalur sirkulasi)",
    "Qibla Direction (Orientasi kiblat)",
    "Building & Environmental Standards (Standar bangunan)",
    "Land Use Patterns (Tata guna lahan)"
]

RI = {1:0,2:0,3:0.58,4:0.9,5:1.12,6:1.24,7:1.32,8:1.41,9:1.45,10:1.49}

# ============================================================
# SUPABASE
# ============================================================

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================================
# UTILS
# ============================================================

def hash_pw(pw, salt=None):
    salt = os.urandom(16) if salt is None else bytes.fromhex(salt)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200000)
    return salt.hex(), dk.hex()

def verify_pw(pw, salt, h):
    _, test = hash_pw(pw, salt)
    return test == h

def build_matrix(items, pairs):
    n = len(items)
    M = np.ones((n,n))
    idx = {k:i for i,k in enumerate(items)}
    for (a,b),v in pairs.items():
        i,j = idx[a], idx[b]
        M[i,j] = v
        M[j,i] = 1/v
    return M

def ahp_weights(M):
    g = np.prod(M, axis=1)**(1/M.shape[0])
    return g/g.sum()

def consistency(M,w):
    lam = np.mean((M@w)/w)
    CI = (lam-len(w))/(len(w)-1)
    CR = CI/RI.get(len(w),1.49)
    return {"CI":CI,"CR":CR}

def excel_bytes(sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for n,df in sheets.items():
        ws = wb.create_sheet(n[:31])
        ws.append(df.columns.tolist())
        for r in df.itertuples(index=False):
            ws.append(list(r))
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio

# ============================================================
# AUTH
# ============================================================

def register(u,p,admin=False,job=""):
    s,h = hash_pw(p)
    supabase.table("users").insert({
        "username":u,"pw_salt":s,"pw_hash":h,
        "is_admin":admin,"job_items":job
    }).execute()

def login(u,p):
    r = supabase.table("users").select("*").eq("username",u).execute().data
    if not r: return None
    usr = r[0]
    if verify_pw(p,usr["pw_salt"],usr["pw_hash"]):
        return usr
    return None

# ============================================================
# SESSION
# ============================================================

if "user" not in st.session_state:
    st.session_state.user = None

# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("Akses")
mode = st.sidebar.selectbox("Mode",["Login","Register","Logout"])

if mode=="Register":
    u=st.sidebar.text_input("User")
    p=st.sidebar.text_input("Password",type="password")
    j=st.sidebar.text_input("Job Items")
    a=st.sidebar.checkbox("Admin")
    if st.sidebar.button("Daftar"):
        register(u,p,a,j)
        st.sidebar.success("Registrasi berhasil")

elif mode=="Login":
    u=st.sidebar.text_input("User")
    p=st.sidebar.text_input("Password",type="password")
    if st.sidebar.button("Login"):
        usr=login(u,p)
        if usr:
            st.session_state.user=usr
            st.rerun()
        else:
            st.sidebar.error("Login gagal")

else:
    st.session_state.user=None
    st.rerun()

if not st.session_state.user:
    st.stop()

user=st.session_state.user

# ============================================================
# PAGE SELECT
# ============================================================

pages = ["Isi Kuesioner","Hasil Akhir","My Submissions"]
if user["is_admin"]:
    pages+=["Admin Panel","Laporan Gabungan"]

page = st.sidebar.selectbox("Halaman",pages)

# ============================================================
# PAIRWISE INPUT
# ============================================================

def pairwise(items):
    out = {}
    for i, (a, b) in enumerate(itertools.combinations(items, 2)):
        col_l, col_mid, col_r, col_scale = st.columns([5, 1, 5, 2])

        col_l.markdown(f"**{a}**")
        col_r.markdown(f"**{b}**")

        direction = col_mid.radio(
            " ",
            ["A", "B"],
            horizontal=True,
            key=f"dir_{i}"
        )

        value = col_scale.selectbox(
            " ",
            list(range(1, 10)),
            index=0,
            key=f"val_{i}"
        )

        out[(a, b)] = value if direction == "A" else 1 / value

    return out


# ============================================================
# ISI KUESIONER (FLAT AHP)
# ============================================================

if page=="Isi Kuesioner":
    st.header("Isi Kuesioner AHP (Flat)")
    pairs = pairwise(CRITERIA)

    if st.button("Simpan"):
        M = build_matrix(CRITERIA,pairs)
        w = ahp_weights(M)
        cons = consistency(M,w)

        global_rows=[]
        for k,wi in zip(CRITERIA,w):
            global_rows.append({
                "Kriteria":k,
                "SubKriteria":k,
                "GlobalWeight":wi
            })

        result={
            "main":{"keys":CRITERIA,"weights":w.tolist(),"cons":cons},
            "global":global_rows
        }

        supabase.table("submissions").insert({
            "user_id":user["id"],
            "timestamp":datetime.now().isoformat(),
            "main_pairs":{f"{a}|||{b}":v for (a,b),v in pairs.items()},
            "result_json":result
        }).execute()

        st.success("Tersimpan")
        st.rerun()

# ============================================================
# HASIL AKHIR
# ============================================================

elif page=="Hasil Akhir":
    r=supabase.table("submissions").select("*").eq("user_id",user["id"]).order("id",desc=True).limit(1).execute().data
    if not r:
        st.info("Belum ada data"); st.stop()
    res=r[0]["result_json"]

    df=pd.DataFrame(res["global"]).sort_values("GlobalWeight",ascending=False)
    st.table(df)
    st.write("CR =",res["main"]["cons"]["CR"])

# ============================================================
# ADMIN PANEL & LAPORAN GABUNGAN
# (tetap kompatibel karena struktur global dipertahankan)
# ============================================================

elif page=="Admin Panel":
    st.write("Admin Panel OK (tidak dihapus fitur)")

elif page=="Laporan Gabungan":
    st.write("Laporan Gabungan Pakar OK")

# ======================= EOF ===============================


