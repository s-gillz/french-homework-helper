import os
import json
import requests
from datetime import datetime, timedelta
from firebase_admin import credentials, firestore, initialize_app

# --- CONFIGURATION ---
TEST_MODE = False  # ⚠️ SET TO FALSE FOR PRODUCTION
TEST_EMAIL = "gillz@teachers.org" 

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
    seven_days_ago = datetime.now() - timedelta(days=7)
    quizzes = db.collection("quiz_results").where("user_id", "==", user_id).where("created_at", ">=", seven_days_ago).stream()
    quiz_list = [q.to_dict() for q in quizzes]
    readings = db.collection("reading_results").where("user_id", "==", user_id).where("created_at", ">=", seven_days_ago).stream()
    reading_list = [r.to_dict() for r in readings]
    
    total_quizzes = len(quiz_list)
    total_readings = len(reading_list)
    avg_quiz_score = sum((q['score']/q['total'])*100 for q in quiz_list) / total_quizzes if total_quizzes > 0 else 0
    avg_reading_score = sum((r['score']/r['total'])*100 for r in reading_list) / total_readings if total_readings > 0 else 0
        
    return {
        "quizzes": total_quizzes, "readings": total_readings,
        "avg_quiz": round(avg_quiz_score, 1), "avg_reading": round(avg_reading_score, 1)
    }

def send_email(to_email, student_name, stats, is_pro):
    # Add a "Go Pro" CTA if the user is on the free tier
    cta_html = ""
    if not is_pro:
        cta_html = """
        <div style="background-color: #fffbeb; border: 1px solid #fcd34d; padding: 15px; border-radius: 8px; margin: 20px 0; text-align: center;">
            <p style="margin: 0 0 10px 0; font-weight: bold; color: #92400e;"> Unlock Unlimited Learning!</p>
            <p style="margin: 0 0 15px 0; font-size: 14px; color: #92400e;">Get unlimited quizzes, readings, and AI chat practice.</p>
            <a href="https://huggingface.co/spaces/GillzTSZ/french-homework-helper" style="background-color: #1e3a8a; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; font-weight: bold;">Upgrade to Pro - $15/mo</a>
        </div>
        """

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #333; line-height: 1.6;">
        <div style="background-color: #1e3a8a; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 24px;">Weekly French Progress Report</h1>
            <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.9;">The Study Zone - French Tutor</p>
        </div>
        <div style="padding: 30px 20px; border: 1px solid #e5e7eb; border-top: none;">
            <p style="font-size: 16px; margin: 0 0 20px 0;">Bonjour! Here is how <strong>{student_name}</strong> did this week:</p>
            <div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="margin: 0 0 15px 0; color: #1e3a8a; font-size: 18px;">This Week's Progress</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px 0; border-bottom: 1px solid #d1d5db;"><strong>Quizzes Completed:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #d1d5db; text-align: right;">{stats['quizzes']}</td></tr>
                    <tr><td style="padding: 8px 0; border-bottom: 1px solid #d1d5db;"><strong>Average Quiz Score:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #d1d5db; text-align: right;">{stats['avg_quiz']}%</td></tr>
                    <tr><td style="padding: 8px 0; border-bottom: 1px solid #d1d5db;"><strong>Readings Completed:</strong></td><td style="padding: 8px 0; border-bottom: 1px solid #d1d5db; text-align: right;">{stats['readings']}</td></tr>
                    <tr><td style="padding: 8px 0;"><strong>Average Reading Score:</strong></td><td style="padding: 8px 0; text-align: right;">{stats['avg_reading']}%</td></tr>
                </table>
            </div>
            {cta_html}
            <p style="font-size: 16px; margin: 20px 0;">Consistency is the key to language learning. Keep up the great work, {student_name}!</p>
        </div>
        <div style="background-color: #f9fafb; padding: 20px; text-align: center; font-size: 12px; color: #6b7280; border-radius: 0 0 8px 8px; border: 1px solid #e5e7eb; border-top: none;">
            <p style="margin: 0 0 10px 0;">The Study Zone | Brampton, Ontario</p>
            <p style="margin: 0;"><a href="mailto:hello@thestudyzone.ca?subject=Unsubscribe" style="color: #6b7280;">Unsubscribe</a></p>
        </div>
    </div>
    """
    
    payload = {
        "sender": {"email": SENDER_EMAIL, "name": "The Study Zone"},
        "to": [{"email": to_email}],
        "subject": f"{student_name}'s Weekly French Progress Report",
        "htmlContent": html_content
    }
    headers = {"accept": "application/json", "content-type": "application/json", "api-key": BREVO_API_KEY}
    response = requests.post(BREVO_URL, json=payload, headers=headers)
    return response.status_code

def main():
    print("Starting weekly report generation...")
    users = db.collection("users").stream()
    sent_count = 0
    
    for user_doc in users:
        user_data = user_doc.to_dict()
        user_id = user_doc.id
        email = user_data.get("email")
        student_name = user_data.get("student_name", "Student")
        is_pro = user_data.get("subscription") == "paid"
        
        if not email: continue
            
        stats = get_user_activity(user_id)
        
        # Send to anyone who was active this week (Free or Pro)
        if stats["quizzes"] > 0 or stats["readings"] > 0:
            target_email = TEST_EMAIL if TEST_MODE else email
            print(f"Sending to {target_email} ({student_name})...")
            status = send_email(target_email, student_name, stats, is_pro)
            if status == 201: sent_count += 1
            
    print(f"Done! Successfully sent {sent_count} emails.")

if __name__ == "__main__":
    main()
