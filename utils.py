import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_notification_email(to_email, subject, body_html):
    """
    Sends an email using SMTP. If SMTP_EMAIL is not set in environment variables,
    it falls back to printing the email safely in the terminal.
    """
    # Prevent sending to the dummy fallback email
    if to_email == 'no-email@local' or not to_email:
        return False
        
    smtp_email = os.environ.get('SMTP_EMAIL', 'complaintanalyzer@gmail.com')
    smtp_password = os.environ.get('SMTP_PASSWORD', 'anslzabwjnxjlqev')
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    
    msg = MIMEMultipart("alternative")
    msg['Subject'] = subject
    msg['From'] = f"Civic Analyzer <{smtp_email or 'no-reply@civicanalyzer.org'}>"
    msg['To'] = to_email
    
    # Attach HTML body
    part = MIMEText(body_html, "html")
    msg.attach(part)
    
    if smtp_email and smtp_password:
        try:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.sendmail(msg['From'], [msg['To']], msg.as_string())
            server.quit()
            print(f"[EMAIL SYSTEM] Successfully sent email to {to_email}")
            return True
        except Exception as e:
            print(f"[EMAIL SYSTEM] Failed to send email via SMTP to {to_email}: {e}")
            return False
    else:
        print("\n" + "="*60)
        print(f"[EMAIL SYSTEM MOCK - NO CREDENTIALS PROVIDED]")
        print(f"To: {to_email}")
        print(f"Subject: {subject}")
        print("Body (HTML):")
        print(body_html)
        print("="*60 + "\n")
        return True
