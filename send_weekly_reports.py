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
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333; line-height: 1.6;">
        <div style="background-color: #1e3a8a; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 24px;">Weekly French Progress Report</h1>
            <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.9;">The Study Zone - French Tutor</p>
        </div>
        
        <div style="padding: 30px 20px; border: 1px solid #e5e7eb; border-top: none;">
            <p style="font-size: 16px; margin: 0 0 20px 0;">Bonjour!</p>
            <p style="font-size: 16px; margin: 0 0 20px 0;">Here is how <strong>{student_name}</strong> did this week:</p>
            
            <div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin: 0 0 15px 0; color: #1e3a8a; font-size: 18px;">This Week's Progress</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #d1d5db;"><strong>Quizzes Completed:</strong></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #d1d5db; text-align: right;">{stats['quizzes']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #d1d5db;"><strong>Average Quiz Score:</strong></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #d1d5db; text-align: right;">{stats['avg_quiz']}%</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0; border-bottom: 1px solid #d1d5db;"><strong>Readings Completed:</strong></td>
                        <td style="padding: 8px 0; border-bottom: 1px solid #d1d5db; text-align: right;">{stats['readings']}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px 0;"><strong>Average Reading Score:</strong></td>
                        <td style="padding: 8px 0; text-align: right;">{stats['avg_reading']}%</td>
                    </tr>
                </table>
            </div>
            
            <p style="font-size: 16px; margin: 20px 0;">Consistency is the key to language learning. Even 10 minutes a day makes a significant difference!</p>
            <p style="font-size: 16px; margin: 0;">Keep up the great work, {student_name}!</p>
        </div>
        
        <div style="background-color: #f9fafb; padding: 20px; text-align: center; font-size: 12px; color: #6b7280; border-radius: 0 0 8px 8px; border: 1px solid #e5e7eb; border-top: none;">
            <p style="margin: 0 0 10px 0;">Need help with tonight's homework?</p>
            <p style="margin: 0;"><a href="https://huggingface.co/spaces/GillzTSZ/french-homework-helper" style="color: #1e3a8a; text-decoration: none;">Log in to your French Tutor</a></p>
            <p style="margin: 15px 0 0 0; font-size: 11px;">The Study Zone | Brampton, Ontario</p>
            <p style="margin: 10px 0 0 0; font-size: 11px;">
    <a href="mailto:info@thestudyzone.ca?subject=Unsubscribe" style="color: #6b7280;">Unsubscribe from weekly reports</a>
</p>
        </div>
    </div>
    """
    
        payload = {
        "sender": {"email": SENDER_EMAIL, "name": "The Study Zone"},
        "to": [{"email": to_email}],
        "subject": f"{student_name}'s Weekly French Progress Report",
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
    
    # FORCE TEST: Send to TEST_EMAIL regardless of activity
    print("\n🧪 FORCE TEST MODE: Sending test email...")
    
    fake_stats = {
        "quizzes": 5,
        "readings": 3,
        "avg_quiz": 85.5,
        "avg_reading": 90.0
    }
    
    print(f"Sending test email to: {TEST_EMAIL}")
    status = send_email(TEST_EMAIL, "Test Student", fake_stats)
    
    if status == 201:
        print("✅ SUCCESS! Check your email inbox.")
        print("   The email system is working perfectly.")
    else:
        print(f"❌ FAILED. Status code: {status}")
        print("   Check your Brevo API key and domain verification.")
    
    print("\n" + "=" * 50)
    print("Test complete!")

if __name__ == "__main__":
    main()
