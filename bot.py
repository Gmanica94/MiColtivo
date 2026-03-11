import sqlite3
import pandas as pd
from datetime import datetime
import os

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("BOT_TOKEN")

(
SELECT_PROJECT,
INSERT_HOURS,
INSERT_DESC,
INSERT_DATE,
EDIT_SELECT,
EDIT_FIELD
) = range(6)

# ---------------- DATABASE ----------------

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
    return [x[0] for x in res.fetchall()]

# ---------------- MENU ----------------

def main_menu():

    keyboard = [
        [InlineKeyboardButton("➕ Inserisci ore", callback_data="insert")],
        [InlineKeyboardButton("📊 Report", callback_data="report")],
        [InlineKeyboardButton("📁 Export", callback_data="export")],
        [InlineKeyboardButton("✏ Modifica ore", callback_data="edit")],
        [InlineKeyboardButton("❌ Elimina ore", callback_data="delete")]
    ]

    return InlineKeyboardMarkup(keyboard)

# ---------------- START ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if not get_user(user.id):

        await update.message.reply_text(
            f"Non autorizzato.\nInvia questo ID all'amministratore:\n{user.id}"
        )
        return

    await update.message.reply_text(
        "Gestione Ore Progetti",
        reply_markup=main_menu()
    )

# ---------------- MENU CALLBACK ----------------

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "insert":

        projects = get_projects()

        keyboard = []

        for p in projects:
            keyboard.append([InlineKeyboardButton(p, callback_data=p)])

        await query.edit_message_text(
            "Seleziona progetto",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return SELECT_PROJECT

    if data == "report":

        await send_report(query)

    if data == "export":

        await export_csv(query)

    if data == "edit":

        await list_user_hours(query)

    if data == "delete":

        await delete_hours(query)

# ---------------- INSERIMENTO ----------------

async def select_project(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    context.user_data["project"] = query.data

    await query.edit_message_text("Quante ore?")

    return INSERT_HOURS

async def insert_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["hours"] = update.message.text

    await update.message.reply_text("Descrizione attività")

    return INSERT_DESC

async def insert_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["desc"] = update.message.text

    await update.message.reply_text(
        "Data attività (YYYY-MM-DD) oppure scrivi 'oggi'"
    )

    return INSERT_DATE

async def insert_date(update: Update, context: ContextTypes.DEFAULT_TYPE):

    date = update.message.text

    if date == "oggi":
        date = datetime.now().strftime("%Y-%m-%d")

    user = update.effective_user.username
    project = context.user_data["project"]
    hours = context.user_data["hours"]
    desc = context.user_data["desc"]

    c.execute(
        "INSERT INTO hours(date,user,project,hours,description) VALUES(?,?,?,?,?)",
        (date, user, project, hours, desc)
    )

    conn.commit()

    await update.message.reply_text(
        "Ore salvate",
        reply_markup=main_menu()
    )

    return ConversationHandler.END

# ---------------- REPORT ----------------

async def send_report(query):

    month = datetime.now().strftime("%Y-%m")

    df = pd.read_sql_query("SELECT * FROM hours", conn)

    df = df[df["date"].str.startswith(month)]

    proj = df.groupby("project")["hours"].sum()
    user = df.groupby("user")["hours"].sum()

    text = f"Report {month}\n\n"

    text += "Progetti\n"

    for p, h in proj.items():
        text += f"{p}: {h}h\n"

    text += "\nUtenti\n"

    for u, h in user.items():
        text += f"{u}: {h}h\n"

    await query.edit_message_text(text, reply_markup=main_menu())

# ---------------- EXPORT ----------------

async def export_csv(query):

    df = pd.read_sql_query("SELECT * FROM hours", conn)

    file = "export.csv"

    df.to_csv(file, index=False)

    await query.message.reply_document(open(file, "rb"))

# ---------------- EDIT ----------------

async def list_user_hours(query):

    user = query.from_user.username

    rows = c.execute(
        "SELECT id,date,project,hours FROM hours WHERE user=? ORDER BY date DESC LIMIT 10",
        (user,)
    ).fetchall()

    text = "Ultime ore inserite\n\n"

    for r in rows:
        text += f"{r[0]} | {r[1]} | {r[2]} | {r[3]}h\n"

    text += "\nScrivi /edit ID"

    await query.edit_message_text(text)

# ---------------- DELETE ----------------

async def delete_hours(query):

    user = query.from_user.username

    rows = c.execute(
        "SELECT id,date,project,hours FROM hours WHERE user=? ORDER BY date DESC LIMIT 10",
        (user,)
    ).fetchall()

    text = "Ore eliminabili\n\n"

    for r in rows:
        text += f"/del_{r[0]} {r[1]} {r[2]} {r[3]}h\n"

    await query.edit_message_text(text)

# ---------------- DELETE COMMAND ----------------

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    command = update.message.text

    id = command.replace("/del_", "")

    c.execute("DELETE FROM hours WHERE id=?", (id,))
    conn.commit()

    await update.message.reply_text(
        "Voce eliminata",
        reply_markup=main_menu()
    )

# ---------------- ADMIN ----------------

async def add_project(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    name = " ".join(context.args)

    c.execute(
        "INSERT INTO projects(name) VALUES(?)",
        (name,)
    )

    conn.commit()

    await update.message.reply_text("Progetto aggiunto")

async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    uid = int(context.args[0])
    name = context.args[1]
    role = context.args[2]

    c.execute(
        "INSERT OR REPLACE INTO users VALUES(?,?,?)",
        (uid, name, role)
    )

    conn.commit()

    await update.message.reply_text("Utente salvato")

# ---------------- BOT ----------------

app = ApplicationBuilder().token(TOKEN).build()

conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(menu_callback, pattern="insert")],
    states={
        SELECT_PROJECT: [CallbackQueryHandler(select_project)],
        INSERT_HOURS: [MessageHandler(filters.TEXT, insert_hours)],
        INSERT_DESC: [MessageHandler(filters.TEXT, insert_desc)],
        INSERT_DATE: [MessageHandler(filters.TEXT, insert_date)]
    },
    fallbacks=[]
)

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addproject", add_project))
app.add_handler(CommandHandler("adduser", add_user))
app.add_handler(MessageHandler(filters.Regex(r"^/del_"), delete_command))

app.add_handler(conv)
app.add_handler(CallbackQueryHandler(menu_callback))

print("BOT AVVIATO")

app.run_polling()
