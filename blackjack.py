import telebot
import sqlite3
from datetime import datetime, timezone
import calendar

expecting_session_data = False

def init_db():
    conn = sqlite3.connect('blackjack_tracker.db')
    cursor = conn.cursor()

    # Check if the table already exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                login_time TEXT,
                logoff_time TEXT,
                session_duration REAL,
                total_hands INTEGER,
                total_wins INTEGER,
                total_losses INTEGER,
                highest_win REAL,
                highest_loss REAL,
                base_bet REAL,
                net_pnl REAL
            )
        ''')
        conn.commit()
    
    conn.close()

# Function to insert a new session
def insert_session():
    conn = sqlite3.connect('blackjack_tracker.db')
    cursor = conn.cursor()
    login_time = datetime.now(timezone.utc)
    cursor.execute("INSERT INTO sessions (login_time) VALUES (?)", (login_time,))
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return session_id


# Function to update session data
def update_session(session_id, logoff_time, session_duration, data):
    conn = sqlite3.connect('blackjack_tracker.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE sessions SET
        logoff_time = ?,
        session_duration = ?,
        total_hands = ?,
        total_wins = ?,
        total_losses = ?,
        highest_win = ?,
        highest_loss = ?,
        base_bet = ?,
        net_pnl = ?
        WHERE session_id = ?
    ''', (logoff_time, session_duration, *data, session_id))
    conn.commit()
    conn.close()

# Initialize the database
init_db()

# Bot initialization
TOKEN = '6511079471:AAEzpHV8vvWMELNxrX8F2NMBHd1xX2lgrtE'  # Replace with your token
bot = telebot.TeleBot(TOKEN)

# Global variable to track the current session ID
current_session_id = None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, 'Hello! This is your Blackjack Portfolio Bot.')

@bot.message_handler(commands=['login'])
def handle_login(message):
    global current_session_id
    current_session_id = insert_session()
    bot.reply_to(message, f"Session started. Good Luck! ID: {current_session_id}")

@bot.message_handler(commands=['logoff'])
def handle_logoff(message):
    global current_session_id
    if current_session_id is None:
        bot.reply_to(message, "Please login first.")
    else:
        bot.reply_to(message, "Please enter your session data separated by space (Total Hands, Total Wins, Total Loss, Highest Wins, Highest Loss, Base Bet, Net Cash):")
        global expecting_session_data
        expecting_session_data = True

@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    global current_session_id
    if current_session_id is None:
        bot.reply_to(message, "You have nothing to cancel.")
    else:
        cancel_session(current_session_id)
        current_session_id = None
        bot.reply_to(message, "Your session has been cancelled.")

def cancel_session(session_id):
    conn = sqlite3.connect('blackjack_tracker.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()

# Function to process the session data input from the user
def process_session_data(message):
    global current_session_id
    if current_session_id:
        try:
            data = [int(x) if i < 3 else float(x) for i, x in enumerate(message.text.split())]
            if len(data) != 7:
                raise ValueError("Incorrect number of arguments")

            total_hands, total_wins, total_losses, base_bet = data[:4]

            # Validation: Total wins + total losses must equal total hands
            if total_wins + total_losses != total_hands:
                raise ValueError("Total wins and losses must equal total hands")

            logoff_time = datetime.now(timezone.utc)
            login_time = get_login_time(current_session_id)
            if isinstance(login_time, str):
                login_time = datetime.strptime(login_time, "%Y-%m-%d %H:%M:%S.%f%z")

            session_duration = (logoff_time - login_time).total_seconds() / 3600
            update_session(current_session_id, logoff_time, session_duration, data)
            bot.reply_to(message, "Session data saved successfully.")
            
            current_session_id = None
        except ValueError as e:
            bot.reply_to(message, str(e))


# Function to get the login time of the current session
def get_login_time(session_id):
    conn = sqlite3.connect('blackjack_tracker.db')
    cursor = conn.cursor()
    cursor.execute("SELECT login_time FROM sessions WHERE session_id = ?", (session_id,))
    login_time = cursor.fetchone()[0]
    conn.close()
    return login_time

@bot.message_handler(func=lambda message: current_session_id is not None)
def handle_session_data(message):
    global expecting_session_data, current_session_id
    if current_session_id:
        process_session_data(message)
        expecting_session_data = False

def get_time_of_day(time_str):
    time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S%z").time()
    if time >= datetime.strptime("06:00:00", "%H:%M:%S").time() and time < datetime.strptime("12:00:00", "%H:%M:%S").time():
        return "Morning"
    elif time >= datetime.strptime("12:00:00", "%H:%M:%S").time() and time < datetime.strptime("18:00:00", "%H:%M:%S").time():
        return "Afternoon"
    elif time >= datetime.strptime("18:00:00", "%H:%M:%S").time() and time < datetime.strptime("00:00:00", "%H:%M:%S").time():
        return "Evening"
    else:
        return "Night"

@bot.message_handler(commands=['statistics'])
def statistics(message):
    global current_session_id
    if current_session_id is not None:
        bot.reply_to(message, "Please logoff (/logoff) or cancel (/cancel) the session first.")
    else:
        try:
            conn = sqlite3.connect('blackjack_tracker.db')
            cursor = conn.cursor()

            # Remove incomplete session records
            cursor.execute("DELETE FROM sessions WHERE logoff_time IS NULL OR session_duration IS NULL")
            conn.commit()

            # Fetch complete session data
            cursor.execute("SELECT login_time, logoff_time, total_hands, total_wins, total_losses, base_bet, net_pnl FROM sessions WHERE logoff_time IS NOT NULL")
            sessions = cursor.fetchall()

            # Variables for calculations
            total_hands, total_wins, total_losses, total_net_pnl = 0, 0, 0, 0
            total_duration = 0
            day_wins = {day: 0 for day in calendar.day_name}

            base_bet_counts = {}
            for session in sessions:
                base_bet = session[6]  # Assuming base_bet is the seventh column
                base_bet_counts[base_bet] = base_bet_counts.get(base_bet, 0) + 1

                # Convert the login_time and logoff_time from string to datetime
                login_time = datetime.strptime(session[0], "%Y-%m-%d %H:%M:%S.%f%z")
                logoff_time = datetime.strptime(session[1], "%Y-%m-%d %H:%M:%S.%f%z")
                duration = (logoff_time - login_time).total_seconds() / 3600
                total_duration += duration

                hands, wins, losses, net_pnl = session[2:6]
                total_hands += hands
                total_wins += wins
                total_losses += losses
                total_net_pnl += net_pnl

                day_wins[calendar.day_name[login_time.weekday()]] += net_pnl

            # Calculations
            win_rate = (total_wins / total_hands) * 100 if total_hands else 0
            pnl_per_hand = total_net_pnl / total_hands if total_hands else 0
            pnl_per_session = total_net_pnl / len(sessions) if sessions else 0
            best_base_bet = max(base_bet_counts, key=base_bet_counts.get)

            avg_session_duration = total_duration / len(sessions) if sessions else 0
            best_day = max(day_wins, key=day_wins.get)
            roi = (total_net_pnl / total_hands) * 100 if total_hands else 0

            # Response preparation
            response = (
                f"Total Hands: {total_hands}\n"
                f"Total Wins: {total_wins}\n"
                f"Total Loss: {total_losses}\n"
                f"Win Rate: {win_rate:.2f}%\n"
                "------------\n"
                f"PnL per hand: {pnl_per_hand:.2f}\n"
                f"PnL per session: {pnl_per_session:.2f}\n"
                f"Best Base Bet: {best_base_bet}\n"
                f"Average Session Duration: {avg_session_duration:.2f} hours\n"
                f"Best Day: {best_day}\n"
                f"Return on Investment: {roi:.2f}%\n"
            )

            bot.reply_to(message, response)
        except Exception as e:
            print("Error in /statistics:", e)
            bot.reply_to(message, "An error occurred while processing statistics.")

bot.polling()