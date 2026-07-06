import os
import uuid
import tempfile
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
from dotenv import load_dotenv

from utils import extract_and_analyze_homework, generate_audio, generate_vocab_audio

load_dotenv()

# --- Firebase Init (NO STORAGE) ---
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-credentials.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- Config ---
FREE_LIMIT = int(os.getenv("FREE_TIER_LIMIT", 3))
STRIPE_MONTHLY = os.getenv("STRIPE_MONTHLY_LINK")
STRIPE_FAMILY = os.getenv("STRIPE_FAMILY_LINK")

# --- Page Config ---
st.set_page_config(
    page_title="French Homework Helper | The Study Zone",
    page_icon="🇫🇷",
    layout="wide"
)

# --- Session State ---
if "user" not in st.session_state:
    st.session_state.user = None

# ============ AUTH FUNCTIONS ============
def sign_up(email, password):
    try:
        user = auth.create_user(email=email, password=password)
        return user
    except Exception as e:
        st.error(f"Sign up failed: {e}")
        return None

def sign_in(email, password):
    try:
        user_record = auth.get_user_by_email(email)
        return user_record
    except Exception:
        return None

# ============ UI ============
st.title("🇫🇷 French Homework Helper")
st.caption("By The Study Zone — Built by an Ontario teacher, for Ontario parents.")

# --- Auth Gate ---
if not st.session_state.user:
    tab1, tab2 = st.tabs(["Sign Up", "Sign In"])
    
    with tab1:
        with st.form("signup_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            grade = st.selectbox("Child's Grade", range(1, 9))
            submitted = st.form_submit_button("Create Account")
            if submitted and email and password:
                user = sign_up(email, password)
                if user:
                    db.collection("users").document(user.uid).set({
                        "email": email,
                        "grade": grade,
                        "usage_count": 0,
                        "subscription": "free"
                    })
                    st.session_state.user = {"uid": user.uid, "email": email, "grade": grade}
                    st.rerun()
    
    with tab2:
        with st.form("signin_form"):
            email = st.text_input("Email", key="signin_email")
            password = st.text_input("Password", type="password", key="signin_pw")
            submitted = st.form_submit_button("Sign In")
            if submitted and email:
                user = sign_in(email, password)
                if user:
                    user_doc = db.collection("users").document(user.uid).get().to_dict()
                    st.session_state.user = {"uid": user.uid, "email": email, **user_doc}
                    st.rerun()
                else:
                    st.error("User not found. Please sign up first.")
    st.stop()

# --- Main App (after auth) ---
user = st.session_state.user
st.success(f"Welcome! Child's grade: {user.get('grade', '?')}")

# --- Usage Check ---
user_ref = db.collection("users").document(user["uid"])
user_doc = user_ref.get().to_dict()
usage = user_doc.get("usage_count", 0)
subscription = user_doc.get("subscription", "free")

if subscription == "free" and usage >= FREE_LIMIT:
    st.warning(f"You've used your {FREE_LIMIT} free homework helps.")
    st.markdown("### 🔓 Unlock Unlimited Help")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Monthly — $15/mo**\nUnlimited helps + audio")
        st.markdown(f"[Subscribe Now]({STRIPE_MONTHLY})")
    with col2:
        st.markdown(f"**Family — $25/mo**\nUp to 3 kids")
        st.markdown(f"[Subscribe Now]({STRIPE_FAMILY})")
    st.info("After payment, email receipt to hello@thestudyzone.ca to activate.")
    st.stop()

# --- Main Form ---
st.markdown("### 📄 Upload Homework")
uploaded = st.file_uploader(
    "Choose an image or PDF",
    type=["jpg", "jpeg", "png", "pdf"],
    help="You can upload a photo (JPG, PNG) or a PDF file"
)

if uploaded:
    file_type = uploaded.type
    if file_type == "application/pdf":
        st.info("📄 PDF file detected")
    else:
        st.info("📸 Image file detected")

analyze_btn = st.button(" Analyze Homework", type="primary", disabled=not uploaded)

if analyze_btn and uploaded:
    with st.spinner("Madame AI is analyzing the homework..."):
        file_bytes = uploaded.read()
        file_type = uploaded.type
        
        # Gemini handles EVERYTHING in one step
        try:
            ai_response = extract_and_analyze_homework(file_bytes, file_type, user.get("grade", 4))
        except Exception as e:
            st.error(f"❌ Analysis failed: {str(e)}")
            st.stop()
        
        # Check if Gemini couldn't read it
        if ai_response.get("translation", "").lower() in ["no text detected", "no homework detected", ""]:
            st.error("❌ Could not read the homework. Try a clearer file or type it manually.")
            st.stop()
        
        # Show what Gemini extracted (for verification)
        st.text_area("What the AI read:", ai_response.get("translation", ""), height=100)
    
    with st.spinner("Generating audio pronunciations..."):
        # Generate audio for vocabulary
        audio_dir = tempfile.mkdtemp()
        vocab_audio = []
        if ai_response.get("vocabulary"):
            vocab_audio = generate_vocab_audio(ai_response["vocabulary"], audio_dir)
        
        # Save session to Firestore
        session_data = {
            "user_id": user["uid"],
            "file_type": file_type,
            "ai_response": ai_response,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        db.collection("homework_sessions").add(session_data)
        
        # Increment usage
        user_ref.update({"usage_count": firestore.Increment(1)})
    
    # ============ DISPLAY RESULTS ============
    st.markdown("---")
    st.markdown("## 📖 Translation")
    st.info(ai_response.get("translation", "N/A"))
    
    st.markdown(f"## 🧠 Concept: **{ai_response.get('concept', 'N/A')}**")
    st.write(ai_response.get("concept_explained", ""))
    
    st.markdown("## 👨‍👩‍👧 How to Guide Your Child")
    for i, step in enumerate(ai_response.get("parent_coach_steps", []), 1):
        st.markdown(f"**{i}.** {step}")
    
    if ai_response.get("vocabulary"):
        st.markdown("## 📚 Vocabulary")
        for i, word in enumerate(ai_response["vocabulary"]):
            col1, col2, col3 = st.columns([2, 2, 1])
            col1.write(f"**{word.get('french', '')}**")
            col2.write(word.get("english", ""))
            
            audio_match = next((a for a in vocab_audio if a["index"] == i), None)
            if audio_match:
                col3.audio(audio_match["audio_path"])
            else:
                col3.write(word.get("pronunciation_tip", ""))
    
    with st.expander("⚠️ Common Mistakes"):
        for mistake in ai_response.get("common_mistakes", []):
            st.markdown(f"- {mistake}")
    
    st.markdown(f"**Ontario Curriculum Link:** {ai_response.get('ontario_curriculum_link', '')}")
    st.success(ai_response.get("encouragement", "You've got this!"))
    
    # --- Upsell CTA ---
    st.markdown("---")
    st.markdown("### 🎯 Still struggling?")
    st.markdown("Book a **free 30-minute assessment** at The Study Zone in Brampton.")
    st.markdown("[📅 Book Assessment](https://calendly.com/your-study-zone)")

# --- Sidebar ---
with st.sidebar:
    st.markdown("### 🇫🇷 French Homework Helper")
    st.markdown(f"**{user.get('email', '')}**")
    st.markdown(f"Subscription: **{subscription}**")
    st.markdown(f"Usage: **{usage}/{FREE_LIMIT if subscription == 'free' else '∞'}**")
    st.markdown("---")
    st.markdown("By The Study Zone")
    if st.button("Sign Out"):
        st.session_state.user = None
        st.rerun()