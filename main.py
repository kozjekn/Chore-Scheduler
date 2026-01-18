import os
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import gspread
import smtplib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler
from pydantic import BaseModel
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# --- Configuration from Environment ---
SHEET_NAME = os.getenv("SHEET_NAME")
CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
# We strip spaces just in case to avoid the 535 Auth error
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD").replace(" ", "")


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for dev, restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---
class LogItem(BaseModel):
    email: str
    task_name: str
    room_name: str
    date: str = None

class DeleteItem(BaseModel):
    email: str
    task_name: str
    room_name: str
    date: str

# --- Helpers ---
def get_sheets():
    gc = gspread.service_account(filename=CREDENTIALS_FILE)
    sh = gc.open(SHEET_NAME)
    # Note: Ensure your sheet tab names match exactly what you have in Google Sheets
    return sh.worksheet("Tasks"), sh.worksheet("Log") # Changed "Chores" to "Tasks" based on your data

tasks_ws, log_ws = get_sheets()

def parse_frequency(freq_str, due_threshold=7):
    """Converts text frequency to days"""
    f = freq_str.lower().strip()
    if "day" in f and "every" in f: return 1
    if "weekly" in f: return 7
    if "bi-weekly" in f: return 14
    if "month" in f: return 30
    if "year" in f: return 365
    return 7 # Default fallback

def calculate_due_status(task_row, log_map, due_threshold=7):
    """Core logic shared by API and Emailer"""
    task_name = task_row['Task']
    room_name = task_row['Room']
    frequency = parse_frequency(task_row['Frequency'])
    
    # Composite Key: Task + Room
    key = (task_name, room_name)
    
    last_done = None
    if key in log_map and log_map[key]:
        last_done = max(log_map[key])
    
    today = datetime.now().date()
    next_due_date = today # Default if never done
    
    if last_done:
        next_due_date = last_done + timedelta(days=frequency)
    
    days_until = (next_due_date - today).days
    
    return {
        "task": task_name,
        "room": room_name,
        "notes": task_row['Notes'],
        "target_day": task_row['Target Day of Week'],
        "frequency": task_row['Frequency'],
        "due_date": next_due_date.strftime("%Y-%m-%d"),
        "days_until": days_until,
        "is_due": days_until <= due_threshold
    }

# --- Endpoints ---

@app.get("/tasks")
def get_tasks(email: str):
    task_due_threshold = 6
    
    # 1. Get raw data
    all_tasks = tasks_ws.get_all_records()
    all_logs = log_ws.get_all_records()
    
    # 2. Filter User's Tasks
    user_tasks = [t for t in all_tasks if t['Owner'].strip().lower() == email.strip().lower() or t['Owner'].strip().lower() == 'all']
    
    # 3. Build Log Map: {(Task, Room): [date_obj, ...]}
    log_map = {}
    recent_history = []
    today = datetime.now().date()

    for log in all_logs:
        # Check if this log belongs to user (case insensitive)
        if log['Done By'].strip().lower() == email.strip().lower():
            try:
                l_date = datetime.strptime(log['Date'], "%Y-%m-%d").date()
                key = (log['Task'], log['Room'])
                
                if key not in log_map: log_map[key] = []
                log_map[key].append(l_date)

                # Add to history if recent (last 3 days)
                if (today - l_date).days <= 3:
                    recent_history.append({
                        "task": log['Task'],
                        "room": log['Room'],
                        "date": log['Date']
                    })
            except ValueError:
                continue

    # 4. Calculate Due Dates
    due_list = []
    for task in user_tasks:
        status = calculate_due_status(task, log_map, due_threshold=task_due_threshold)
        if status['is_due']:
            due_list.append(status)

    return {
        "due_tasks": sorted(due_list, key=lambda x: (x['days_until'], x['task'])),
        "recent_history": sorted(recent_history, key=lambda x: x['date'], reverse=True)
    }

@app.post("/log")
def log_chore(item: LogItem):
    today = datetime.now().strftime("%Y-%m-%d")
    # Columns: Task, Room, Date, Done By
    log_ws.append_row([item.task_name, item.room_name, today, item.email])
    return {"status": "logged"}

@app.post("/uncheck")
def uncheck_chore(item: DeleteItem):
    records = log_ws.get_all_records()
    
    # Find row to delete (Exact match on all 4 fields)
    row_to_delete = -1
    for i, r in enumerate(records):
        if (r['Task'] == item.task_name and 
            r['Room'] == item.room_name and
            r['Date'] == item.date and 
            r['Done By'] == item.email):
            row_to_delete = i + 2 
            # We don't break immediately to find the LAST occurrence if duplicates exist
            
    if row_to_delete > 0:
        log_ws.delete_rows(row_to_delete) # Actually delete the row since there is no "Status" column in your new definition
        return {"status": "deleted"}
    
    raise HTTPException(status_code=404, detail="Log entry not found")

# --- STATIC FILE SERVING (Must be at the bottom) ---

# Mount the 'assets' folder (or whatever Vite outputs for JS/CSS)
# Vite usually puts assets in a folder named 'assets' inside dist
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

# Catch-all route for SPA (Single Page Application)
# This ensures that if you refresh the page at /some-route, it serves index.html
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    # Check if the requested file actually exists (e.g., favicon.ico)
    file_path = os.path.join("static", full_path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Otherwise, return index.html for Svelte to handle routing
    return FileResponse("static/index.html")

# --- Scheduler (Weekly Email) ---

def send_email_to_user(to_email, grouped_tasks):
    msg = MIMEMultipart()
    msg['Subject'] = "🏠 Your Weekly Chores Summary"
    msg['From'] = f"House Manager <{SENDER_EMAIL}>"
    msg['To'] = to_email
    
    # Building HTML Body with Room Grouping
    sections = ""
    for room, tasks in grouped_tasks.items():
        task_list = ""
        for t in tasks:
            color = "#dc3545" if t['days_until'] <= 0 else "#198754"
            status = "DUE NOW" if t['days_until'] <= 0 else f"In {t['days_until']} days"
            
            task_list += f"""
            <div style="padding: 10px; border-bottom: 1px solid #eee;">
                <span style="font-weight: bold; color: #333;">{t['task']}</span><br>
                <span style="color: {color}; font-size: 0.9em; font-weight: bold;">{status}</span> 
                <span style="color: #777; font-size: 0.8em;">(Target: {t['target_day']})</span>
            </div>
            """
        
        sections += f"""
        <div style="margin-bottom: 20px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
            <div style="background-color: #f8f9fa; padding: 10px; font-weight: bold; border-bottom: 1px solid #ddd;">
                📍 {room}
            </div>
            {task_list}
        </div>
        """

    body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #0d6efd;">Chore Checklist</h2>
            <p>Hi! Here are the tasks assigned to you that are due this week:</p>
            {sections}
            <p style="font-size: 0.8em; color: #999; margin-top: 30px;">
                This is an automated reminder from your House Manager App.
            </p>
        </body>
    </html>
    """
    
    msg.attach(MIMEText(body, 'html'))

    try:
        # Use with to ensure the connection is closed even if it fails
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls() # Secure the connection
            server.login(SENDER_EMAIL, SENDER_PASSWORD) # Use the 16-char App Password
            server.send_message(msg)
            print(f"✅ Successfully sent email to {to_email}")
    except smtplib.SMTPAuthenticationError:
        print(f"❌ AUTH ERROR: Check your App Password")
        print(f"{e}")
    except Exception as e:
        print(f"❌ General Error sending to {to_email}: {e}")
        print(f"{e}")

def send_weekly_emails():
    print("Running Weekly Email Job...")
    all_tasks = tasks_ws.get_all_records()
    all_logs = log_ws.get_all_records()
    
    # Map logs globally first
    # {(Owner, Task, Room): [dates]}
    global_log_map = {}
    for log in all_logs:
        try:
            d = datetime.strptime(log['Date'], "%Y-%m-%d").date()
            k = (log['Done By'].lower(), log['Task'], log['Room'])
            if k not in global_log_map: global_log_map[k] = []
            global_log_map[k].append(d)
        except: continue

    # Group tasks by owner
    tasks_by_owner = {}
    for t in all_tasks:
        o = t['Owner'].strip().lower()
        if not '@' in o: continue
        if o not in tasks_by_owner: tasks_by_owner[o] = []
        tasks_by_owner[o].append(t)
    
    tasks_for_all = [t for t in all_tasks if t['Owner'].strip().lower() == 'all' ]

    for owner in tasks_by_owner:
        tasks_by_owner[owner].extend(tasks_for_all)
    

    # Process each owner
    for owner, tasks in tasks_by_owner.items():
        due_items = []
        for t in tasks:

            status = calculate_due_status(t, global_log_map)
            if status['is_due']:
                due_items.append(status)

        if due_items:
            # Group the due items by room for the email
            email_groups = {}
            for item in due_items:
                room = item['room']
                if room not in email_groups: email_groups[room] = []
                email_groups[room].append(item)
            
            send_email_to_user(owner, email_groups)

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_weekly_emails, 'cron', day_of_week='mon', hour=8)
    scheduler.start()

start_scheduler()