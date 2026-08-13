import telebot
import requests
import json
import time
import threading
from flask import Flask, request

# ===== CONFIG =====
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"   # Replace
GITHUB_TOKEN = "YOUR_GITHUB_PAT"             # Replace
REPO_OWNER = "G-Bot-Open"
REPO_NAME = "G-bot-Rdp"
WORKFLOW_ID = "rdp.yml"  # or use filename

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
    response = requests.post(url, headers=headers, json=payload)
    return response.status_code == 204

def get_latest_run_id():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?status=in_progress&per_page=1"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers).json()
    if resp["total_count"] > 0:
        return resp["workflow_runs"][0]["id"]
    return None

def get_run_logs(run_id):
    # Fetch the log output (we can fetch the raw logs via API)
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs/{run_id}/logs"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers, allow_redirects=True)
    # We need to parse the zip? Actually we can get the job steps via API
    # Simpler: use the "Display Connection Details" step output from logs.
    # We'll instead fetch the run details and find the IP from the job steps.
    # But easier: we can use the "Get Tailscale IP" step which writes to stdout.
    # We'll use the logs API to get the entire log and grep.
    if resp.status_code == 200:
        # The logs are in a zip; we need to extract or we can use the job steps API.
        # Let's use the jobs API to get step outputs (not available directly).
        # Alternative: We can let the bot wait for a fixed time and then query the run status.
        pass
    return None

# We'll implement a polling mechanism: trigger workflow, wait for completion, then fetch IP from the run.

def get_latest_successful_run_ip():
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/actions/runs?status=success&per_page=1"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    resp = requests.get(url, headers=headers).json()
    if resp["total_count"] == 0:
        return None
    run = resp["workflow_runs"][0]
    # Get jobs for this run
    jobs_url = run["jobs_url"]
    jobs_resp = requests.get(jobs_url, headers=headers).json()
    # Find step output from "Get Tailscale IP" step
    for job in jobs_resp["jobs"]:
        for step in job["steps"]:
            if step["name"] == "Get Tailscale IP" and step["status"] == "completed":
                # The output is in the logs; we can use the run logs URL
                # Let's fetch the logs for this job
                log_url = step["logs_url"]  # actually this might not exist
                # Simpler: we can parse the workflow run's annotations or use the "Display Connection Details" step
                pass
    # We'll use a hack: when the workflow runs, it prints the IP in the logs.
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
