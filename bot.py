import sqlite3
import pandas as pd
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters
)
import os

TOKEN = os.getenv("BOT_TOKEN")

SELECT_PROJECT, HOURS, DESC = range(3)

# DATABASE
conn = sqlite3.connect("data.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY,
name TEXT,
role TEXT
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


# ---------------- UTILITY ----------------

def get_user(user_id):
    res = c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    return res.fetchone()


def is_admin(user_id):
    user = get_user(user_id)
    return user and user[2] == "admin"


def get_projects():
    res = c.execute("SELECT name FROM projects")
    return [r[0] for r in res.fetchall()]


# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = get_user(update.message.from_user.id)

    if not user:
        await update.message.reply_text(
            "Non sei autorizzato.\nInvia il tuo ID all'amministratore:\n"
            f"{update.message.from_user.id}"
        )
        return

    text = "Timesheet Bot\n\n"

    text += "/ore inserisci ore\n"
    text += "/projects lista progetti\n"
    text += "/report report mese\n"
    text += "/export export csv\n"

    if user[2] == "admin":
        text += "\nComandi admin:\n"
        text += "/adduser id nome ruolo\n"
        text += "/addproject nome\n"

    await update.message.reply_text(text)


# ---------------- USER ----------------

async def adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.message.from_user.id):
        return

    try:
        user_id = int(context.args[0])
        name = context.args[1]
        role = context.args[2]
    except:
        await update.message.reply_text(
            "/adduser ID nome ruolo(admin/user)"
        )
        return

    c.execute(
        "INSERT OR REPLACE INTO users VALUES(?,?,?)",
        (user_id, name, role)
    )

    conn.commit()

    await update.message.reply_text("Utente salvato")


# ---------------- PROJECTS ----------------

async def addproject(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.message.from_user.id):
        return

    name = " ".join(context.args)

    c.execute(
        "INSERT INTO projects(name) VALUES(?)",
        (name,)
    )

    conn.commit()

    await update.message.reply_text("Progetto aggiunto")


async def projects(update: Update, context: ContextTypes.DEFAULT_TYPE):

    projects = get_projects()

    text = "Progetti:\n"

    for p in projects:
        text += f"- {p}\n"

    await update.message.reply_text(text)


# ---------------- ORE ----------------

async def ore(update: Update, context: ContextTypes.DEFAULT_TYPE):

    projects = get_projects()

    keyboard = []

    for p in projects:
        keyboard.append(
            [InlineKeyboardButton(p, callback_data=p)]
        )

    await update.message.reply_text(
        "Seleziona progetto",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return SELECT_PROJECT


async def project_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    context.user_data["project"] = query.data

    await query.edit_message_text("Quante ore?")

    return HOURS


async def hours(update: Update, context: ContextTypes.DEFAULT_TYPE):

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
        "INSERT INTO hours(date,user,project,hours,description) VALUES(?,?,?,?,?)",
        (date, user, project, hours, description)
    )

    conn.commit()

    await update.message.reply_text("Ore registrate")

    return ConversationHandler.END


# ---------------- REPORT ----------------

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if context.args:
        month = context.args[0]
    else:
        month = datetime.now().strftime("%Y-%m")

    df = pd.read_sql_query("SELECT * FROM hours", conn)

    df = df[df["date"].str.startswith(month)]

    proj = df.groupby("project")["hours"].sum()
    user = df.groupby("user")["hours"].sum()

    text = f"Report {month}\n\n"

    text += "Per progetto\n"

    for p, h in proj.items():
        text += f"{p}: {h}\n"

    text += "\nPer utente\n"

    for u, h in user.items():
        text += f"{u}: {h}\n"

    await update.message.reply_text(text)


# ---------------- EXPORT ----------------

async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):

    df = pd.read_sql_query("SELECT * FROM hours", conn)

    if context.args:
        project = " ".join(context.args)
        df = df[df["project"] == project]

    file = "export.csv"

    df.to_csv(file, index=False)

    await update.message.reply_document(open(file, "rb"))


async def export_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    df = pd.read_sql_query("SELECT * FROM hours", conn)

    file = "export.xlsx"

    df.to_excel(file, index=False)

    await update.message.reply_document(open(file, "rb"))


# ---------------- BACKUP ----------------

async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_document(open("data.db", "rb"))


# ---------------- BOT ----------------

app = ApplicationBuilder().token(TOKEN).build()

conv = ConversationHandler(
    entry_points=[CommandHandler("ore", ore)],
    states={
        SELECT_PROJECT: [CallbackQueryHandler(project_selected)],
        HOURS: [MessageHandler(filters.TEXT, hours)],
        DESC: [MessageHandler(filters.TEXT, desc)],
    },
    fallbacks=[]
)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("adduser", adduser))
app.add_handler(CommandHandler("addproject", addproject))
app.add_handler(CommandHandler("projects", projects))
app.add_handler(CommandHandler("report", report))
app.add_handler(CommandHandler("export", export))
app.add_handler(CommandHandler("exportexcel", export_excel))
app.add_handler(CommandHandler("backup", backup))

app.add_handler(conv)

print("Bot avviato")

app.run_polling()
