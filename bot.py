import os
import time
import threading
import zipfile
import io
import requests
import telebot
from flask import Flask

# ===== HARDCODED TOKENS (Tu yahan apne daal) =====
TELEGRAM_TOKEN = "8846023281:AAF15F--5wT-xQc1HFzD0hIhQcKXXVX25xc"   # <-- Apna Telegram bot token
GITHUB_TOKEN = "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"  # <-- Apna GitHub PAT

# ===== CONFIG =====
REPO_OWNER = "G-Bot-Open"
REPO_NAME = "G-bot-Rdp"
WORKFLOW_ID = "rdp.yml"

# Validate tokens
if ":" not in TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN must contain a colon")
if not GITHUB_TOKEN:
    raise ValueError("❌ GITHUB_TOKEN is empty")

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

    time.sleep(60)
    ip = None
    for _ in range(10):
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

@app.route('/')
def index():
    return "Bot is running!"

if __name__ == "__main__":
    threading.Thread(target=bot.polling, kwargs={'none_stop': True, 'interval': 1}).start()
    app.run(host='0.0.0.0', port=8080)d = resp["workflow_runs"][0]["id"]
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
