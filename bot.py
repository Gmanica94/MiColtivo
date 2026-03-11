import sqlite3
import pandas as pd
from datetime import datetime
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("BOT_TOKEN")

# -------- DATABASE --------

conn = sqlite3.connect("data.db", check_same_thread=False)
c = conn.cursor()

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

# -------- USER STATE --------

user_state = {}

# -------- MENU --------

def main_menu():

    keyboard = [

        [InlineKeyboardButton("➕ Inserisci ore", callback_data="insert")],

        [InlineKeyboardButton("📊 Report mese", callback_data="report")],

        [InlineKeyboardButton("📁 Export CSV", callback_data="export")],

        [InlineKeyboardButton("📁 Export Excel", callback_data="excel")],

        [InlineKeyboardButton("✏ Modifica ore", callback_data="edit")],

        [InlineKeyboardButton("❌ Elimina ore", callback_data="delete")]

    ]

    return InlineKeyboardMarkup(keyboard)

# -------- START --------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(

        "Gestione ore progetto",

        reply_markup=main_menu()

    )

# -------- MENU --------

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    action = query.data

    user = query.from_user.id

    if action == "insert":

        projects = c.execute(

            "SELECT name FROM projects"

        ).fetchall()

        keyboard = []

        for p in projects:

            keyboard.append(

                [InlineKeyboardButton(p[0], callback_data=f"project_{p[0]}")]

            )

        await query.edit_message_text(

            "Seleziona progetto",

            reply_markup=InlineKeyboardMarkup(keyboard)

        )

    elif action == "report":

        await report(query)

    elif action == "export":

        await export_csv(query)

    elif action == "excel":

        await export_excel(query)

    elif action == "edit":

        await list_hours(query)

    elif action == "delete":

        await delete_hours(query)

# -------- PROJECT SELECT --------

async def project_select(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    project = query.data.replace("project_", "")

    user = query.from_user.id

    user_state[user] = {

        "step": "hours",

        "project": project

    }

    await query.edit_message_text(

        f"Progetto: {project}\n\n"

        "Quante ore?"

    )

# -------- TEXT INPUT --------

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user.id

    if user not in user_state:

        return

    state = user_state[user]["step"]

    text = update.message.text

    if state == "hours":

        user_state[user]["hours"] = text

        user_state[user]["step"] = "desc"

        await update.message.reply_text(

            "Descrizione attività"

        )

    elif state == "desc":

        user_state[user]["desc"] = text

        user_state[user]["step"] = "date"

        await update.message.reply_text(

            "Data attività (YYYY-MM-DD) oppure scrivi 'oggi'"

        )

    elif state == "date":

        if text == "oggi":

            date = datetime.now().strftime("%Y-%m-%d")

        else:

            date = text

        project = user_state[user]["project"]

        hours = user_state[user]["hours"]

        desc = user_state[user]["desc"]

        username = update.effective_user.username

        c.execute(

            "INSERT INTO hours(date,user,project,hours,description) VALUES(?,?,?,?,?)",

            (date, username, project, hours, desc)

        )

        conn.commit()

        user_state.pop(user)

        await update.message.reply_text(

            "Ore salvate",

            reply_markup=main_menu()

        )

# -------- REPORT --------

async def report(query):

    month = datetime.now().strftime("%Y-%m")

    df = pd.read_sql_query(

        "SELECT * FROM hours",

        conn

    )

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

    await query.edit_message_text(

        text,

        reply_markup=main_menu()

    )

# -------- EXPORT --------

async def export_csv(query):

    df = pd.read_sql_query(

        "SELECT * FROM hours",

        conn

    )

    file = "export.csv"

    df.to_csv(file, index=False)

    await query.message.reply_document(

        open(file, "rb")

    )

async def export_excel(query):

    df = pd.read_sql_query(

        "SELECT * FROM hours",

        conn

    )

    file = "export.xlsx"

    df.to_excel(file, index=False)

    await query.message.reply_document(

        open(file, "rb")

    )

# -------- EDIT / DELETE --------

async def list_hours(query):

    rows = c.execute(

        "SELECT id,date,user,project,hours FROM hours ORDER BY date DESC LIMIT 10"

    ).fetchall()

    text = "Ultime ore registrate\n\n"

    for r in rows:

        text += f"{r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]}h\n"

    await query.edit_message_text(text)

async def delete_hours(query):

    rows = c.execute(

        "SELECT id,date,project,hours FROM hours ORDER BY date DESC LIMIT 10"

    ).fetchall()

    text = "Elimina voce\n\n"

    for r in rows:

        text += f"/del_{r[0]} {r[1]} {r[2]} {r[3]}h\n"

    await query.edit_message_text(text)

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cmd = update.message.text

    id = cmd.replace("/del_", "")

    c.execute(

        "DELETE FROM hours WHERE id=?",

        (id,)

    )

    conn.commit()

    await update.message.reply_text(

        "Voce eliminata",

        reply_markup=main_menu()

    )

# -------- PROJECT --------

async def add_project(update: Update, context: ContextTypes.DEFAULT_TYPE):

    name = " ".join(context.args)

    c.execute(

        "INSERT INTO projects(name) VALUES(?)",

        (name,)

    )

    conn.commit()

    await update.message.reply_text(

        "Progetto aggiunto"

    )

# -------- BOT --------

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))

app.add_handler(CommandHandler("addproject", add_project))

app.add_handler(MessageHandler(filters.Regex(r"^/del_"), delete_command))

app.add_handler(CallbackQueryHandler(project_select, pattern="project_"))

app.add_handler(CallbackQueryHandler(menu))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

print("BOT AVVIATO")

app.run_polling()
