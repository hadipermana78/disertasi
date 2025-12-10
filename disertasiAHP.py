# ============================================================
# STREAMLIT AHP MULTI-USER SYSTEM
# Supabase-based — FINAL Version (with job_items + expert reports)
# ============================================================

import streamlit as st
import numpy as np
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import uuid
import json

# ============================================================
# CONFIG — SUPABASE
# ============================================================

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================================================
# LOGIN SYSTEM (simple session)
# ============================================================

def login(username, password):
    res = supabase.table("users").select("*").eq("username", username).execute()
    if len(res.data) == 0:
        return None
    user = res.data[0]
    if user["password"] == password:
        return user
    return None

def require_login():
    if "user" not in st.session_state:
        st.error("Silakan login terlebih dahulu.")
        st.stop()

# ============================================================
# CONFIG — AHP CRITERIA & SUBCRITERIA (POLUSI VISUAL)
# ============================================================

CRITERIA = [
    "A. Polusi Visual Langsung",
    "B. Indikator Kontekstual",
    "C. Elemen Estetika / Penurun Polusi"
]

SUBCRITERIA = {
    "A. Polusi Visual Langsung": [
        "A1. Papan Iklan (Billboards)",
        "A2. Papan Tanda (Signs)",
        "A3. Graffiti",
        "A4. Utilitas (Tiang/Kabel Listrik)",
        "A5. Pagar (Fences)",
        "A6. Furnitur Jalan (Kursi, Tong Sampah, Kios, Tiang)",
        "A7. Pedagang Kaki Lima (PKL)",
        "A8. Jalan Rusak",
        "A9. Kendaraan Bermotor (Parkir/Kemacetan)",
        "A10. Kendaraan Non-Bermotor (Sepeda/Becak Menumpuk)"
    ],

    "B. Indikator Kontekstual": [
        "B1. Jumlah Bangunan",
        "B2. Rata-rata Jumlah Lantai",
        "B3. Keberadaan Fungsi Komersial",
        "B4. Keberadaan Hunian / Rumah",
        "B5. Tipe Jalan (Utama / Sekunder / Trotoar)"
    ],

    "C. Elemen Estetika / Penurun Polusi": [
        "C1. Tumbuhan / Vegetasi",
        "C2. Seni Publik (Public Art / Mural Positif)",
        "C3. Langit / Air (Haze)"
    ]
}

# ============================================================
# AHP HELPERS
# ============================================================

def priority_vector(matrix):
    eigvals, eigvecs = np.linalg.eig(matrix)
    max_index = np.argmax(eigvals)
    vec = np.abs(eigvecs[:, max_index])
    return vec / np.sum(vec)

def consistency_ratio(matrix):
    n = matrix.shape[0]
    vec = priority_vector(matrix)
    lam = np.sum(np.dot(matrix, vec) / vec) / n

    RI_table = {
        1: 0.0,
        2: 0.0,
        3: 0.58,
        4: 0.90,
        5: 1.12,
        6: 1.24,
        7: 1.32,
        8: 1.41,
        9: 1.45,
        10: 1.49
    }

    CI = (lam - n) / (n - 1) if n > 2 else 0
    RI = RI_table.get(n, 1.49)
    return CI / RI if RI != 0 else 0

def build_pairwise_matrix(items, values):
    n = len(items)
    M = np.ones((n, n))
    idx = 0
    for i in range(n):
        for j in range(i+1, n):
            v = values[idx]
            M[i, j] = v
            M[j, i] = 1 / v
            idx += 1
    return M

def num_comparisons(n):
    return n * (n - 1) // 2

# ============================================================
# SAVE & LOAD SUBMISSIONS
# ============================================================

def save_submission(user_id, criteria, subcriteria, weights):
    supabase.table("job_items").insert({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "timestamp": str(datetime.now()),
        "criteria": json.dumps(criteria),
        "subcriteria": json.dumps(subcriteria),
        "weights": json.dumps(weights)
    }).execute()

def get_submissions():
    return supabase.table("job_items").select("*").execute().data

# ============================================================
# APP — UI
# ============================================================

def app_login():
    st.title("🔐 Login AHP System")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        user = login(username, password)
        if user:
            st.session_state.user = user
            st.success("Login berhasil!")
            st.experimental_rerun()
        else:
            st.error("Username atau password salah.")

def app_main():
    require_login()
    st.title("📊 AHP Evaluation — Polusi Visual")

    st.subheader("👋 Selamat datang, " + st.session_state.user["username"])

    # ============================================================
    # PAIRWISE FOR MAIN CRITERIA
    # ============================================================

    st.markdown("## 1️⃣ Perbandingan Berpasangan — **Kriteria Utama**")

    num = num_comparisons(len(CRITERIA))
    criteria_vals = []

    for i in range(len(CRITERIA)):
        for j in range(i+1, len(CRITERIA)):
            v = st.select_slider(
                f"{CRITERIA[i]}  vs  {CRITERIA[j]}",
                options=[1/9, 1/8, 1/7, 1/6, 1/5, 1/4, 1/3, 1/2,
                         1, 2, 3, 4, 5, 6, 7, 8, 9],
                value=1
            )
            criteria_vals.append(v)

    M_criteria = build_pairwise_matrix(CRITERIA, criteria_vals)
    CR_val = consistency_ratio(M_criteria)
    criteria_weights = priority_vector(M_criteria)

    st.write("### ⚖️ Bobot Kriteria")
    st.dataframe(pd.DataFrame({
        "Kriteria": CRITERIA,
        "Bobot": criteria_weights
    }))

    st.warning(f"CR = {CR_val:.4f}")
    if CR_val > 0.1:
        st.error("❌ Konsistensi buruk (CR > 0.1). Mohon perbaiki penilaian.")
    else:
        st.success("✔️ Konsistensi baik.")

    # ============================================================
    # SUBCRITERIA
    # ============================================================

    all_sub_weights = {}

    for crit in CRITERIA:
        st.markdown(f"## 2️⃣ Subkriteria — **{crit}**")

        items = SUBCRITERIA[crit]
        vals = []

        for i in range(len(items)):
            for j in range(i+1, len(items)):
                v = st.select_slider(
                    f"{items[i]}  vs  {items[j]}",
                    options=[1/9, 1/8, 1/7, 1/6, 1/5, 1/4, 1/3, 1/2,
                             1, 2, 3, 4, 5, 6, 7, 8, 9],
                    value=1
                )
                vals.append(v)

        M = build_pairwise_matrix(items, vals)
        weights = priority_vector(M)
        CRx = consistency_ratio(M)

        st.write("### Bobot Subkriteria")
        st.dataframe(pd.DataFrame({
            "Subkriteria": items,
            "Bobot": weights
        }))

        st.warning(f"CR = {CRx:.4f}")
        if CRx > 0.1:
            st.error("❌ Konsistensi subkriteria buruk.")
        else:
            st.success("✔️ Konsistensi baik.")

        all_sub_weights[crit] = dict(zip(items, weights.tolist()))

    # ============================================================
    # SAVE
    # ============================================================

    if st.button("💾 Simpan Hasil Penilaian"):
        save_submission(
            user_id=st.session_state.user["id"],
            criteria=dict(zip(CRITERIA, criteria_weights)),
            subcriteria=all_sub_weights,
            weights=criteria_weights.tolist()
        )
        st.success("✔️ Penilaian berhasil disimpan!")

    # ============================================================
    # EXPERT REPORTS
    # ============================================================

    st.markdown("---")
    st.subheader("📘 Expert Reports (Semua User)")

    data = get_submissions()

    if len(data) == 0:
        st.info("Belum ada laporan.")
    else:
        st.dataframe(pd.DataFrame(data))

# ============================================================
# ROUTER
# ============================================================

if "user" not in st.session_state:
    app_login()
else:
    app_main()

