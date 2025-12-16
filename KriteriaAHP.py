# app_ahp_supabase_jobitems_FINAL_fixed_with_expert_reports.py
# Streamlit AHP Multi-User — Supabase-backed version with job_items (cleaned & fixed)
# Requirements: streamlit==1.38.0, supabase==2.3.3, httpx==0.25.2, numpy, pandas, openpyxl, reportlab, altair

import streamlit as st
import json
import itertools
import numpy as np
import pandas as pd
from io import BytesIO
from datetime import datetime
import hashlib
import os
import zipfile  # <-- baru: untuk mengemas PDF ke ZIP
from reportlab.lib.utils import simpleSplit
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors


from supabase import create_client

# PDF libs (optional)
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
except Exception:
    canvas = None
    A4 = None
    mm = None

from openpyxl import Workbook

st.set_page_config(page_title="AHP Multi-User (Supabase)", layout="wide")

# -------------------------
# Supabase setup & check
# -------------------------
if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
    st.warning("Supabase secrets belum dikonfigurasi. Tambahkan SUPABASE_URL dan SUPABASE_KEY (service_role) di Streamlit Secrets.")
    st.stop()

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ------------------------------
# Utility: Excel writer (openpyxl)
# ------------------------------
def to_excel_bytes(df_dict):
    wb = Workbook()
    # remove default sheet
    default = wb.active
    wb.remove(default)
    for sheet_name, df in df_dict.items():
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)
        ws = wb.create_sheet(sheet_name[:31])
        ws.append(list(df.columns))
        for row in df.itertuples(index=False, name=None):
            ws.append(list(row))
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return output

# ------------------------------
# Config / Data
# ------------------------------
CRITERIA = [
    "Image Title — Kejelasan judul gambar dalam menjelaskan konteks dan fungsi visual",
    "Comparison Scale — Keberadaan dan keterbacaan skala perbandingan ukuran",
    "Dimension — Informasi dimensi fisik bangunan atau elemen ruang",
    "Notation — Konsistensi dan keterbacaan simbol atau tanda grafis",
    "Description — Teks penjelas yang mendukung pemahaman gambar",
    "Virtual Line — Garis imajiner untuk menunjukkan relasi, arah, atau batas",
    "Dotted Line — Garis putus-putus sebagai penanda elemen non-fisik",
    "Main Wind Direction — Informasi arah angin utama dalam konteks lingkungan",
    "Circulation Path — Kejelasan jalur sirkulasi manusia atau kendaraan",
    "Qibla Direction — Orientasi kiblat sebagai pertimbangan religius-spasial",
    "Building and Environmental Standards — Kepatuhan terhadap standar bangunan dan lingkungan",
    "Land Use Patterns — Kesesuaian gambar dengan pola tata guna lahan sekitar"
]


RI_DICT = {1:0.0,2:0.0,3:0.58,4:0.90,5:1.12,6:1.24,7:1.32,8:1.41,9:1.45,10:1.49}

# ------------------------------
# Auth helpers (PBKDF2)
# ------------------------------
def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16)
    else:
        salt = bytes.fromhex(salt)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 200000)
    return salt.hex(), dk.hex()


def verify_password(password, salt_hex, hash_hex):
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 200000)
    return dk.hex() == hash_hex

# ------------------------------
# AHP core functions
# ------------------------------

def build_matrix_from_pairs(items, pair_values):
    n = len(items)
    M = np.ones((n, n), dtype=float)
    idx = {it: i for i, it in enumerate(items)}
    for (a, b), val in pair_values.items():
        if a not in idx or b not in idx:
            continue
        i = idx[a]; j = idx[b]
        M[i, j] = float(val)
        if float(val) != 0:
            M[j, i] = 1.0 / float(val)
    return M


def geometric_mean_weights(mat):
    n = mat.shape[0]
    # handle potential zeros or negative values defensively
    gm = np.prod(mat, axis=1) ** (1.0 / n)
    w = gm / gm.sum()
    return w


def consistency_metrics(mat, weights):
    n = mat.shape[0]
    Aw = mat.dot(weights)
    lambda_max = float(np.mean(Aw / weights))
    CI = (lambda_max - n) / (n - 1) if n > 1 else 0.0
    RI = RI_DICT.get(n, 1.49)
    CR = CI / RI if RI != 0 else 0.0
    return {"lambda_max": lambda_max, "CI": CI, "CR": CR}

# ------------------------------
# PDF generation (reportlab)
# ------------------------------

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors


def make_table(data, col_widths):
    """
    Membuat tabel ReportLab dengan text wrapping (tidak terpotong).
    """
    styles = getSampleStyleSheet()
    styleN = styles["Normal"]

    wrapped_data = []
    for row in data:
        wrapped_row = []
        for cell in row:
            if isinstance(cell, str):
                wrapped_row.append(Paragraph(cell, styleN))
            else:
                wrapped_row.append(cell)
        wrapped_data.append(wrapped_row)

    table = Table(wrapped_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def generate_pdf_bytes(submission_row):
    if canvas is None:
        raise RuntimeError("reportlab not installed")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    elements = []

    elements.append(
        Paragraph(
            "<b>Laporan Hasil AHP – Penataan Ruang Publik</b>",
            styles["Title"]
        )
    )
    elements.append(Spacer(1, 12))

    meta_text = (
        f"<b>User / Pakar:</b> {submission_row.get('username','')}<br/>"
        f"<b>Job Items:</b> {submission_row.get('job_items','')}<br/>"
        f"<b>Waktu:</b> {submission_row.get('timestamp','')}"
    )
    elements.append(Paragraph(meta_text, styles["Normal"]))
    elements.append(Spacer(1, 12))

    # 1. Kriteria Utama
    elements.append(Paragraph("<b>1. Bobot Kriteria Utama</b>", styles["Heading2"]))

    main = submission_row["result"]["main"]
    table_data = [["No", "Kriteria", "Bobot"]]
    for i, (k, w) in enumerate(zip(main["keys"], main["weights"]), start=1):
        table_data.append([str(i), k, f"{w:.4f}"])

    elements.append(make_table(table_data, [30, 350, 80]))
    elements.append(Spacer(1, 12))

    # 2. Global Sub-Kriteria
    elements.append(Paragraph("<b>2. Bobot Global Sub-Kriteria (Top 20)</b>", styles["Heading2"]))

    global_df = pd.DataFrame(submission_row["result"]["global"])
    global_df = global_df.sort_values("GlobalWeight", ascending=False).head(20)

    table_data = [["No", "Sub-Kriteria", "Kriteria", "Bobot Global"]]
    for i, row in enumerate(global_df.itertuples(), start=1):
        table_data.append([
            str(i),
            row.SubKriteria,
            row.Kriteria,
            f"{row.GlobalWeight:.6f}"
        ])

    elements.append(make_table(table_data, [30, 220, 150, 80]))
    elements.append(Spacer(1, 12))

    # 3. Konsistensi
    cons = main["cons"]
    elements.append(Paragraph("<b>3. Ringkasan Konsistensi</b>", styles["Heading2"]))
    elements.append(
        Paragraph(
            f"Kriteria Utama — CI: {cons.get('CI',0):.4f} | CR: {cons.get('CR',0):.4f}",
            styles["Normal"]
        )
    )

    doc.build(elements)
    buffer.seek(0)
    return buffer

# ------------------------------
# Supabase-backed DB operations (with job_items)
# ------------------------------

def register_user(username, password, is_admin=False, job_items=""):
    if not username or not password:
        return False, "Username dan password wajib diisi."
    salt, pw_hash = hash_password(password)
    # normalize job_items to string (comma-separated)
    if isinstance(job_items, list):
        ji = ", ".join(job_items)
    else:
        ji = str(job_items or "").strip()
    payload = {
        "username": username,
        "pw_salt": salt,
        "pw_hash": pw_hash,
        "is_admin": is_admin,
        "job_items": ji
    }
    try:
        res = supabase.table("users").insert(payload).execute()
        if hasattr(res, "error") and res.error:
            return False, f"Registrasi gagal: {getattr(res.error, 'message', str(res.error))}"
        return True, "Registrasi berhasil. Silakan login."
    except Exception as e:
        return False, f"Registrasi gagal: {e}"


def authenticate_user(username, password):
    res = supabase.table("users").select("*").eq("username", username).execute()
    data = getattr(res, "data", res) or []
    if len(data) == 0:
        return False, "User tidak ditemukan."
    user = data[0]
    try:
        if verify_password(password, user["pw_salt"], user["pw_hash"]):
            return True, {
                "id": user["id"],
                "username": user["username"],
                "is_admin": bool(user.get("is_admin", False)),
                "job_items": user.get("job_items", "") or ""
            }
        return False, "Password salah."
    except Exception as e:
        return False, f"Auth error: {e}"


def save_submission(user_id, main_pairs, sub_pairs, result):
    payload = {
        "user_id": user_id,
        "timestamp": datetime.now().isoformat(),
        "main_pairs": main_pairs,
        "sub_pairs": sub_pairs,
        "result_json": result
    }
    res = supabase.table("submissions").insert(payload).execute()
    return getattr(res, "data", res)


def get_user_submissions(user_id):
    res = supabase.table("submissions").select("*").eq("user_id", user_id).order("id", desc=True).execute()
    return getattr(res, "data", []) or []


def delete_submission(submission_id):
    res = supabase.table("submissions").delete().eq("id", submission_id).execute()
    return getattr(res, "data", []) or []


def get_all_submissions_with_user():
    users_res = supabase.table("users").select("*").order("username", desc=False).execute()
    users = getattr(users_res, "data", []) or []
    all_rows = []
    for u in users:
        sid_res = supabase.table("submissions").select("*").eq("user_id", u["id"]).order("id", desc=True).limit(1).execute()
        subs = getattr(sid_res, "data", []) or []
        if subs:
            s = subs[0]
            all_rows.append({
                "id": s["id"],
                "username": u["username"],
                "timestamp": s.get("timestamp"),
                "result_json": s.get("result_json"),
                "job_items": u.get("job_items", "")
            })
    all_rows = sorted(all_rows, key=lambda x: x["id"], reverse=True)
    return all_rows


def get_latest_submission_by_user(user_id):
    res = supabase.table("submissions").select("*").eq("user_id", user_id).order("id", desc=True).limit(1).execute()
    data = getattr(res, "data", []) or []
    return data[0] if data else None


def get_latest_submissions_per_user_list():
    users_res = supabase.table("users").select("*").order("username", desc=False).execute()
    users = getattr(users_res, "data", []) or []
    experts = []
    for u in users:
        sub = get_latest_submission_by_user(u["id"])
        if sub is not None:
            experts.append((u["username"], sub.get("result_json"), sub.get("main_pairs"), u.get("job_items", "")))
    return experts

# ------------------------------
# UI & Routing
# ------------------------------
if 'user' not in st.session_state:
    st.session_state['user'] = None

st.sidebar.title("Akses ")
auth_mode = st.sidebar.selectbox("Mode", ["Login", "Register", "Logout"])

if auth_mode == "Register":
    st.sidebar.subheader("Daftar Pengguna Baru")
    new_user = st.sidebar.text_input("Username (daftar)", key="reg_user")
    new_pw = st.sidebar.text_input("Password (daftar)", type="password", key="reg_pw")
    admin_check = st.sidebar.checkbox("Daftarkan sebagai admin", key="reg_admin")
    job_items_input = st.sidebar.text_input("Job Items / Keahlian (pisahkan koma jika lebih dari 1)", key="reg_job_items")
    if st.sidebar.button("Daftar", key="btn_register"):
        ok, msg = register_user(new_user, new_pw, bool(admin_check), job_items_input)
        if ok:
            st.sidebar.success(msg)
        else:
            st.sidebar.error(msg)

elif auth_mode == "Login":
    st.sidebar.subheader("Masuk")
    login_user = st.sidebar.text_input("Username", key="login_user")
    login_pw = st.sidebar.text_input("Password", type="password", key="login_pw")
    if st.sidebar.button("Masuk", key="btn_login"):
        ok, info = authenticate_user(login_user, login_pw)
        if ok:
            st.session_state['user'] = info
            st.sidebar.success(f"Selamat datang, {info['username']}")
        else:
            st.sidebar.error(info)

else:  # Logout
    if st.sidebar.button("Logout", key="btn_logout"):
        st.session_state['user'] = None
        st.sidebar.info("Anda telah logout.")

if not st.session_state['user']:
    st.title("Aplikasi Kuesioner AHP — Multi-user")
    st.write("Silakan login atau daftar melalui panel kiri (sidebar).")
    st.write("Setelah login, Anda dapat mengisi kuesioner AHP atau melihat hasil.")
    st.stop()

user = st.session_state['user']
# show job items in sidebar if present
if user.get("job_items"):
    st.sidebar.markdown(f"**Job Items / Keahlian:** {user.get('job_items','')}")
st.sidebar.markdown(f"**User:** {user['username']}  {'(admin)' if user['is_admin'] else ''}")

if user['is_admin']:
    page = st.sidebar.selectbox("Halaman", [
        "Isi Kuesioner",
        "My Submissions",
        "Hasil Akhir Penilaian",
        "Admin Panel",
        "Laporan Final Gabungan Pakar"
    ])
else:
    page = st.sidebar.selectbox("Halaman", [
        "Isi Kuesioner",
        "My Submissions",
        "Hasil Akhir Penilaian"
    ])


def _short_key(prefix, a, b):
    h = hashlib.sha1((prefix + "::" + a + "|||" + b).encode("utf-8")).hexdigest()
    return h[:12]


def pairwise_inputs(items, key_prefix):
    pairs = list(itertools.combinations(items, 2))
    out = {}
    for (a, b) in pairs:
        col_l, col_mid, col_r, col_scale = st.columns([6, 1, 6, 2])
        col_l.markdown(f"<div style='white-space:normal'>{a}</div>", unsafe_allow_html=True)
        col_r.markdown(f"<div style='white-space:normal'>{b}</div>", unsafe_allow_html=True)
        kshort = _short_key(key_prefix, a, b)
        direction = col_mid.radio("", ["L", "R"], index=0, key=f"{kshort}_dir", horizontal=True, label_visibility="collapsed")
        val = col_scale.selectbox("", list(range(1, 10)), index=1, key=f"{kshort}_scale", label_visibility="collapsed")
        if direction == "L":
            out[(a, b)] = float(val)
        else:
            out[(a, b)] = float(1.0 / val)
    return out

# Page: Isi Kuesioner
# Page: Isi Kuesioner
if page == "Isi Kuesioner":
    st.header("Isi Kuesioner AHP — Penataan Ruang Publik")
    st.write("Isi perbandingan berpasangan menggunakan skala 1–9. (1 = sama penting, 9 = mutlak lebih penting).")

    st.markdown("**1) Perbandingan Kriteria Utama**")
    main_pairs = pairwise_inputs(CRITERIA, "MAIN")

    if st.button("Simpan hasil ke database"):
        # --- AHP MAIN ---
        main_mat = build_matrix_from_pairs(CRITERIA, main_pairs)
        main_w = geometric_mean_weights(main_mat)
        main_cons = consistency_metrics(main_mat, main_w)

        # --- AHP FLAT (TANPA SUB-KRITERIA) ---
        local = {}

        global_rows = []
        for k, w in zip(CRITERIA, main_w):
            global_rows.append({
                "Kriteria": k,
                "SubKriteria": k,
                "LocalWeight": 1.0,
                "MainWeight": float(w),
                "GlobalWeight": float(w)
            })

        result = {
            "main": {
                "keys": CRITERIA,
                "weights": list(map(float, main_w)),
                "cons": main_cons,
                "mat": main_mat.tolist()
            },
            "local": {},
            "global": global_rows
        }

        main_pairs_store = {f"{a} ||| {b}": v for (a, b), v in main_pairs.items()}
        save_submission(user['id'], main_pairs_store, {}, result)

        st.success("Hasil berhasil disimpan ke database (Supabase).")
        st.rerun()

    st.markdown("---")
   
if st.button("Simpan hasil ke database"):
    # === AHP KRITERIA UTAMA (FLAT) ===
    main_mat = build_matrix_from_pairs(CRITERIA, main_pairs)
    main_w = geometric_mean_weights(main_mat)
    main_cons = consistency_metrics(main_mat, main_w)

    # === GLOBAL = BOBOT KRITERIA (karena flat) ===
    global_rows = []
    for k, w in zip(CRITERIA, main_w):
        global_rows.append({
            "Kriteria": k,
            "SubKriteria": k,
            "LocalWeight": 1.0,
            "MainWeight": float(w),
            "GlobalWeight": float(w)
        })

    result = {
        "main": {
            "keys": CRITERIA,
            "weights": list(map(float, main_w)),
            "cons": main_cons,
            "mat": main_mat.tolist()
        },
        "local": {},  # kosong karena flat
        "global": global_rows
    }

    main_pairs_store = {
        f"{a} ||| {b}": float(v)
        for (a, b), v in main_pairs.items()
    }

    save_submission(user['id'], main_pairs_store, {}, result)
    st.success("Hasil berhasil disimpan ke database (Supabase).")
    st.rerun()


        result = {
            "main": {"keys": CRITERIA, "weights": list(map(float, main_w)), "cons": main_cons, "mat": main_mat.tolist()},
            "local": local,
            "global": global_rows
        }
        ts = datetime.now().isoformat()
        main_pairs_store = {f"{a} ||| {b}": v for (a, b), v in main_pairs.items()}
        save_submission(user['id'], main_pairs_store, sub_pairs, result)
        st.success("Hasil berhasil disimpan ke database (Supabase).")
        st.rerun()

# Page: My Submissions
elif page == "My Submissions":
    st.header("Submission Saya")
    rows = get_user_submissions(user["id"])
    if not rows:
        st.info("Belum ada submission.")
    else:
        for r in rows:
            sid = r.get("id")
            ts = r.get("timestamp")
            res = r.get("result_json") if r.get("result_json") is not None else r.get("result")
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except Exception:
                    res = {}
            st.subheader(f"Submission #{sid} — {ts}")
            if user.get("job_items"):
                st.write("**Job Items / Keahlian:** " + str(user.get("job_items","")))
            dfg = pd.DataFrame(res.get('global', [])).sort_values("GlobalWeight", ascending=False).head(10)
            st.table(dfg)
            col1, col2 = st.columns(2)
            with col1:
                df_main = pd.DataFrame({"Kriteria": res['main']['keys'], "Weight": res['main']['weights']})
                df_global = pd.DataFrame(res['global']).sort_values("GlobalWeight", ascending=False)
                meta_df = pd.DataFrame([{
                    "User": user['username'],
                    "Timestamp": ts,
                    "Job Items": user.get("job_items","")
                }])
                excel_out = to_excel_bytes({
                    "Meta": meta_df,
                    "Kriteria_Utama": df_main,
                    "Global_Weights": df_global
                })
                st.download_button(f"Download Excel #{sid}", data=excel_out,
                                   file_name=f"submission_{sid}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key=f"ex_{sid}")
            with col2:
                submission_row = {
                    "id": sid,
                    "username": user["username"],
                    "timestamp": ts,
                    "result": res,
                    "job_items": user.get("job_items", "")
                }
                try:
                    pdf_bio = generate_pdf_bytes(submission_row)
                    st.download_button(f"Download PDF #{sid}", data=pdf_bio,
                                       file_name=f"submission_{sid}.pdf", mime="application/pdf", key=f"pdf_{sid}")
                except RuntimeError as e:
                    st.warning(str(e))

# Page: Hasil Akhir Penilaian (latest submission user)
elif page == "Hasil Akhir Penilaian":
    st.header("Hasil Akhir Penilaian Pakar (AHP)")
    latest = get_latest_submission_by_user(user["id"])
    if not latest:
        st.info("Anda belum mengisi kuesioner AHP.")
        st.stop()
    sid = latest.get("id")
    ts = latest.get("timestamp")
    res = latest.get("result_json") if latest.get("result_json") is not None else latest.get("result")
    if isinstance(res, str):
        try:
            res = json.loads(res)
        except Exception:
            res = {}
    if user.get("job_items"):
        st.write("**Job Items / Keahlian:** " + str(user.get("job_items","")))
    st.subheader("1. Bobot Kriteria Utama")
    df_main = pd.DataFrame({"Kriteria": res['main']['keys'], "Bobot": res['main']['weights']})
    st.table(df_main)
    st.write("**CI = {:.4f}, CR = {:.4f}**".format(res['main']['cons'].get('CI', 0), res['main']['cons'].get('CR', 0)))

    st.markdown("---")
    st.subheader("2. Bobot Sub-Kriteria (Bobot Lokal per Grup)")
    for group_name, info in res.get("local", {}).items():
        st.markdown(f"#### {group_name}")
        df_local = pd.DataFrame({"Sub-Kriteria": info.get("keys", []), "Bobot Lokal": info.get("weights", [])})
        st.table(df_local)
        st.write("**CI = {:.4f}, CR = {:.4f}**".format(info.get("cons", {}).get("CI", 0), info.get("cons", {}).get("CR", 0)))

    st.markdown("---")
    st.subheader("3. Bobot Global (Ranking Semua Sub-Kriteria)")
    df_global = pd.DataFrame(res.get("global", [])).sort_values("GlobalWeight", ascending=False)
    st.table(df_global)
    st.subheader("Grafik Bobot Global (Top 20)")
    try:
        import altair as alt
        chart = alt.Chart(df_global.head(20)).mark_bar().encode(
            x='GlobalWeight:Q',
            y=alt.Y('SubKriteria:N', sort='-x')
        ).properties(height=500)
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.info("Altair tidak tersedia, grafik dilewati.")

    st.markdown("---")
    st.subheader("4. Download Laporan")
    submission_row = {
        "id": sid,
        "username": user["username"],
        "timestamp": ts,
        "result": res,
        "job_items": user.get("job_items", "")
    }
    try:
        pdf_bio = generate_pdf_bytes(submission_row)
        st.download_button("📄 Download Laporan PDF", data=pdf_bio,
                           file_name=f"hasil_ahp_{sid}.pdf", mime="application/pdf")
    except RuntimeError as e:
        st.warning(str(e))

    excel_bio = to_excel_bytes({
        "Meta": pd.DataFrame([{"User": user['username'], "Timestamp": ts, "Job Items": user.get("job_items","")}]),
        "Kriteria_Utama": pd.DataFrame({"Kriteria": res['main']['keys'], "Bobot": res['main']['weights']}),
        "Global_Weights": pd.DataFrame(res.get("global", [])).sort_values("GlobalWeight", ascending=False)
    })
    st.download_button("📊 Download Excel Hasil", data=excel_bio,
                       file_name=f"hasil_ahp_{sid}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# Admin Panel
elif page == "Admin Panel" and user["is_admin"]:
    st.header("📊 Admin Panel – Manajemen Submission Pakar")
    all_rows = get_all_submissions_with_user()
    if not all_rows:
        st.info("Belum ada submission dari pakar.")
        st.stop()

    summary_rows = []
    for r in all_rows:
        sid = r.get("id")
        username = r.get("username")
        ts = r.get("timestamp")
        job_items = r.get("job_items", "")
        res = r.get("result_json") if r.get("result_json") is not None else r.get("result")
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except Exception:
                res = {}
        main_weights = res.get("main", {}).get("weights", [])
        cr_main = res.get("main", {}).get("cons", {}).get("CR", 0)
        summary_rows.append({
            "ID": sid,
            "User": username,
            "Job Items": job_items,
            "Timestamp": ts,
            "CR Utama": cr_main,
            "Bobot Kriteria (truncated)": ", ".join(f"{w:.3f}" for w in (main_weights[:7] if len(main_weights) >= 7 else main_weights))
        })
    df_summary = pd.DataFrame(summary_rows)
    st.dataframe(df_summary, use_container_width=True)

    st.markdown("---")
    st.subheader("🗑 Hapus Submission")
    del_id = st.number_input("Masukkan ID submission yang ingin dihapus", min_value=1, step=1)
    if st.button("Hapus Submission"):
        try:
            delete_submission(int(del_id))
            st.success(f"Submission #{del_id} telah dihapus.")
            st.rerun()
        except Exception as e:
            st.error(f"Gagal menghapus: {e}")

    st.markdown("---")
    st.subheader("📥 Download Semua Data (Excel)")
    excel_sheets = {"Ringkasan_Admin": df_summary}
    for r in all_rows:
        sid = r.get("id")
        res = r.get("result_json") if r.get("result_json") is not None else r.get("result")
        job_items = r.get("job_items", "")
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except Exception:
                res = {}
        df_main = pd.DataFrame({"Kriteria": res.get("main", {}).get("keys", []),
                                "Bobot": res.get("main", {}).get("weights", [])})
        df_global = pd.DataFrame(res.get("global", [])).sort_values("GlobalWeight", ascending=False)
        meta_df = pd.DataFrame([{"User": r.get("username"), "Job Items": job_items, "Timestamp": r.get("timestamp")}])
        excel_sheets[f"Meta_{sid}"] = meta_df
        excel_sheets[f"Main_{sid}"] = df_main
        excel_sheets[f"Global_{sid}"] = df_global

    excel_all = to_excel_bytes(excel_sheets)
    st.download_button("📊 Download Semua Data (Excel)", data=excel_all,
                       file_name="all_submissions.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # =========================
    # Tambahan: Laporan Per-Pakar
    # =========================
    st.markdown("---")
    st.subheader("📑 Laporan Per-Pakar (individual expert reports)")
    st.write("Unduh laporan PDF / Excel untuk tiap pakar. Jika reportlab belum terpasang, PDF akan dinonaktifkan.")

    # list per-pakar dengan tombol download
    pdf_bytes_list = []  # akan dipakai jika ingin zip semua
    for r in all_rows:
        sid = r.get("id")
        username = r.get("username")
        ts = r.get("timestamp")
        job_items = r.get("job_items", "")
        res = r.get("result_json") if r.get("result_json") is not None else r.get("result")
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except Exception:
                res = {}

        st.markdown(f"**#{sid} — {username}**  _{ts}_  | Job Items: {job_items}")
        cols = st.columns([1,1,1,6])
        with cols[0]:
            # Excel per pakar
            df_main = pd.DataFrame({"Kriteria": res.get("main", {}).get("keys", []),
                                    "Bobot": res.get("main", {}).get("weights", [])})
            df_global = pd.DataFrame(res.get("global", [])).sort_values("GlobalWeight", ascending=False)
            meta_df = pd.DataFrame([{"User": username, "Job Items": job_items, "Timestamp": ts}])
            excel_bio = to_excel_bytes({
                "Meta": meta_df,
                "Kriteria_Utama": df_main,
                "Global_Weights": df_global
            })
            st.download_button(f"Excel #{sid}", data=excel_bio,
                               file_name=f"laporan_pakar_{username}_{sid}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key=f"exp_ex_{sid}")

        with cols[1]:
            # PDF per pakar (jika tersedia)
            submission_row = {
                "id": sid,
                "username": username,
                "timestamp": ts,
                "result": res,
                "job_items": job_items
            }
            if canvas is not None:
                try:
                    pdf_bio = generate_pdf_bytes(submission_row)
                    # simpan bytes untuk zip agregasi
                    pdf_bytes_list.append((f"laporan_pakar_{username}_{sid}.pdf", pdf_bio.getvalue()))
                    st.download_button(f"PDF #{sid}", data=pdf_bio,
                                       file_name=f"laporan_pakar_{username}_{sid}.pdf",
                                       mime="application/pdf",
                                       key=f"exp_pdf_{sid}")
                except Exception as e:
                    st.error(f"Gagal membuat PDF untuk {username} (#{sid}): {e}")
            else:
                st.info("reportlab tidak terpasang — PDF tidak tersedia.")

        with cols[2]:
            # Tampilkan ringkasan table ringkas (top 5)
            try:
                dfg = df_global.head(5)
                st.table(dfg)
            except Exception:
                st.write("Tidak ada data global.")

    # tombol untuk mengunduh semua PDF pakar sebagai ZIP (jika ada)
    if pdf_bytes_list:
        zip_b = BytesIO()
        with zipfile.ZipFile(zip_b, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for fname, data in pdf_bytes_list:
                zf.writestr(fname, data)
        zip_b.seek(0)
        st.download_button("📦 Download Semua Laporan PDF (ZIP)", data=zip_b,
                           file_name="laporan_semua_pakar_pdf.zip", mime="application/zip")
    else:
        if canvas is None:
            st.info("PDF tidak tersedia karena 'reportlab' belum terpasang. Anda bisa mengunduh Excel masing-masing pakar.")
        else:
            st.info("Belum ada PDF yang berhasil dihasilkan untuk dikemas.")

# Laporan Final Gabungan Pakar (admin-only)
elif page == "Laporan Final Gabungan Pakar" and user["is_admin"]:
    st.header("📘 Laporan Final Gabungan Antar Pakar (AHP)")
    experts = get_latest_submissions_per_user_list()
    if not experts:
        st.warning("Belum ada pakar yang mengisi kuesioner.")
        st.stop()
    st.success(f"Ditemukan {len(experts)} pakar (menggunakan submission terbaru tiap pakar).")

    # 1) AIJ — aggregate pairwise matrices (main criteria)
    all_main_matrices = []
    expert_meta = []
    for username, rjson, main_pairs_json, job_items in experts:
        expert_meta.append({"username": username, "job_items": job_items})
        mp = {}
        try:
            mp = main_pairs_json if isinstance(main_pairs_json, dict) else json.loads(main_pairs_json)
        except Exception:
            mp = {}
        pair_values = {}
        for k, v in (mp.items() if isinstance(mp, dict) else []):
            try:
                a, b = [s.strip() for s in k.split("|||")]
                pair_values[(a, b)] = float(v)
            except Exception:
                continue
        M = build_matrix_from_pairs(CRITERIA, pair_values)
        all_main_matrices.append(M)

    GM = np.exp(np.mean([np.log(m) for m in all_main_matrices], axis=0))
    weights_aij = geometric_mean_weights(GM)
    cons_aij = consistency_metrics(GM, weights_aij)
    df_aij = pd.DataFrame({"Kriteria": CRITERIA, "Bobot_AI J": weights_aij})
    st.subheader("1) Bobot Gabungan Kriteria Utama (AIJ)")
    st.table(df_aij)
    st.write(f"CI = {cons_aij['CI']:.4f}, CR = {cons_aij['CR']:.4f}")

    # 2) AIP — aggregate individual priorities
    all_w = []
    for username, rjson, _, _ in experts:
        try:
            res = rjson if isinstance(rjson, dict) else json.loads(rjson)
        except Exception:
            res = {}
        all_w.append(np.array(res.get("main", {}).get("weights", [])))
    all_w = np.vstack(all_w)
    w_aip = np.exp(np.mean(np.log(all_w), axis=0))
    w_aip = w_aip / w_aip.sum()
    df_aip = pd.DataFrame({"Kriteria": CRITERIA, "Bobot_AIP": w_aip})
    st.subheader("2) Bobot Gabungan Kriteria Utama (AIP)")
    st.table(df_aip)

   df_global = pd.DataFrame({
    "Kriteria": CRITERIA,
    "SubKriteria": CRITERIA,
    "GlobalWeight": weights_aij
})


    try:
        import altair as alt
        chart = alt.Chart(df_global.head(20)).mark_bar().encode(
            x='GlobalWeight:Q',
            y=alt.Y('SubKriteria:N', sort='-x')
        ).properties(height=500)
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.info("Altair tidak tersedia, grafik dilewati.")

    # include expert_meta in excel
    excel_bio = to_excel_bytes({
        "AIJ_Kriteria": df_aij,
        "AIP_Kriteria": df_aip,
        "Global_Combined": df_global,
        "Experts": pd.DataFrame(expert_meta)
    })
    st.download_button("📥 Download Excel Gabungan", data=excel_bio,
                       file_name="AHP_Gabungan_Pakar.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # normalize job_items
    def normalize_job_items(value):
        if isinstance(value, list):
            return ", ".join([str(v) for v in value])
        return str(value or "")

    all_job_items = ", ".join(
        normalize_job_items(m.get("job_items", ""))
        for m in expert_meta
    )

    payload = {
        "username": "GABUNGAN PAKAR",
        "timestamp": datetime.now().isoformat(),
        "result": {
            "main": {"keys": CRITERIA, "weights": list(map(float, weights_aij)), "cons": cons_aij},
            "global": df_global.to_dict(orient="records")
        },
        "job_items": all_job_items
    }

    try:
        pdf_bio = generate_pdf_bytes(payload)
        st.download_button("📄 Download PDF Gabungan", data=pdf_bio,
                           file_name="AHP_Gabungan_Pakar.pdf", mime="application/pdf")
    except RuntimeError as e:
        st.warning(str(e))

# EOF









