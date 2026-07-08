import os
import uuid
import tempfile
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta

from utils import (extract_and_analyze_homework, generate_audio, generate_vocab_audio, 
                   chat_with_tutor, generate_quiz, generate_reading_comprehension)
from auth_api import send_verification_email, send_password_reset_email

load_dotenv()

if not firebase_admin._apps:
    # Try Streamlit secrets first, then environment variables, then local file
    firebase_creds = None
    
    # Method 1: Streamlit Cloud secrets
    try:
        firebase_creds = st.secrets["GOOGLE_APPLICATION_CREDENTIALS"]
    except (KeyError, FileNotFoundError):
        pass
    
    # Method 2: Environment variable
    if not firebase_creds:
        firebase_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    # Initialize Firebase
    if firebase_creds:
        # If it's a JSON string, parse it
        if isinstance(firebase_creds, str):
            cred_dict = json.loads(firebase_creds)
            cred = credentials.Certificate(cred_dict)
        else:
            # If it's already a dict (from st.secrets TOML)
            cred = credentials.Certificate(firebase_creds)
    else:
        # Fallback to local file (for local development)
        cred = credentials.Certificate("firebase-credentials.json")
    
    firebase_admin.initialize_app(cred)

db = firestore.client()
FREE_LIMIT = int(os.getenv("FREE_TIER_LIMIT", 3))

# ============ SEO & META TAGS (Hidden from UI, visible to search engines) ============
st.set_page_config(
    page_title="French Tutor | French Immersion Help Brampton Mississauga GTA | The Study Zone",
    page_icon="🇫🇷",
    layout="wide",
    menu_items={
        'Get Help': 'https://thestudyzone.ca',
        'Report a bug': 'mailto:hello@thestudyzone.ca',
        'About': "# French Tutor for French Immersion Students in Brampton, Mississauga, and GTA"
    }
)

# Hidden SEO content for search engines
st.markdown("""
<div style="display:none;">
<h1>French Tutor for French Immersion Students</h1>
<p>AI-powered French homework helper and tutor for students in Brampton, Mississauga, Oakville, Burlington, Milton, Caledon, Vaughan, Markham, and Greater Toronto Area (GTA).</p>
<p>Serving postal codes: L6P, L6R, L6S, L6T, L6V, L6W, L6X, L6Y, L6Z, L7A, L7B, L7C, L6G, L6H, L6J, L6K, L6L, L6M, L6N, L9P, L9S, L9T, L9V, L9W, L9X, L7M, L7N, L7P, L7S, L7T, L7K, L7J, L7H, L7G, L7E, L7R, L7L, L4S, L4E, L4C, L4B, L4G, L4H, L4J, L4K, L4L, L4M, L4N, L4P, L4R, L4T, L4V, L4W, L4X, L4Y, L4Z, L3G, L3J, L3K, L3L, L3M, L3N, L3P, L3R, L3S, L3T, L3V, L3W, L3X, L3Y, L3Z, L0P, L0N, L0J, L0G, L0B, L0A, L0C, L0E, L0H, L0K, L0L, L0M, L1B, L1C, L1E, L1G, L1H, L1J, L1K, L1L, L1M, L1N, L1P, L1R, L1S, L1T, L1V, L1W, L1X, L1Y, L1Z</p>
<p>Expert Ontario French Immersion tutor, homework help, reading comprehension, conversation practice, daily quizzes, progress tracking, IEP support, differentiated instruction, curriculum-aligned learning, Grade 1-8 French Immersion, Core French, Extended French.</p>
<p>Keywords: French tutor Brampton, French Immersion help Mississauga, French homework helper GTA, AI French tutor Ontario, French reading comprehension, French conversation practice, French quiz generator, French Immersion support Peel Region, French tutor near me, online French tutor Canada, French Immersion parent help, French pronunciation guide, French vocabulary builder, French grammar help, French Immersion resources, French tutor Oakville, French tutor Burlington, French tutor Milton, French tutor Caledon, French tutor Vaughan, French tutor Markham.</p>
</div>
""", unsafe_allow_html=True)

# ============ SESSION STATE ============
if "user" not in st.session_state: st.session_state.user = None
if "page" not in st.session_state: st.session_state.page = "homework"
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "quiz_questions" not in st.session_state: st.session_state.quiz_questions = []
if "quiz_score" not in st.session_state: st.session_state.quiz_score = None
if "reading_data" not in st.session_state: st.session_state.reading_data = None
if "reading_score" not in st.session_state: st.session_state.reading_score = None

# ============ AUTH FUNCTIONS ============
def sign_up(email, password, data):
    try:
        user = auth.create_user(email=email, password=password)
        db.collection("users").document(user.uid).set({
            "email": email, 
            "usage_count": 0, 
            "subscription": "free", 
            "email_verified": False,
            "xp": 0,
            "quiz_count_today": 0,
            "reading_count_today": 0,
            "last_activity_date": datetime.now().strftime('%Y-%m-%d'),
            **data
        })
        send_verification_email(email)
        return user
    except auth.EmailAlreadyExistsError: return "This email is already registered."
    except Exception as e: return str(e)

def sign_in(email, password):
    try:
        user_record = auth.get_user_by_email(email)
        return user_record, None
    except Exception: return None, "invalid_credentials"

def reset_daily_counts_if_needed(user_ref, user_doc):
    """Reset daily counts if it's a new day"""
    last_date = user_doc.get('last_activity_date', '')
    today = datetime.now().strftime('%Y-%m-%d')
    
    if last_date != today:
        user_ref.update({
            "quiz_count_today": 0,
            "reading_count_today": 0,
            "last_activity_date": today
        })
        return True
    return False

# ============ AUTH UI (Redesigned) ============
if not st.session_state.user:
    # Hero section with logo
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
       # st.image("src/logo.png", width=200)
        st.markdown("<h1 style='text-align: center; color: #1e3a8a;'>French Tutor</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; font-size: 18px; color: #64748b;'>Your child's personal French Immersion expert<br><em>By The Study Zone</em></p>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Benefits section
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("### 📸")
        st.markdown("**Homework Help**")
        st.caption("Snap a photo, get instant help")
    with col2:
        st.markdown("### 📖")
        st.markdown("**Daily Reading**")
        st.caption("Build comprehension skills")
    with col3:
        st.markdown("### 📝")
        st.markdown("**Practice Quizzes**")
        st.caption("Test knowledge daily")
    with col4:
        st.markdown("### 💬")
        st.markdown("**Conversation**")
        st.caption("Practice speaking French")
    
    st.markdown("---")
    
    # Sign in / Sign up tabs (Sign In first!)
    tab1, tab2 = st.tabs(["🔐 Sign In", "✨ Create Account"])
    
    with tab1:
        st.markdown("### Welcome Back!")
        with st.form("signin_form"):
            email = st.text_input("Email Address")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")
        
        if submitted:
            user, error = sign_in(email, password)
            if error == "invalid_credentials": st.error("Invalid email or password.")
            elif user:
                user_doc = db.collection("users").document(user.uid).get().to_dict()
                st.session_state.user = {"uid": user.uid, "email": email, **user_doc}
                st.rerun()
        
        if st.button("Forgot Password?"):
            if email:
                if send_password_reset_email(email): st.success("Reset link sent!")
                else: st.error("Failed to send.")
            else: st.warning("Enter email first.")
    
    with tab2:
        st.markdown("### Create Your Account")
        with st.form("signup_form"):
            st.markdown("**👤 Parent Information**")
            email = st.text_input("Email Address", key="signup_email")
            password = st.text_input("Password", type="password", key="signup_pw")
            
            st.markdown("---")
            st.markdown("**🎓 Child's Profile**")
            student_name = st.text_input("Student's First Name")
            grade = st.selectbox("Grade", range(1, 9))
            
            st.markdown("---")
            st.markdown("**✨ Advanced Options (Optional)**")
            first_language = st.selectbox("Child's First Language", ["English", "Punjabi", "Urdu", "Hindi", "Arabic", "Other"])
            learning_style = st.selectbox("Learning Style", ["Visual (likes pictures)", "Auditory (likes listening)", "Kinesthetic (likes moving/doing)"])
            iep_needs = st.text_area("IEP Accommodations / Special Needs", placeholder="e.g., Needs extra time, simplified instructions...")
            parent_goal = st.text_area("Main Goal for this year", placeholder="e.g., Improve reading confidence...")
            
            submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")
            
            if submitted:
                if not email or not password or not student_name:
                    st.error("Please fill in required fields (email, password, student name).")
                else:
                    profile_data = {
                        "student_name": student_name, 
                        "parent_name": email.split('@')[0], 
                        "grade": grade,
                        "first_language": first_language,
                        "learning_style": learning_style,
                        "iep_needs": iep_needs,
                        "parent_goal": parent_goal
                    }
                    result = sign_up(email, password, profile_data)
                    if isinstance(result, str): st.error(result)
                    else: st.success("✅ Account created! Please check your email to verify, then sign in.")
    
    st.markdown("---")
    st.markdown("<p style='text-align: center; color: #94a3b8; font-size: 12px;'>Trusted by French Immersion families across Brampton, Mississauga, and the GTA</p>", unsafe_allow_html=True)
    st.stop()

# ============ MAIN APP ============
user = st.session_state.user
user_ref = db.collection("users").document(user["uid"])
user_doc = user_ref.get().to_dict()
usage = user_doc.get("usage_count", 0)

# Reset daily counts if it's a new day
reset_daily_counts_if_needed(user_ref, user_doc)
user_doc = user_ref.get().to_dict()  # Refresh after potential reset

# ============ SIDEBAR ============
with st.sidebar:
    # st.image("src/logo.png", width=150) # Keep commented out if logo is bad
    
    # Calculate Level based on XP (100 XP = Level 1, 200 XP = Level 2, etc.)
    user_xp = user_doc.get('xp', 0)
    user_level = (user_xp // 100) + 1
    xp_for_next_level = (user_level * 100) - user_xp
    
    st.markdown(f"### 👋 Bonjour, {user.get('student_name', 'Student')}!")
    st.markdown(f"**Grade {user.get('grade', '?')}**")
    
    # XP Progress Bar
    st.markdown(f"**Level {user_level}** ({user_xp} XP)")
    st.progress(user_xp % 100 / 100)
    st.caption(f"{xp_for_next_level} XP to Level {user_level + 1}")
    
    st.markdown("---")
    
    # --- FEATURE LOCKING LOGIC ---
    is_pro = user_doc.get('subscription') == 'paid'
    
    # Homework is always accessible (but limited by usage count)
    if st.button("📸 Homework Helper", use_container_width=True, type="primary" if st.session_state.page=="homework" else "secondary"):
        st.session_state.page = "homework"; st.rerun()
    
    # Reading is locked for free users after 1 per day
    reading_locked = (not is_pro) and (user_doc.get('reading_count_today', 0) >= 1)
    if reading_locked:
        st.button("📖 Daily Reading 🔒", use_container_width=True, disabled=True, help="Upgrade to Pro for unlimited readings!")
    elif st.button("📖 Daily Reading", use_container_width=True, type="primary" if st.session_state.page=="reading" else "secondary"):
        st.session_state.page = "reading"; st.session_state.reading_score = None; st.rerun()
    
    # Quiz is locked for free users after 1 per day
    quiz_locked = (not is_pro) and (user_doc.get('quiz_count_today', 0) >= 1)
    if quiz_locked:
        st.button("📝 Daily Quiz 🔒", use_container_width=True, disabled=True, help="Upgrade to Pro for unlimited quizzes!")
    elif st.button("📝 Daily Quiz", use_container_width=True, type="primary" if st.session_state.page=="quiz" else "secondary"):
        st.session_state.page = "quiz"; st.session_state.quiz_score = None; st.rerun()
    
    # Practice Chat is PRO ONLY
    if not is_pro:
        st.button("💬 Practice Chat 🔒", use_container_width=True, disabled=True, help="Upgrade to Pro to chat with Madame AI!")
    elif st.button("💬 Practice Chat", use_container_width=True, type="primary" if st.session_state.page=="practice" else "secondary"):
        st.session_state.page = "practice"; st.session_state.chat_history = []; st.rerun()
    
    if st.button("📊 Progress Dashboard", use_container_width=True, type="primary" if st.session_state.page=="progress" else "secondary"):
        st.session_state.page = "progress"; st.rerun()
    if st.button("⚙️ My Profile", use_container_width=True, type="primary" if st.session_state.page=="profile" else "secondary"):
        st.session_state.page = "profile"; st.rerun()
    
    st.markdown("---")
    
    if not is_pro:
        st.markdown("### 🚀 Go Pro!")
        st.caption("Unlock unlimited access & chat")
        monthly_link = os.getenv("STRIPE_MONTHLY_LINK") or "#"
        st.markdown(f"[**Upgrade to Pro - $15/mo**]({monthly_link})")
        st.markdown("---")
    
    st.caption(f"Homework uses: {usage}/{FREE_LIMIT}")
    if st.button("Sign Out", use_container_width=True):
        st.session_state.user = None; st.rerun()

# ============ PAGES ============

# --- PROFILE PAGE ---
if st.session_state.page == "profile":
    st.title("⚙️ My Profile")
    st.write(f"**Email:** {user['email']}")
    st.write(f"**Student:** {user.get('student_name')}")
    st.write(f"**Grade:** {user.get('grade')}")
    st.write(f"**First Language:** {user.get('first_language')}")
    st.write(f"**Learning Style:** {user.get('learning_style')}")
    st.write(f"**IEP Needs:** {user.get('iep_needs', 'None')}")
    st.write(f"**Parent Goal:** {user.get('parent_goal', 'N/A')}")
    st.markdown("---")
    if st.button("Send Password Reset Email"):
        if send_password_reset_email(user['email']): st.success("Check your email!")

# --- PRACTICE CHAT PAGE ---
elif st.session_state.page == "practice":
    st.title("💬 Practice Chat")
    st.caption("Chat with Madame AI to practice your French conversation!")
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]): st.markdown(message["content"])
    if prompt := st.chat_input("Type in French or English..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Madame is thinking..."):
                response = chat_with_tutor(st.session_state.chat_history, prompt, user)
                st.markdown(response)
        st.session_state.chat_history.append({"role": "assistant", "content": response})
        
        # Award XP for chatting (5 XP per message)
        user_ref.update({"xp": firestore.Increment(5)})

# --- DAILY QUIZ PAGE ---
elif st.session_state.page == "quiz":
    st.title("📝 Daily French Quiz")
    st.caption("Test your knowledge! Madame AI will generate 5 questions just for your grade level.")
    
    if not st.session_state.quiz_questions:
        if st.button("🎲 Generate New Quiz", type="primary"):
            with st.spinner("Madame is writing your quiz..."):
                try:
                    st.session_state.quiz_questions = generate_quiz(user)
                    st.session_state.quiz_score = None
                except Exception as e:
                    st.error(f"Failed to generate quiz: {e}")
    
    if st.session_state.quiz_questions:
        if st.session_state.quiz_score is None:
            answers = {}
            for i, q in enumerate(st.session_state.quiz_questions):
                st.markdown(f"### Question {i+1}: {q['question']}")
                answers[i] = st.radio(f"Select answer for Q{i+1}", q['options'], key=f"q_{i}", index=None)
            
            if st.button("Submit Quiz", type="primary"):
                score = 0
                results = []
                for i, q in enumerate(st.session_state.quiz_questions):
                    is_correct = answers[i] == q['answer']
                    if is_correct: score += 1
                    results.append({"question": q['question'], "user_answer": answers[i], "correct_answer": q['answer'], "explanation": q['explanation'], "is_correct": is_correct})
                
                st.session_state.quiz_score = score
                st.session_state.quiz_results = results
                
                # Save to Firestore AND ADD XP
                db.collection("quiz_results").add({
                    "user_id": user["uid"], 
                    "score": score, 
                    "total": len(st.session_state.quiz_questions), 
                    "results": results, 
                    "created_at": firestore.SERVER_TIMESTAMP
                })
                
                # Add XP (10 XP per correct answer)
                xp_earned = score * 10
                user_ref.update({
                    "xp": firestore.Increment(xp_earned),
                    "quiz_count_today": firestore.Increment(1)
                })
                
                st.success(f"🎉 You earned {xp_earned} XP!")
                st.rerun()
        else:
            score = st.session_state.quiz_score
            total = len(st.session_state.quiz_questions)
            percentage = (score / total) * 100
            if percentage >= 70: st.balloons()
            st.markdown(f"## 🎉 You scored {score} out of {total}! ({percentage:.0f}%)")
            
            for i, res in enumerate(st.session_state.quiz_results):
                status = "✅ Correct!" if res['is_correct'] else "❌ Incorrect"
                st.markdown(f"**Q{i+1}: {res['question']}**")
                st.markdown(f"Your answer: {res['user_answer']} {status}")
                if not res['is_correct']:
                    st.markdown(f"Correct answer: **{res['correct_answer']}**")
                st.info(f"💡 Madame's Tip: {res['explanation']}")
                st.markdown("---")
                
            if st.button("Take Another Quiz"):
                st.session_state.quiz_questions = []
                st.session_state.quiz_score = None
                st.rerun()

# --- DAILY READING PAGE ---
elif st.session_state.page == "reading":
    st.title("📖 Daily Reading Comprehension")
    st.caption("Read a French passage and answer questions to build your skills!")
    
    if not st.session_state.reading_data:
        if st.button("📚 Generate Today's Reading", type="primary"):
            with st.spinner("Madame is preparing your reading passage..."):
                try:
                    st.session_state.reading_data = generate_reading_comprehension(user)
                    st.session_state.reading_score = None
                except Exception as e:
                    st.error(f"Failed to generate reading: {e}")
    
    if st.session_state.reading_data:
        rd = st.session_state.reading_data
        
        st.markdown(f"### 📖 {rd.get('title', 'Reading Passage')}")
        st.markdown("**French Passage:**")
        st.info(rd.get('passage', ''))
        
        if st.button("🔊 Listen to Passage"):
            with st.spinner("Generating audio..."):
                try:
                    audio_dir = tempfile.mkdtemp()
                    audio_path = os.path.join(audio_dir, "passage.mp3")
                    generate_audio(rd.get('passage', ''), audio_path)
                    
                    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                        st.audio(audio_path)
                    else:
                        st.warning("⚠️ Audio generation failed. Please try again.")
                except Exception as e:
                    st.warning(f"⚠️ Audio temporarily unavailable: {str(e)[:100]}")
        
        with st.expander("📝 English Translation"):
            st.write(rd.get('translation', ''))
        
        st.markdown("---")
        
        if st.session_state.reading_score is None:
            answers = {}
            questions = rd.get('questions', [])
            for i, q in enumerate(questions):
                st.markdown(f"**Question {i+1}: {q['question']}**")
                answers[i] = st.radio(f"Answer for Q{i+1}", q['options'], key=f"rq_{i}", index=None)
            
            if st.button("Submit Answers", type="primary"):
                score = 0
                results = []
                questions = rd.get('questions', [])
                for i, q in enumerate(questions):
                    is_correct = answers.get(i) == q['answer']
                    if is_correct: score += 1
                    results.append({"question": q['question'], "user_answer": answers.get(i), "correct_answer": q['answer'], "explanation": q['explanation'], "is_correct": is_correct})
                
                st.session_state.reading_score = score
                st.session_state.reading_results = results
                st.session_state.reading_total = len(questions)
                
                # Save to Firestore AND ADD XP
                db.collection("reading_results").add({
                    "user_id": user["uid"], 
                    "score": score, 
                    "total": len(questions), 
                    "title": rd.get('title', ''),
                    "results": results, 
                    "created_at": firestore.SERVER_TIMESTAMP
                })
                
                # Add XP (15 XP for completing a reading)
                xp_earned = 15
                user_ref.update({
                    "xp": firestore.Increment(xp_earned),
                    "reading_count_today": firestore.Increment(1)
                })
                
                st.success(f"🎉 You earned {xp_earned} XP!")
                st.rerun()
        else:
            score = st.session_state.reading_score
            total = st.session_state.reading_total
            percentage = (score / total) * 100 if total > 0 else 0
            if percentage >= 70: st.balloons()
            st.markdown(f"## 🎉 You scored {score} out of {total}! ({percentage:.0f}%)")
            
            for i, res in enumerate(st.session_state.reading_results):
                status = "✅ Correct!" if res['is_correct'] else "❌ Incorrect"
                st.markdown(f"**Q{i+1}: {res['question']}**")
                st.markdown(f"Your answer: {res['user_answer']} {status}")
                if not res['is_correct']:
                    st.markdown(f"Correct answer: **{res['correct_answer']}**")
                st.info(f"💡 Tip: {res['explanation']}")
                st.markdown("---")
            
            if st.button("📚 Try Another Reading"):
                st.session_state.reading_data = None
                st.session_state.reading_score = None
                st.rerun()

# --- PROGRESS DASHBOARD PAGE ---
elif st.session_state.page == "progress":
    st.title("📊 Progress Dashboard")
    st.caption("Track your child's French learning journey!")
    
    quiz_data = db.collection("quiz_results").where("user_id", "==", user["uid"]).order_by("created_at", direction=firestore.Query.DESCENDING).limit(50).stream()
    quizzes = [doc.to_dict() for doc in quiz_data]
    
    reading_data = db.collection("reading_results").where("user_id", "==", user["uid"]).order_by("created_at", direction=firestore.Query.DESCENDING).limit(50).stream()
    readings = [doc.to_dict() for doc in reading_data]
    
    if not quizzes and not readings:
        st.info("📝 No activities yet! Start with **Daily Reading** or **Daily Quiz** to track progress.")
    else:
        total_quizzes = len(quizzes)
        total_readings = len(readings)
        
        quiz_scores = [q['score'] for q in quizzes] if quizzes else [0]
        reading_scores = [r['score'] for r in readings] if readings else [0]
        
        avg_quiz = sum(quiz_scores) / len(quiz_scores) if quizzes else 0
        avg_reading = sum(reading_scores) / len(reading_scores) if readings else 0
        
        total_questions = sum(q['total'] for q in quizzes) + sum(r['total'] for r in readings)
        correct_answers = sum(quiz_scores) + sum(reading_scores)
        overall_accuracy = (correct_answers / total_questions) * 100 if total_questions > 0 else 0
        
        all_dates = []
        for q in quizzes:
            if q.get('created_at'): all_dates.append(q['created_at'].strftime('%Y-%m-%d'))
        for r in readings:
            if r.get('created_at'): all_dates.append(r['created_at'].strftime('%Y-%m-%d'))
        
        unique_dates = sorted(list(set(all_dates)))
        streak = 0
        if unique_dates:
            today = datetime.now().date()
            for i in range(len(unique_dates) + 1):
                check_date = today - timedelta(days=i)
                if check_date.strftime('%Y-%m-%d') in unique_dates:
                    streak += 1
                else:
                    break
        
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1: st.metric("Quizzes Taken", total_quizzes)
        with col2: st.metric("Readings Done", total_readings)
        with col3: st.metric("Avg Quiz Score", f"{avg_quiz:.1f}")
        with col4: st.metric("Avg Reading", f"{avg_reading:.1f}")
        with col5: st.metric("🔥 Day Streak", streak)
        
        st.markdown("---")
        
        st.subheader("📈 Score Trend Over Time")
        chart_data = []
        for q in quizzes:
            if q.get('created_at'):
                chart_data.append({"Date": q['created_at'].strftime('%Y-%m-%d'), "Type": "Quiz", "Score": q['score']})
        for r in readings:
            if r.get('created_at'):
                chart_data.append({"Date": r['created_at'].strftime('%Y-%m-%d'), "Type": "Reading", "Score": r['score']})
        
        if chart_data:
            import pandas as pd
            df = pd.DataFrame(chart_data)
            df = df.sort_values("Date")
            st.line_chart(df.set_index("Date")["Score"])
        
        st.markdown("---")
        
        st.subheader("🎯 Areas to Focus On")
        wrong_answers = []
        for q in quizzes:
            for result in q.get('results', []):
                if not result.get('is_correct'): wrong_answers.append(("Quiz", result['question']))
        for r in readings:
            for result in r.get('results', []):
                if not result.get('is_correct'): wrong_answers.append(("Reading", result['question']))
        
        if wrong_answers:
            st.warning(f"Your child has missed {len(wrong_answers)} questions. Review these:")
            for i, (source, question) in enumerate(wrong_answers[:5]):
                st.markdown(f"**{i+1}. [{source}]** {question}")
        else:
            st.success("🎉 Perfect record! No weak areas detected yet.")
        
        st.markdown("---")
        
        st.subheader("📅 Recent Activity")
        all_activity = []
        for q in quizzes:
            if q.get('created_at'):
                all_activity.append({"date": q['created_at'], "type": "Quiz", "score": q['score'], "total": q['total']})
        for r in readings:
            if r.get('created_at'):
                all_activity.append({"date": r['created_at'], "type": "Reading", "score": r['score'], "total": r['total']})
        
        all_activity.sort(key=lambda x: x['date'], reverse=True)
        
        for activity in all_activity[:15]:
            date_str = activity['date'].strftime('%b %d, %Y at %I:%M %p')
            icon = "📝" if activity['type'] == "Quiz" else "📖"
            st.markdown(f"**{date_str}** {icon} {activity['type']}: {activity['score']}/{activity['total']} ({(activity['score']/activity['total']*100):.0f}%)")

# --- HOMEWORK HELPER PAGE ---
elif st.session_state.page == "homework":
    st.title("📸 Homework Helper")
    st.caption("Upload a photo or PDF for an instant lesson plan.")
    if usage >= FREE_LIMIT:
        st.warning(f"You've used your {FREE_LIMIT} free helps.")
        monthly_link = os.getenv("STRIPE_MONTHLY_LINK") or "mailto:hello@thestudyzone.ca"
        family_link = os.getenv("STRIPE_FAMILY_LINK") or "mailto:hello@thestudyzone.ca"
        col1, col2 = st.columns(2)
        with col1: st.markdown(f"**Monthly $15**\n[Subscribe]({monthly_link})")
        with col2: st.markdown(f"**Family $25**\n[Subscribe]({family_link})")
        st.stop()

    uploaded = st.file_uploader("Choose image or PDF", type=["jpg", "jpeg", "png", "pdf"])
    if st.button("🎯 Analyze Homework", type="primary", disabled=not uploaded):
        with st.spinner("Madame AI is analyzing..."):
            file_bytes = uploaded.read()
            try: ai_response = extract_and_analyze_homework(file_bytes, uploaded.type, user)
            except Exception as e: st.error(f"Failed: {e}"); st.stop()
            if not ai_response.get("translation"): st.error("Could not read homework."); st.stop()
                
        with st.spinner("Generating audio..."):
            audio_dir = tempfile.mkdtemp()
            vocab_audio = generate_vocab_audio(ai_response.get("vocabulary", []), audio_dir) if ai_response.get("vocabulary") else []
            
        db.collection("homework_sessions").add({"user_id": user["uid"], "ai_response": ai_response, "created_at": firestore.SERVER_TIMESTAMP})
        user_ref.update({"usage_count": firestore.Increment(1)})
        
        st.markdown("---")
        st.markdown("## 📖 Translation"); st.info(ai_response.get("translation"))
        st.markdown(f"## 🧠 Concept: **{ai_response.get('concept')}**"); st.write(ai_response.get("concept_explained"))
        st.markdown("## 👨‍👩‍👧 Parent Coach Steps")
        for i, step in enumerate(ai_response.get("parent_coach_steps", []), 1): st.markdown(f"**{i}.** {step}")
        if ai_response.get("vocabulary"):
            st.markdown("## 📚 Vocabulary")
            for i, word in enumerate(ai_response["vocabulary"]):
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(f"**{word.get('french')}**"); c2.write(word.get("english"))
                audio_match = next((a for a in vocab_audio if a["index"] == i), None)
                if audio_match: c3.audio(audio_match["audio_path"])
        st.markdown(f"**Curriculum:** {ai_response.get('ontario_curriculum_link')}")
        st.success(ai_response.get("encouragement"))
