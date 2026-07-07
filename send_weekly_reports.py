import os
import json
import requests
from datetime import datetime, timedelta
from firebase_admin import credentials, firestore, initialize_app

# --- CONFIGURATION ---
TEST_MODE = True  # Keep True for now - only emails TEST_EMAIL
TEST_EMAIL = "gillz@teachers.org"  # 👈 CHANGE THIS TO YOUR EMAIL!

# --- INIT FIREBASE ---
cred_dict = json.loads(os.environ["FIREBASE_CREDENTIALS"])
cred = credentials.Certificate(cred_dict)
initialize_app(cred)
db = firestore.client()

# --- BREVO CONFIG ---
BREVO_API_KEY = os.environ["BREVO_API_KEY"]
SENDER_EMAIL = os.environ["SENDER_EMAIL"]
BREVO_URL = "https://api.brevo.com/v3/smtp/email"

def get_user_activity(user_id):
    """Fetches quiz and reading stats for the last 7 days"""
    seven_days_ago = datetime.now() - timedelta(days=7)
    
    quizzes = db.collection("quiz_results").where("user_id", "==", user_id).where("created_at", ">=", seven_days_ago).stream()
    quiz_list = [q.to_dict() for q in quizzes]
    
    readings = db.collection("reading_results").where("user_id", "==", user_id).where("created_at", ">=", seven_days_ago).stream()
    reading_list = [r.to_dict() for r in readings]
    
    total_quizzes = len(quiz_list)
    total_readings = len(reading_list)
    
    avg_quiz_score = 0
    if total_quizzes > 0:
        avg_quiz_score = sum((q['score']/q['total'])*100 for q in quiz_list) / total_quizzes
        
    avg_reading_score = 0
    if total_readings > 0:
        avg_reading_score = sum((r['score']/r['total'])*100 for r in reading_list) / total_readings
        
    return {
        "quizzes": total_quizzes,
        "readings": total_readings,
        "avg_quiz": round(avg_quiz_score, 1),
        "avg_reading": round(avg_reading_score, 1)
    }

def send_email(to_email, student_name, stats):
    """Sends the HTML email via Brevo"""
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333;">
        <div style="background-color: #1e3a8a; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0;">🇫🇷 Weekly French Progress Report</h1>
            <p style="margin: 5px 0 0 0; font-size: 14px;">By The Study Zone</p>
        </div>
        <div style="padding: 20px; border: 1px solid #e5e7eb; border-top: none;">
            <p>Bonjour! Here is how <strong>{student_name}</strong> did this week:</p>
            
            <div style="background-color: #f3f4f6; padding: 15px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin-top: 0; color: #1e3a8a;">📊 This Week's Stats</h3>
                <p>📝 <strong>Quizzes Completed:</strong> {stats['quizzes']}</p>
                <p>🎯 <strong>Average Quiz Score:</strong> {stats['avg_quiz']}%</p>
                <p>📖 <strong>Readings Completed:</strong> {stats['readings']}</p>
                <p>🧠 <strong>Average Reading Score:</strong> {stats['avg_reading']}%</p>
            </div>
            
            <p>Consistency is the key to language learning. Even 10 minutes a day makes a massive difference!</p>
            <p>Keep up the great work, {student_name}! 🌟</p>
        </div>
        <div style="background-color: #f9fafb; padding: 15px; text-align: center; font-size: 12px; color: #6b7280; border-radius: 0 0 8px 8px; border: 1px solid #e5e7eb; border-top: none;">
            <p>Need help with tonight's homework? <a href="https://huggingface.co/spaces/GillzTSZ/french-homework-helper" style="color: #1e3a8a;">Log in to your French Tutor</a></p>
        </div>
    </div>
    """
    
    payload = {
        "sender": {"email": SENDER_EMAIL, "name": "French Tutor by The Study Zone"},
        "to": [{"email": to_email}],
        "subject": f"🇫🇷 {student_name}'s Weekly French Progress Report!",
        "htmlContent": html_content
    }
    
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "api-key": BREVO_API_KEY
    }
    
    response = requests.post(BREVO_URL, json=payload, headers=headers)
    return response.status_code

def main():
    print("Starting weekly report generation...")
    print(f"Test mode: {TEST_MODE}")
    print(f"Test email: {TEST_EMAIL}")
    print(f"Sender email: {SENDER_EMAIL}")
    print("-" * 50)
    
    users = db.collection("users").stream()
    sent_count = 0
    user_count = 0
    
    for user_doc in users:
        user_data = user_doc.to_dict()
        user_id = user_doc.id
        email = user_data.get("email")
        student_name = user_data.get("student_name", "Student")
        subscription = user_data.get("subscription", "free")
        
        user_count += 1
        print(f"\n[User {user_count}] {student_name} ({email})")
        print(f"  Subscription: {subscription}")
        
        if not email:
            print("  ⚠️  Skipped: No email address")
            continue
        
        # REMOVED SUBSCRIPTION FILTER FOR DEBUGGING
        # Previously: if subscription != "paid": continue
        
        stats = get_user_activity(user_id)
        print(f"  Activity: {stats['quizzes']} quizzes, {stats['readings']} readings")
        
        # Only email if they were active this week
        if stats["quizzes"] > 0 or stats["readings"] > 0:
            target_email = TEST_EMAIL if TEST_MODE else email
            
            print(f"  ✅ Sending to: {target_email}")
            status = send_email(target_email, student_name, stats)
            
            if status == 201:
                sent_count += 1
                print(f"  ✅ SUCCESS!")
            else:
                print(f"  ❌ FAILED. Status: {status}")
        else:
            print("  ⚠️  Skipped: No activity this week")
    
    print("\n" + "=" * 50)
    print(f"Total users found: {user_count}")
    print(f"Emails sent: {sent_count}")
    print("Done!")

if __name__ == "__main__":
    main()
