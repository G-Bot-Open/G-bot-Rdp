import os
import time
import threading
import zipfile
import io
import requests
import telebot
from flask import Flask

# ===== DEBUG: Check if env vars are set =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

print(f"TELEGRAM_TOKEN = {TELEGRAM_TOKEN}")
print(f"GITHUB_TOKEN (first 10 chars) = {GITHUB_TOKEN[:10] if GITHUB_TOKEN else 'None'}")

if not TELEGRAM_TOKEN or ":" not in TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN is missing or invalid (must contain a colon)")

if not GITHUB_TOKEN:
    raise ValueError("❌ GITHUB_TOKEN is missing")

# ===== CONFIG =====
REPO_OWNER = "G-Bot-Open"
REPO_NAME = "G-bot-Rdp"
WORKFLOW_ID = "rdp.yml"

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ===== GITHUB API FUNCTIONS =====

def trigger_workflow(password):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{WORKFLOW_ID}/dispatches"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {GITHUB_TOKEN}"
    }
    payload = {
        "ref": "main",
        "inputs": {
            "password": password
        }
    }
    r = requests.post(url, headers=headers, json=payload)
    return r.status_code == 204

def get_latest_ip():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?status=success&per_page=1"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers).json()
    if resp.get("total_count", 0) == 0:
        return None
    run = resp["workflow_runs"][0]
    logs_url = run.get("logs_url")
    if not logs_url:
        return None
    logs_resp = requests.get(logs_url, headers=headers, allow_redirects=True)
    if logs_resp.status_code != 200:
        return None
    with zipfile.ZipFile(io.BytesIO(logs_resp.content)) as z:
        for fname in z.namelist():
            if fname.endswith(".txt"):
                with z.open(fname) as f:
                    content = f.read().decode('utf-8', errors='ignore')
                    for line in content.split('\n'):
                        if "IP: " in line and "100." in line:
                            return line.split("IP:")[-1].strip()
    return None

# ===== TELEGRAM COMMANDS =====

@bot.message_handler(commands=['start', 'help'])
def send_help(msg):
    bot.reply_to(msg, 
        "🔥 Welcome to RDP Bot!\n\n"
        "/newrdp <password> - Create new RDP session\n"
        "/status - Check active workflow\n"
        "/stop - Cancel current session\n"
        "/help - Show this"
    )

@bot.message_handler(commands=['newrdp'])
def new_rdp(msg):
    parts = msg.text.split()
    if len(parts) < 2:
        bot.reply_to(msg, "❌ Usage: /newrdp <password>")
        return
    password = parts[1]
    bot.reply_to(msg, "⏳ Creating RDP session... please wait 1-2 minutes.")
    
    if not trigger_workflow(password):
        bot.reply_to(msg, "❌ Failed to trigger workflow. Check GitHub token.")
        return

    time.sleep(60)  # wait for runner to start
    ip = None
    for _ in range(10):  # max 100 seconds
        ip = get_latest_ip()
        if ip:
            break
        time.sleep(10)
    
    if ip:
        reply = (
            f"✅ RDP Ready!\n\n"
            f"🌐 IP: {ip}\n"
            f"👤 Username: runneradmin\n"
            f"🔑 Password: {password}\n\n"
            f"⏳ Active for ~6 hours.\n"
            f"❌ Use /stop to cancel."
        )
        bot.reply_to(msg, reply)
    else:
        bot.reply_to(msg, "❌ Could not fetch IP. Check GitHub Actions logs.")

@bot.message_handler(commands=['status'])
def status(msg):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?per_page=1"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers).json()
    if r.get("total_count", 0) == 0:
        bot.reply_to(msg, "❌ No workflow runs found.")
        return
    run = r["workflow_runs"][0]
    status_text = f"Run #{run['id']}\nStatus: {run['status']} {run.get('conclusion', '')}\n{run['html_url']}"
    bot.reply_to(msg, status_text)

@bot.message_handler(commands=['stop'])
def stop(msg):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?status=in_progress&per_page=1"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers).json()
    if r.get("total_count", 0) == 0:
        bot.reply_to(msg, "❌ No active workflow to cancel.")
        return
    run_id = r["workflow_runs"][0]["id"]
    cancel_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs/{run_id}/cancel"
    resp = requests.post(cancel_url, headers=headers)
    if resp.status_code == 202:
        bot.reply_to(msg, f"✅ Workflow #{run_id} cancelled. VM will terminate shortly.")
    else:
        bot.reply_to(msg, "❌ Failed to cancel workflow.")

# ===== FLASK KEEP-ALIVE =====

@app.route('/')
def index():
    return "Bot is running!"

# ===== MAIN =====
if __name__ == "__main__":
    # Start bot polling in background thread
    threading.Thread(target=bot.polling, kwargs={'none_stop': True, 'interval': 1}).start()
    # Run Flask server
    app.run(host='0.0.0.0', port=8080)    # We'll use a hack: when the workflow runs, it prints the IP in the logs.
    # So we can fetch the logs archive and extract the IP.
    logs_url = run["logs_url"]
    logs_resp = requests.get(logs_url, headers=headers, allow_redirects=True)
    if logs_resp.status_code == 200:
        # logs_resp.content is a zip file; we can extract in memory and find the IP.
        import zipfile
        import io
        with zipfile.ZipFile(io.BytesIO(logs_resp.content)) as z:
            for file in z.namelist():
                if file.endswith(".txt"):
                    with z.open(file) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        # Look for "IP: 100."
                        lines = content.split('\n')
                        for line in lines:
                            if "IP: 100." in line:
                                ip = line.split("IP:")[-1].strip()
                                return ip
    return None

# But this is complex; we can also read the "Display Connection Details" step output.
# Actually we can store the IP in a file artifact? That's extra.
# For simplicity, we'll rely on the bot to fetch the IP from the logs.

def get_latest_ip():
    # Fetch the latest successful run and extract IP from its logs
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?status=success&per_page=1"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers).json()
    if resp["total_count"] == 0:
        return None
    run = resp["workflow_runs"][0]
    logs_url = run["logs_url"]
    logs_resp = requests.get(logs_url, headers=headers, allow_redirects=True)
    if logs_resp.status_code == 200:
        import zipfile, io
        with zipfile.ZipFile(io.BytesIO(logs_resp.content)) as z:
            for file in z.namelist():
                if file.endswith(".txt"):
                    with z.open(file) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        lines = content.split('\n')
                        for line in lines:
                            if "IP: " in line and "100." in line:
                                ip = line.split("IP:")[-1].strip()
                                return ip
    return None

# ===== TELEGRAM COMMANDS =====

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🔥 Welcome to RDP Bot!\n\nCommands:\n/newrdp <password> - Create new RDP session with custom password\n/status - Check active session\n/stop - Cancel active session\n/help - Show this")

@bot.message_handler(commands=['newrdp'])
def new_rdp(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Usage: /newrdp <password>")
        return
    password = parts[1]
    # Trigger workflow
    bot.reply_to(message, "⏳ Creating RDP session... Please wait up to 2 minutes.")
    success = trigger_workflow(password)
    if not success:
        bot.reply_to(message, "❌ Failed to trigger workflow. Check GitHub token.")
        return
    # Wait and poll for IP
    time.sleep(60)  # give time for runner to start
    ip = None
    for attempt in range(10):  # 10 attempts, 10 seconds each = 100s
        ip = get_latest_ip()
        if ip:
            break
        time.sleep(10)
    if ip:
        reply = f"✅ RDP Ready!\n\n🌐 IP: {ip}\n👤 User: runneradmin\n🔑 Pass: {password}\n\n⏳ Active for ~6 hours."
        bot.reply_to(message, reply)
    else:
        bot.reply_to(message, "❌ Could not get IP. Workflow may still be running. Check GitHub Actions.")

@bot.message_handler(commands=['status'])
def status(message):
    # Check latest run status
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?per_page=1"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers).json()
    if resp["total_count"] == 0:
        bot.reply_to(message, "❌ No recent workflow runs.")
        return
    run = resp["workflow_runs"][0]
    status_str = run["status"] + (" (" + run["conclusion"] + ")" if run["conclusion"] else "")
    reply = f"🔄 Latest run: #{run['id']}\nStatus: {status_str}\nURL: {run['html_url']}"
    bot.reply_to(message, reply)

@bot.message_handler(commands=['stop'])
def stop_rdp(message):
    # Cancel the current in-progress run
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?status=in_progress&per_page=1"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers).json()
    if resp["total_count"] == 0:
        bot.reply_to(message, "❌ No active workflow to stop.")
        return
    run_id = resp["workflow_runs"][0]["id"]
    cancel_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs/{run_id}/cancel"
    cancel_resp = requests.post(cancel_url, headers=headers)
    if cancel_resp.status_code == 202:
        bot.reply_to(message, f"✅ Workflow #{run_id} cancelled. VM will be terminated soon.")
    else:
        bot.reply_to(message, "❌ Failed to cancel workflow.")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.reply_to(message, "Commands:\n/newrdp <password> - Create RDP\n/status - Check active session\n/stop - Cancel current session\n/help - This")

# ===== FLASK KEEP-ALIVE =====

@app.route('/')
def index():
    return "Bot is running!"

def run_bot():
    bot.polling(none_stop=True)

if __name__ == '__main__':
    # Start bot in a thread
    threading.Thread(target=run_bot).start()
    # Run Flask on port 8080 (Render uses this)
    app.run(host='0.0.0.0', port=8080)
