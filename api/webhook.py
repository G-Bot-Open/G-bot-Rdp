import os
import requests
import json
import time
import zipfile
import io
from flask import Flask, request, Response
import telebot

# ---------- Environment ----------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_OWNER = "G-Bot-Open"
REPO_NAME = "G-bot-Rdp"
WORKFLOW_ID = "rdp.yml"

# ---------- Validation ----------
if not TELEGRAM_TOKEN or ":" not in TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN missing or invalid")
if not GITHUB_TOKEN:
    raise ValueError("GITHUB_TOKEN missing")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)

# ---------- GitHub helpers ----------
def trigger_workflow(password):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/workflows/{WORKFLOW_ID}/dispatches"
    headers = {"Accept": "application/vnd.github.v3+json", "Authorization": f"token {GITHUB_TOKEN}"}
    payload = {"ref": "main", "inputs": {"password": password}}
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

# ---------- Telegram Handlers ----------
@bot.message_handler(commands=['start', 'help'])
def send_help(msg):
    bot.reply_to(msg, "🔥 RDP Bot\n/newrdp <pass> - create\n/status - check\n/stop - cancel")

@bot.message_handler(commands=['newrdp'])
def new_rdp(msg):
    parts = msg.text.split()
    if len(parts) < 2:
        bot.reply_to(msg, "❌ Usage: /newrdp <password>")
        return
    password = parts[1]
    bot.reply_to(msg, "⏳ Creating RDP... wait 1-2 min.")
    if not trigger_workflow(password):
        bot.reply_to(msg, "❌ Workflow trigger failed.")
        return
    time.sleep(60)
    ip = None
    for _ in range(10):
        ip = get_latest_ip()
        if ip:
            break
        time.sleep(10)
    if ip:
        bot.reply_to(msg, f"✅ RDP Ready!\nIP: {ip}\nUser: runneradmin\nPass: {password}\n~6h active.")
    else:
        bot.reply_to(msg, "❌ IP not found. Check Actions logs.")

@bot.message_handler(commands=['status'])
def status(msg):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?per_page=1"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers).json()
    if r.get("total_count", 0) == 0:
        bot.reply_to(msg, "No runs.")
        return
    run = r["workflow_runs"][0]
    bot.reply_to(msg, f"Run #{run['id']}: {run['status']} {run.get('conclusion','')}")

@bot.message_handler(commands=['stop'])
def stop(msg):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?status=in_progress&per_page=1"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers).json()
    if r.get("total_count", 0) == 0:
        bot.reply_to(msg, "No active run.")
        return
    run_id = r["workflow_runs"][0]["id"]
    cancel_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs/{run_id}/cancel"
    resp = requests.post(cancel_url, headers=headers)
    if resp.status_code == 202:
        bot.reply_to(msg, f"✅ Cancelled #{run_id}.")
    else:
        bot.reply_to(msg, "❌ Cancel failed.")

# ---------- Webhook Endpoint ----------
@app.route('/', methods=['GET'])
def index():
    return "Bot is running on Vercel!"

@app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('UTF-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return Response('ok', status=200)
    except Exception as e:
        print(f"Webhook error: {e}")
        return Response('error', status=500)

# ---------- Set webhook (will run at import) ----------
def set_webhook():
    webhook_url = f"https://{os.getenv('VERCEL_URL', '')}/{TELEGRAM_TOKEN}"
    if not webhook_url.startswith("https://"):
        webhook_url = "https://" + webhook_url
    try:
        bot.remove_webhook()
        resp = bot.set_webhook(url=webhook_url)
        print(f"Webhook set to {webhook_url} - result: {resp}")
    except Exception as e:
        print(f"Webhook set failed: {e}")

# Only run on serverless environment (not local)
if os.getenv('VERCEL_URL'):
    set_webhook()
else:
    print("No VERCEL_URL, skipping webhook setup")
