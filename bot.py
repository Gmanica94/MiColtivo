import sqlite3
import pandas as pd
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
import os

TOKEN = os.getenv("BOT_TOKEN")

# Stati conversazione
PROGETTO, ORE, DESC = range(3)

# Database
conn = sqlite3.connect("timesheet.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
username TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS projects(
id INTEGER PRIMARY KEY AUTOINCREMENT,
name TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS hours(
id INTEGER PRIMARY KEY AUTOINCREMENT,
date TEXT,
user TEXT,
project TEXT,
hours REAL,
description TEXT
)
""")

conn.commit()

# ---------- UTIL ----------

def is_user_allowed(user_id):
    res = c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    return res.fetchone() is not None


def get_projects():
    res = c.execute("SELECT name FROM projects")
    return [r[0] for r in res.fetchall()]


# ---------- COMANDI ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    if not is_user_allowed(user.id):
        await update.message.reply_text(
            f"Utente non autorizzato.\nInvia questo ID all'amministratore:\n{user.id}"
        )
        return

    await update.message.reply_text(
        "Bot Timesheet\n\n"
        "/ore inserisci ore\n"
        "/progetti lista progetti\n"
        "/report mese\n"
        "/export export csv"
    )


# ---------- GESTIONE UTENTI ----------

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if len(context.args) < 2:
        await update.message.reply_text("/adduser USERID username")
        return

    user_id = int(context.args[0])
    username = context.args[1]

    c.execute(
        "INSERT OR IGNORE INTO users VALUES (?,?)",
        (user_id, username)
    )
    conn.commit()

    await update.message.reply_text("Utente aggiunto")


# ---------- PROGETTI ----------

async def add_project(update: Update, context: ContextTypes.DEFAULT_TYPE):

    name = " ".join(context.args)

    c.execute(
        "INSERT INTO projects(name) VALUES (?)",
        (name,)
    )
    conn.commit()

    await update.message.reply_text("Progetto aggiunto")


async def list_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):

    projects = get_projects()

    if not projects:
        await update.message.reply_text("Nessun progetto")
        return

    text = "Progetti:\n"
    for p in projects:
        text += f"- {p}\n"

    await update.message.reply_text(text)


# ---------- INSERIMENTO ORE ----------

async def ore_start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_user_allowed(update.message.from_user.id):
        await update.message.reply_text("Non autorizzato")
        return ConversationHandler.END

    projects = get_projects()

    if not projects:
        await update.message.reply_text("Nessun progetto configurato")
        return ConversationHandler.END

    text = "Seleziona progetto:\n"
    for p in projects:
        text += f"- {p}\n"

    await update.message.reply_text(text)

    return PROGETTO


async def progetto(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["project"] = update.message.text

    await update.message.reply_text("Quante ore?")

    return ORE


async def ore(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["hours"] = update.message.text

    await update.message.reply_text("Descrizione attività")

    return DESC


async def desc(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.message.from_user.username
    project = context.user_data["project"]
    hours = context.user_data["hours"]
    description = update.message.text
    date = datetime.now().strftime("%Y-%m-%d")

    c.execute(
        "INSERT INTO hours(date,user,project,hours,description) VALUES (?,?,?,?,?)",
        (date, user, project, hours, description)
    )
    conn.commit()

    await update.message.reply_text("Ore registrate!")

    return ConversationHandler.END


# ---------- REPORT ----------

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):

    month = datetime.now().strftime("%Y-%m")

    df = pd.read_sql_query("SELECT * FROM hours", conn)

    df = df[df["date"].str.startswith(month)]

    report = df.groupby("project")["hours"].sum()

    text = f"Report {month}\n\n"

    for p, h in report.items():
        text += f"{p}: {h} ore\n"

    await update.message.reply_text(text)


# ---------- EXPORT CSV ----------

async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):

    df = pd.read_sql_query("SELECT * FROM hours", conn)

    if len(context.args) > 0:
        project = " ".join(context.args)
        df = df[df["project"] == project]

    file = "export.csv"

    df.to_csv(file, index=False)

    await update.message.reply_document(open(file, "rb"))


# ---------- BOT ----------

app = ApplicationBuilder().token(TOKEN).build()

conv = ConversationHandler(
    entry_points=[CommandHandler("ore", ore_start)],
    states={
        PROGETTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, progetto)],
        ORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ore)],
        DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, desc)],
    },
    fallbacks=[]
)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("adduser", add_user))
app.add_handler(CommandHandler("addproject", add_project))
app.add_handler(CommandHandler("progetti", list_projects))
app.add_handler(CommandHandler("report", report))
app.add_handler(CommandHandler("export", export))
app.add_handler(conv)

print("Bot avviato")

app.run_polling()
