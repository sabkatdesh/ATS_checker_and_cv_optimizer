# streamlit_app.py
# ============================================================
# CV Optimizer — Streamlit Frontend
# Fixes: logo, no dimming, fields clear after add, projects
# ============================================================

import streamlit as st
import requests
import time
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# SETUP
# ============================================================

API_URL = os.environ.get("API_URL", "http://localhost:8000")
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_ANON_KEY = os.environ["SUPABASE_ANON_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

st.set_page_config(
    page_title="CV Optimizer",
    page_icon="📄",
    layout="centered"
)

# ============================================================
# LOGO HELPER — shown on every page
# ============================================================

def show_logo():
    """
    Shows logo at top of every page.
    Put your logo image file named 'logo.png' in the same
    folder as streamlit_app.py.
    If no logo file found, shows text logo instead.
    """
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png")
    if os.path.exists(logo_path):
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.image(logo_path, width=200)
    else:
        # Text fallback if no logo image yet
        st.markdown(
            "<h2 style='text-align:center; color:#4F8BF9;'>📄 CV Optimizer</h2>",
            unsafe_allow_html=True
        )
    st.divider()


# ============================================================
# HELPERS
# ============================================================

def get_headers():
    token = st.session_state.get("token", "")
    return {"Authorization": f"Bearer {token}"}


def api_get(endpoint):
    try:
        res = requests.get(f"{API_URL}{endpoint}", headers=get_headers(), timeout=30)
        return res.json(), res.status_code
    except Exception as e:
        return {"error": str(e)}, 500


def api_post(endpoint, data):
    try:
        res = requests.post(f"{API_URL}{endpoint}", json=data, headers=get_headers(), timeout=30)
        return res.json(), res.status_code
    except Exception as e:
        return {"error": str(e)}, 500


def logout():
    supabase.auth.sign_out()
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


# ============================================================
# PAGE: LOGIN / SIGNUP
# ============================================================

def page_login():
    show_logo()
    st.write("Optimize your CV for any job in minutes.")
    st.divider()

    tab1, tab2 = st.tabs(["Login", "Sign Up"])

    with tab1:
        st.subheader("Welcome back")
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_pass")

        if st.button("Login", use_container_width=True, type="primary"):
            if not email or not password:
                st.error("Please enter email and password")
            else:
                try:
                    res = supabase.auth.sign_in_with_password({
                        "email": email,
                        "password": password
                    })
                    st.session_state.user = res.user
                    st.session_state.token = res.session.access_token
                    st.rerun()
                except Exception:
                    st.error("Invalid email or password. Please try again.")

    with tab2:
        st.subheader("Create your account")
        new_email = st.text_input("Email", key="signup_email")
        new_password = st.text_input("Password (min 6 characters)", type="password", key="signup_pass")
        new_password2 = st.text_input("Confirm Password", type="password", key="signup_pass2")

        if st.button("Sign Up", use_container_width=True):
            if not new_email or not new_password:
                st.error("Please fill all fields")
            elif new_password != new_password2:
                st.error("Passwords do not match")
            elif len(new_password) < 6:
                st.error("Password must be at least 6 characters")
            else:
                try:
                    supabase.auth.sign_up({
                        "email": new_email,
                        "password": new_password
                    })
                    st.success("Account created! Please check your email to confirm, then log in.")
                except Exception:
                    st.error("Could not create account. Email may already be registered.")


# ============================================================
# PAGE: HOME
# ============================================================

def page_home():
    show_logo()
    st.title("🚀 Generate Your Optimized CV")

    balance_data, _ = api_get("/billing/balance")
    balance = balance_data.get("balance", 0)
    cost = balance_data.get("cost_per_cv", 10)

    col1, col2 = st.columns(2)
    col1.metric("Your Coins", balance)
    col2.metric("Cost Per CV", cost)

    st.divider()

    if "current_thread" in st.session_state:
        _show_generation_progress()
        return

    if "last_result" in st.session_state:
        _show_results()
        return

    st.subheader("Paste Job Description")
    jd = st.text_area(
        "Copy and paste the full job description here",
        height=300,
        placeholder="We are looking for a Senior Python Developer...",
        key="jd_input"
    )

    if st.button("✨ Generate Optimized CV", use_container_width=True, type="primary"):
        if not jd or len(jd.strip()) < 50:
            st.error("Please paste a complete job description")
        elif balance < cost:
            st.error(f"Not enough coins. You need {cost} coins but have {balance}.")
            st.info("Redirecting to Billing page...")
            time.sleep(2)
            st.session_state.nav = "💰 Billing"
            st.rerun()
        else:
            data, status = api_post("/sessions/start", {"job_description": jd})
            if status == 200:
                st.session_state.current_thread = data["thread_id"]
                st.rerun()
            elif status == 400 and "profile" in data.get("detail", "").lower():
                st.error("Please complete your profile first.")
                st.session_state.nav = "👤 Profile"
                time.sleep(2)
                st.rerun()
            else:
                st.error(data.get("detail", "Something went wrong. Please try again."))


def _show_generation_progress():
    """
    FIX: Dimming issue was caused by st.spinner() wrapping time.sleep()
    inside a rerun loop. Removed spinner — just show status text instead.
    st.spinner dims the entire page which confused users.
    """
    thread_id = st.session_state.current_thread
    status_data, _ = api_get(f"/sessions/{thread_id}/status")
    status = status_data.get("status", "running")

    if status == "running":
        # FIX: No st.spinner here — it was causing the dimming
        st.info("⏳ Analyzing your CV against the job description. Please wait...")
        st.write("This usually takes 1-2 minutes. Page will update automatically.")
        # Simple progress bar animation instead of dimming spinner
        progress = st.progress(0)
        for i in range(100):
            time.sleep(0.03)
            progress.progress(i + 1)
        st.rerun()

    elif status == "awaiting_hitl":
        st.warning("🤔 We found some gaps. Please answer these questions:")
        gaps = status_data.get("gaps", [])
        answers = []
        for i, gap in enumerate(gaps):
            ans = st.text_input(f"Q{i+1}: {gap}", key=f"gap_{i}")
            answers.append(f"Q{i+1}: {gap}\nA{i+1}: {ans}")

        if st.button("Submit Answers & Continue", type="primary"):
            qna = "\n\n".join(answers)
            reply_data, reply_status = api_post(
                f"/sessions/{thread_id}/reply",
                {"user_qna": qna}
            )
            if reply_status == 200:
                st.rerun()
            else:
                st.error("Something went wrong submitting answers.")

    elif status == "complete":
        st.session_state.last_result = status_data
        del st.session_state.current_thread
        st.rerun()

    elif status == "ineligible":
        st.error("❌ Your profile does not match this job well enough to generate a CV.")
        score = status_data.get("eligibility_score", 0)
        st.write(f"Match score: {score}/100")
        st.write("Try a different job description that better matches your experience.")
        if st.button("Try Another Job"):
            del st.session_state.current_thread
            st.rerun()

    elif status == "error":
        st.error("Something went wrong during generation. Please try again.")
        if st.button("Try Again"):
            del st.session_state.current_thread
            st.rerun()

    else:
        st.info(f"Status: {status}. Please wait...")
        time.sleep(3)
        st.rerun()


def _show_results():
    result = st.session_state.last_result
    st.success("✅ Your optimized CV is ready!")
    st.divider()

    st.subheader("📊 ATS Score Comparison")
    eligibility_score = result.get("eligibility_score", 0)
    ats_score = result.get("ats_score", 0)

    col1, col2, col3 = st.columns(3)
    col1.metric("Initial Match Score", f"{eligibility_score}/100",
                help="How well your profile matched before optimization")
    col2.metric("Optimized ATS Score", f"{ats_score}%",
                delta=f"+{round(ats_score - eligibility_score, 1)}%")
    col3.metric("Improvement", f"{round(ats_score - eligibility_score, 1)}%")

    st.divider()

    pdf_url = result.get("pdf_url")
    if pdf_url:
        st.subheader("📥 Download Your CV")
        st.link_button("⬇️ Download Optimized CV (PDF)", pdf_url,
                       use_container_width=True, type="primary")
    else:
        st.warning("PDF generation had an issue. Please contact support.")

    st.divider()

    if st.button("🔄 Generate Another CV", use_container_width=True):
        del st.session_state.last_result
        if "jd_input" in st.session_state:
            del st.session_state.jd_input
        st.rerun()


# ============================================================
# PAGE: PROFILE
# ============================================================

def page_profile():
    show_logo()
    st.title("👤 My Profile")
    st.write("Fill in your CV information once. We'll use it every time you generate.")
    st.divider()

    # ── Load profile from API once per session ────────────────
    if "profile_loaded" not in st.session_state:
        profile_data, status = api_get("/profile")
        profile = profile_data.get("profile") or {} if status == 200 else {}
        skills = profile.get("skills") or {}

        st.session_state.p_experience    = profile.get("experience") or []
        st.session_state.p_education     = profile.get("education") or []
        st.session_state.p_certifications= profile.get("certifications") or []
        st.session_state.p_projects      = profile.get("projects") or []

        st.session_state.p_full_name  = profile.get("full_name", "")
        st.session_state.p_email      = profile.get("email", "")
        st.session_state.p_phone      = profile.get("phone", "")
        st.session_state.p_location   = profile.get("location", "")
        st.session_state.p_linkedin   = profile.get("linkedin", "")
        st.session_state.p_github     = profile.get("github", "")
        st.session_state.p_portfolio  = profile.get("portfolio", "")
        st.session_state.p_summary    = profile.get("summary", "")
        st.session_state.p_hard_skills= ", ".join(skills.get("hard_skills", []))
        st.session_state.p_tools      = ", ".join(skills.get("tools", []))
        st.session_state.p_frameworks = ", ".join(skills.get("frameworks", []))
        st.session_state.p_cloud      = ", ".join(skills.get("cloud_platforms", []))
        st.session_state.p_soft_skills= ", ".join(skills.get("soft_skills", []))

        # Counters for unique keys — incrementing clears the form fields
        st.session_state.exp_counter  = 0
        st.session_state.edu_counter  = 0
        st.session_state.cert_counter = 0
        st.session_state.proj_counter = 0

        st.session_state.profile_loaded = True

    # ── Personal Info ─────────────────────────────────────────
    st.subheader("Personal Information")
    col1, col2 = st.columns(2)
    full_name = col1.text_input("Full Name", value=st.session_state.p_full_name, key="pi_full_name")
    email     = col2.text_input("Email", value=st.session_state.p_email, key="pi_email")
    phone     = col1.text_input("Phone", value=st.session_state.p_phone, key="pi_phone")
    location  = col2.text_input("Location", value=st.session_state.p_location, key="pi_location")
    linkedin  = col1.text_input("LinkedIn URL", value=st.session_state.p_linkedin, key="pi_linkedin")
    github    = col2.text_input("GitHub URL", value=st.session_state.p_github, key="pi_github")
    portfolio = st.text_input("Portfolio URL", value=st.session_state.p_portfolio, key="pi_portfolio")

    st.divider()

    # ── Summary ───────────────────────────────────────────────
    st.subheader("Professional Summary")
    summary = st.text_area("Write 2-4 sentences about yourself",
                           value=st.session_state.p_summary,
                           height=120, key="pi_summary")

    st.divider()

    # ── Skills ───────────────────────────────────────────────
    st.subheader("Skills")
    hard_skills_text = st.text_input("Hard Skills (comma separated)",
                                     value=st.session_state.p_hard_skills, key="pi_hard")
    tools_text       = st.text_input("Tools (comma separated)",
                                     value=st.session_state.p_tools, key="pi_tools")
    frameworks_text  = st.text_input("Frameworks (comma separated)",
                                     value=st.session_state.p_frameworks, key="pi_fw")
    cloud_text       = st.text_input("Cloud Platforms (comma separated)",
                                     value=st.session_state.p_cloud, key="pi_cloud")
    soft_skills_text = st.text_input("Soft Skills (comma separated)",
                                     value=st.session_state.p_soft_skills, key="pi_soft")

    st.divider()

    # ── Work Experience ───────────────────────────────────────
    st.subheader("Work Experience")

    with st.expander("➕ Add Work Experience"):
        c = st.session_state.exp_counter
        job_title = st.text_input("Job Title", key=f"exp_title_{c}")
        company   = st.text_input("Company Name", key=f"exp_company_{c}")
        start_date= st.text_input("Start Date (e.g. Jan 2022)", key=f"exp_start_{c}")
        end_date  = st.text_input("End Date (e.g. Dec 2023 or Present)", key=f"exp_end_{c}")
        responsibilities = st.text_area("Responsibilities (one per line)",
                                        key=f"exp_resp_{c}", height=100)
        achievements = st.text_area("Achievements (one per line)",
                                    key=f"exp_ach_{c}", height=80)

        if st.button("✅ Add This Experience"):
            if job_title and company:
                st.session_state.p_experience.append({
                    "job_title": job_title,
                    "company": company,
                    "start_date": start_date,
                    "end_date": end_date,
                    "responsibilities": [r.strip() for r in responsibilities.split("\n") if r.strip()],
                    "achievements": [a.strip() for a in achievements.split("\n") if a.strip()],
                })
                st.session_state.exp_counter += 1  # increments key → clears fields
                st.success(f"✅ Added: {job_title} at {company}")
                st.rerun()
            else:
                st.error("Job title and company are required")

    if st.session_state.p_experience:
        st.write(f"**{len(st.session_state.p_experience)} experience entry/entries:**")
        for i, exp in enumerate(st.session_state.p_experience):
            with st.expander(f"🏢 {exp.get('job_title', '')} at {exp.get('company', '')}"):
                st.write(f"**Period:** {exp.get('start_date', '')} — {exp.get('end_date', 'Present')}")
                if exp.get("responsibilities"):
                    st.write("**Responsibilities:**")
                    for r in exp["responsibilities"]:
                        st.write(f"- {r}")
                if exp.get("achievements"):
                    st.write("**Achievements:**")
                    for a in exp["achievements"]:
                        st.write(f"+ {a}")
                if st.button("🗑️ Remove", key=f"remove_exp_{i}"):
                    st.session_state.p_experience.pop(i)
                    st.rerun()

    st.divider()

    # ── Education ─────────────────────────────────────────────
    st.subheader("Education")

    with st.expander("➕ Add Education"):
        c = st.session_state.edu_counter
        degree      = st.text_input("Degree (e.g. BSc)", key=f"edu_degree_{c}")
        field       = st.text_input("Field of Study (e.g. Computer Science)", key=f"edu_field_{c}")
        institution = st.text_input("Institution Name", key=f"edu_inst_{c}")
        grad_year   = st.text_input("Graduation Year", key=f"edu_grad_{c}")

        if st.button("✅ Add Education"):
            if degree and institution:
                st.session_state.p_education.append({
                    "degree": degree,
                    "field": field,
                    "institution": institution,
                    "graduation_year": grad_year,
                })
                st.session_state.edu_counter += 1
                st.success(f"✅ Added: {degree} from {institution}")
                st.rerun()
            else:
                st.error("Degree and institution are required")

    if st.session_state.p_education:
        st.write(f"**{len(st.session_state.p_education)} education entry/entries:**")
        for i, edu in enumerate(st.session_state.p_education):
            with st.expander(f"🎓 {edu.get('degree')} — {edu.get('institution')}"):
                st.write(f"Field: {edu.get('field', '')}")
                st.write(f"Graduated: {edu.get('graduation_year', '')}")
                if st.button("🗑️ Remove", key=f"remove_edu_{i}"):
                    st.session_state.p_education.pop(i)
                    st.rerun()

    st.divider()

    # ── Certifications ────────────────────────────────────────
    st.subheader("Certifications")

    with st.expander("➕ Add Certification"):
        c = st.session_state.cert_counter
        cert_name   = st.text_input("Certification Name", key=f"cert_name_{c}")
        cert_issuer = st.text_input("Issuer (e.g. AWS, Google)", key=f"cert_issuer_{c}")
        cert_year   = st.text_input("Year", key=f"cert_year_{c}")

        if st.button("✅ Add Certification"):
            if cert_name:
                st.session_state.p_certifications.append({
                    "name": cert_name,
                    "issuer": cert_issuer,
                    "year": cert_year,
                })
                st.session_state.cert_counter += 1
                st.success(f"✅ Added: {cert_name}")
                st.rerun()
            else:
                st.error("Certification name is required")

    if st.session_state.p_certifications:
        st.write(f"**{len(st.session_state.p_certifications)} certification(s):**")
        for i, cert in enumerate(st.session_state.p_certifications):
            with st.expander(f"📜 {cert.get('name')}"):
                st.write(f"Issuer: {cert.get('issuer', '')}")
                st.write(f"Year: {cert.get('year', '')}")
                if st.button("🗑️ Remove", key=f"remove_cert_{i}"):
                    st.session_state.p_certifications.pop(i)
                    st.rerun()

    st.divider()

    # ── Projects ──────────────────────────────────────────────
    st.subheader("Projects")
    st.caption("Add your personal or professional projects — this helps the AI optimize your CV better.")

    with st.expander("➕ Add Project"):
        c = st.session_state.proj_counter
        proj_title = st.text_input("Project Title", key=f"proj_title_{c}")
        proj_desc  = st.text_area("Description (what it does, what you built)",
                                   key=f"proj_desc_{c}", height=100)
        proj_tech  = st.text_input("Technologies Used (comma separated, e.g. Python, FastAPI, Docker)",
                                    key=f"proj_tech_{c}")

        if st.button("✅ Add Project"):
            if proj_title:
                st.session_state.p_projects.append({
                    "title": proj_title,
                    "description": proj_desc,
                    "technologies": [t.strip() for t in proj_tech.split(",") if t.strip()],
                })
                st.session_state.proj_counter += 1
                st.success(f"✅ Added: {proj_title}")
                st.rerun()
            else:
                st.error("Project title is required")

    if st.session_state.p_projects:
        st.write(f"**{len(st.session_state.p_projects)} project(s):**")
        for i, proj in enumerate(st.session_state.p_projects):
            with st.expander(f"💻 {proj.get('title')}"):
                st.write(proj.get("description", ""))
                techs = proj.get("technologies", [])
                if techs:
                    st.write(f"**Tech:** {', '.join(techs)}")
                if st.button("🗑️ Remove", key=f"remove_proj_{i}"):
                    st.session_state.p_projects.pop(i)
                    st.rerun()

    st.divider()

    # ── Save Button ───────────────────────────────────────────
    if st.button("💾 Save Profile", use_container_width=True, type="primary"):

        def parse_csv(text):
            return [s.strip() for s in text.split(",") if s.strip()]

        profile_payload = {
            "full_name"    : full_name,
            "email"        : email,
            "phone"        : phone,
            "location"     : location,
            "linkedin"     : linkedin,
            "github"       : github,
            "portfolio"    : portfolio,
            "summary"      : summary,
            "skills": {
                "hard_skills"    : parse_csv(hard_skills_text),
                "tools"          : parse_csv(tools_text),
                "frameworks"     : parse_csv(frameworks_text),
                "cloud_platforms": parse_csv(cloud_text),
                "soft_skills"    : parse_csv(soft_skills_text),
            },
            "experience"    : st.session_state.p_experience,
            "education"     : st.session_state.p_education,
            "certifications": st.session_state.p_certifications,
            "projects"      : st.session_state.p_projects,
        }

        data, status = api_post("/profile", profile_payload)
        if status == 200:
            st.success("✅ Profile saved successfully!")
        else:
            st.error(f"Failed to save. Error: {data.get('detail', 'Check that api.py is running on port 8000')}")


# ============================================================
# PAGE: PAST CVs
# ============================================================

def page_past_cvs():
    show_logo()
    st.title("📁 My Past CVs")
    st.divider()

    data, status = api_get("/sessions")

    if status != 200:
        st.error("Could not load your CVs. Make sure api.py is running.")
        return

    sessions = data.get("sessions", [])

    if not sessions:
        st.info("You haven't generated any CVs yet. Go to Home to get started!")
        return

    for session in sessions:
        status_val = session.get("status", "")
        ats        = session.get("ats_score")
        date       = session.get("created_at", "")[:10]
        pdf_url    = session.get("pdf_url")

        if status_val == "complete":      badge = "✅"
        elif status_val == "running":     badge = "⏳"
        elif status_val == "awaiting_hitl": badge = "🤔"
        elif status_val == "ineligible":  badge = "❌"
        else:                             badge = "⚠️"

        with st.container(border=True):
            col1, col2, col3 = st.columns([2, 1, 1])
            col1.write(f"{badge} **{date}**")
            col2.write(f"ATS: **{ats}%**" if ats else "ATS: —")

            if pdf_url and status_val == "complete":
                col3.link_button("⬇️ Download", pdf_url)
            elif status_val == "running":
                col3.write("In progress...")
            elif status_val == "ineligible":
                col3.write("Not eligible")


# ============================================================
# PAGE: BILLING
# ============================================================

def page_billing():
    show_logo()
    st.title("💰 Billing & Coins")
    st.divider()

    balance_data, _ = api_get("/billing/balance")
    balance = balance_data.get("balance", 0)
    cost    = balance_data.get("cost_per_cv", 10)

    col1, col2 = st.columns(2)
    col1.metric("Current Balance", f"{balance} coins")
    col2.metric("Cost Per CV", f"{cost} coins")

    st.divider()

    st.subheader("Buy Coins")
    st.info("💳 bKash and Nagad payments coming soon. For now, contact us to top up.")

    col1, col2, col3 = st.columns(3)
    with col1:
        with st.container(border=True):
            st.write("**Starter**")
            st.write("50 coins")
            st.write("~5 CVs")
            st.write("৳ 99")
            st.button("Buy", key="buy_50", disabled=True)
    with col2:
        with st.container(border=True):
            st.write("**Popular ⭐**")
            st.write("150 coins")
            st.write("~15 CVs")
            st.write("৳ 249")
            st.button("Buy", key="buy_150", disabled=True)
    with col3:
        with st.container(border=True):
            st.write("**Pro**")
            st.write("500 coins")
            st.write("~50 CVs")
            st.write("৳ 699")
            st.button("Buy", key="buy_500", disabled=True)

    st.caption("Payments via bKash and Nagad coming soon.")
    st.divider()

    st.subheader("Transaction History")
    history_data, _ = api_get("/billing/history")
    transactions = history_data.get("transactions", [])

    if not transactions:
        st.info("No transactions yet.")
    else:
        for t in transactions:
            amount = t.get("amount", 0)
            desc   = t.get("description", "")
            date   = t.get("created_at", "")[:10]
            col1, col2, col3 = st.columns([2, 1, 1])
            col1.write(desc)
            col2.write(date)
            col3.write(f"🟢 +{amount}" if amount > 0 else f"🔴 {amount}")


# ============================================================
# MAIN APP
# ============================================================

def main():
    if "user" not in st.session_state:
        page_login()
        return

    with st.sidebar:
        # Logo in sidebar too
        st.markdown("### 📄 CV Optimizer")
        st.write(f"👋 {st.session_state.user.email}")
        st.divider()

        page = st.radio(
            "Navigation",
            ["🏠 Home", "👤 Profile", "📁 Past CVs", "💰 Billing"],
            key="nav"
        )

        st.divider()
        if st.button("Logout", use_container_width=True):
            logout()

    if page == "🏠 Home":
        page_home()
    elif page == "👤 Profile":
        page_profile()
    elif page == "📁 Past CVs":
        page_past_cvs()
    elif page == "💰 Billing":
        page_billing()


if __name__ == "__main__":
    main()