
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import pandas as pd
import os
import matplotlib.pyplot as plt
import json
from datetime import datetime, time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open("Finance Bot").sheet1

import os
TOKEN = os.getenv("TOKEN")
CONFIG_FILE = "config.json"

# =====================
# INIT CONFIG
# =====================
if not os.path.exists(CONFIG_FILE):
    config = {"income": 0, "budget": {}}
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)

# =====================
# HELPERS
# =====================
def load_config():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f)

def get_file():
    now = datetime.now()
    return f"finance_{now.year}_{now.month}.csv"

def ensure_file():
    file = get_file()
    if not os.path.exists(file):
        df = pd.DataFrame(columns=["kategori", "jumlah"])
        df.to_csv(file, index=False)
    return file

def parse_amount(text):
    text = text.lower()
    if "rb" in text:
        return int(text.replace("rb", "")) * 1000
    if "jt" in text:
        return int(text.replace("jt", "")) * 1000000
    if "k" in text:
        return int(text.replace("k", "")) * 1000
    return int(text)

# =====================
# COMMANDS
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot aktif! ketik /help")

    # set reminder harian jam 20:00
    context.job_queue.run_daily(reminder, time=time(20, 0), chat_id=update.effective_chat.id)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📌 COMMAND:
/setincome 10000000
/setbudget makan 2000000
/expense makan 50000
/saldo
/reset
/report
/report 2026-04

💬 Bisa juga:
makan 25rb
kopi 20k
"""
    await update.message.reply_text(text)

async def setincome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cfg = load_config()
    cfg["income"] = int(context.args[0])
    save_config(cfg)
    await update.message.reply_text("Pemasukan diset!")

async def setbudget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kategori = context.args[0]
    jumlah = int(context.args[1])

    cfg = load_config()
    cfg["budget"][kategori] = jumlah
    save_config(cfg)

    await update.message.reply_text(f"Budget {kategori} = {jumlah}")

async def expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kategori = context.args[0]
    jumlah = int(context.args[1])

    file = ensure_file()
    df = pd.read_csv(file)
    df.loc[len(df)] = [kategori, jumlah]
    df.to_csv(file, index=False)
    sheet.append_row([
    str(datetime.now()),
    kategori,
    jumlah
    ])
    cfg = load_config()
    used = df[df["kategori"] == kategori]["jumlah"].sum()
    budget = cfg["budget"].get(kategori, 0)
    sisa = budget - used

    if sisa < 0:
        msg = f"⚠️ OVER BUDGET {kategori}! ({sisa})"
    else:
        msg = f"Sisa {kategori}: {sisa}"

    await update.message.reply_text(msg)

async def saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = ensure_file()
    df = pd.read_csv(file)
    cfg = load_config()

    text = "📊 Sisa Budget:"


    for k, b in cfg["budget"].items():
        used = df[df["kategori"] == k]["jumlah"].sum()
        sisa = b - used
        text += f"{k}: {sisa}"

    await update.message.reply_text(text)

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        file = f"finance_{context.args[0].replace('-', '_')}.csv"
    else:
        file = ensure_file()

    if not os.path.exists(file):
        await update.message.reply_text("Data tidak ada")
        return

    df = pd.read_csv(file)
    summary = df.groupby("kategori").sum()

    summary.plot(kind='bar')
    plt.savefig("report.png")
    plt.close()

    text = "📈 Report:"
    for i, row in summary.iterrows():
        text += f"{i}: {row['jumlah']}"

    await update.message.reply_text(text)
    await update.message.reply_photo(photo=open("report.png", "rb"))

# =====================
# FREE TEXT INPUT
# =====================
async def free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        parts = text.split()
        kategori = parts[0]
        jumlah = parse_amount(parts[1])

        file = ensure_file()
        df = pd.read_csv(file)
        df.loc[len(df)] = [kategori, jumlah]
        df.to_csv(file, index=False)
        
        sheet.append_row([
        str(datetime.now()),
        kategori,
        jumlah
        ])
        
        await update.message.reply_text(f"Tercatat: {kategori} {jumlah}")
    except:
        pass

# =====================
# REMINDER
# =====================
async def reminder(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=context.job.chat_id, text="Jangan lupa catat pengeluaran hari ini 💸")

# =====================
# RESET MANUAL
# =====================
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # hapus file transaksi
    file = get_file()
    if os.path.exists(file):
        os.remove(file)

    ensure_file()

    # reset config (budget + income)
    cfg = {
        "income": 0,
        "budget": {}
    }
    save_config(cfg)

    await update.message.reply_text("Semua data bulan ini sudah di-reset (budget & transaksi) ✅")
    
    
# =====================
# RUN BOT
# =====================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("setincome", setincome))
app.add_handler(CommandHandler("setbudget", setbudget))
app.add_handler(CommandHandler("expense", expense))
app.add_handler(CommandHandler("saldo", saldo))
app.add_handler(CommandHandler("report", report))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, free_text))
app.add_handler(CommandHandler("reset", reset))

app.run_polling()
