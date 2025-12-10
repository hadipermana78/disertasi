import streamlit as st
import numpy as np
import pandas as pd
from supabase import create_client, Client
from math import sqrt

# -----------------------------------------------------
# SUPABASE CONFIG
# -----------------------------------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------------------------------
# AUTH FUNCTIONS (LOGIN)
# -----------------------------------------------------
def login(username, password):
    user = supabase.table("users").select("*").eq("username", username).execute()
    if user.data:
        row = user.data[0]
        if password == row["hashed_password"]:   # gunakan hashed bila perlu
            return row
    return None

# -----------------------------------------------------
# NEW AHP CRITERIA (POLUSI VISUAL)
# -----------------------------------------------------

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
        "A10. Kendaraan Non-Bermotor"
    ],
    "B. Indikator Kontekstual": [
        "B1. Jumlah Bangunan",
        "B2. Rata-rata Jumlah Lantai",
        "B3. Fungsi Komersial",
        "B4. Hunian / Rumah",
        "B5. Tipe Jalan"
    ],
    "C. Elemen Estetika / Penurun Polusi": [
        "C1. Tumbuhan / Vegetasi",
        "C2. Seni Publik",
        "C3. Langit / Haze"
    ]
}

# -----------------------------------------------------
# AHP FUNCTIONS
# -----------------------------------------------------
def pairwise_matrix(items, inputs):
    n = len(items)
    M = np.ones((n, n))
    idx = 0
    for i in range(n):
        for j in range(i+1, n):
            M[i,j] = inputs[idx]
            M[j,i] = 1 / inputs[idx]
            idx += 1
    return M

def ahp_weights(matrix):
    eigen_vals, eigen_vecs = np.linalg.eig(matrix)
    max_index = np.argmax(eigen_vals)
    principal = eigen_vecs[:, max_index].real
    weights = principal / principal.sum()

    n = matrix.shape[0]
    λ_max = eigen_vals[max_index].real
    CI = (λ_max - n) / (n - 1) if n > 1 else 0
    RI_table = {1:0,2:0,3:0.58,4:0.9,5:1.12,6:1.24,7:1.32,8:1.41,9:1.45,10:1.49}
    CR = CI / RI_table[n] if n in RI_table and RI_table[n] != 0 else 0

    return weights, CI, CR

# -----------------------------------------------------
# PAGE LAYOUT
# -----------------------------------------------------
st.set_page_config(page_title="AHP Polusi Visual", layout="wide")

st.title("AHP – Penilaian Polusi Visual (Versi Final)")

# -----------------------------------------------------
# LOGIN SECTION
# -----------------------------------------------------
if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    st.subheader("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Masuk"):
        user = login(username, password)
        if user:
            st.session_state.user = user
            st.success("Login berhasil!")
            st.rerun()
        else:
            st.error("Username / password salah")
    st.stop()

user = st.session_state.user
st.success(f"Anda login sebagai **{user['username']}** ({user['role']})")

# -----------------------------------------------------
# PILIH JOB ITEM
# -----------------------------------------------------
st.subheader("Pilih Gambar / Job Item")

jobs = supabase.table("job_items").select("*").execute().data
job_options = {f"{j['id']} – {j.get('description','(tanpa judul)')}": j["id"] for j in jobs}

if not jobs:
    st.warning("Belum ada job items.")
    st.stop()

selected_job = st.selectbox("Pilih item", list(job_options.keys()))
job_id = job_options[selected_job]

# -----------------------------------------------------
# AHP INPUT SECTION
# -----------------------------------------------------
st.header("Form AHP – Penilaian Subkriteria")

all_results = {}

for cat, items in SUBCRITERIA.items():
    st.subheader(cat)

    st.write("Isi perbandingan berpasangan (1–9).")

    pairs = []
    for i in range(len(items)):
        for j in range(i+1, len(items)):
            pairs.append((items[i], items[j]))

    inputs = []
    for left, right in pairs:
        value = st.number_input(
            f"{left}  dibanding  {right}",
            min_value=1.0, max_value=9.0, step=1.0, value=1.0
        )
        inputs.append(value)

    M = pairwise_matrix(items, inputs)
    weights, CI, CR = ahp_weights(M)

    df = pd.DataFrame({
        "Subkriteria": items,
        "Bobot": weights.round(4)
    })

    st.dataframe(df)

    st.info(f"Consistency Ratio (CR): **{CR:.4f}**")

    all_results[cat] = {
        "weights": weights.tolist(),
        "cr": float(CR)
    }

# -----------------------------------------------------
# SAVE BUTTON
# -----------------------------------------------------
if st.button("Simpan Hasil ke Supabase"):

    # Simpan submission
    sub = supabase.table("submissions").insert({
        "job_item_id": job_id,
        "user_id": user["id"],
        "consistency_ratio": float(np.mean([all_results[c]["cr"] for c in all_results]))
    }).execute()

    submission_id = sub.data[0]["id"]

    # Simpan tiap pairwise comparison
    for cat, items in SUBCRITERIA.items():
        pairs = []
        for i in range(len(items)):
            for j in range(i+1, len(items)):
                pairs.append((items[i], items[j]))

        inputs = []
        for left, right in pairs:
            key = f"{cat}_{left}_{right}"
        
        # Loop input ulang dari UI
        idx = 0
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                supabase.table("comparisons").insert({
                    "submission_id": submission_id,
                    "left_item": items[i],
                    "right_item": items[j],
                    "value": float(1.0)  # placeholder jika perlu diisi ulang
                }).execute()
                idx += 1

    st.success("Data berhasil disimpan ke Supabase!")

# -----------------------------------------------------
# HISTORY & REPORT
# -----------------------------------------------------
st.header("Riwayat Penilaian Saya")

my_subs = supabase.table("submissions").select("*").eq("user_id", user["id"]).execute().data

st.write(pd.DataFrame(my_subs))
