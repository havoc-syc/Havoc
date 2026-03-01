import os
import requests
import pandas as pd
import time
from datetime import datetime
from telegram import Bot

# ---------------------------
# Environment variables
# ---------------------------
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_KEY = os.getenv("API_KEY")  # TwelveData API key

bot = Bot(token=TOKEN)

# ---------------------------
# Settings
# ---------------------------
pairs = ["EUR/USD", "USD/JPY", "GBP/USD"]
trade_amount = 0.50  # $0.50 per trade
expiration = "2 Minutes"
max_signals = 3
max_losses = 2
confidence_threshold = 75  # %

# Session & daily tracking
session_signals = 0
session_losses = 0
daily_wins = 0
daily_losses = 0
last_session_date = None
last_session_period = None

# ---------------------------
# Helper functions
# ---------------------------
def in_session():
    hour = datetime.now().hour
    return (8 <= hour < 12) or (14 <= hour < 18)

def get_data(pair):
    url = f"https://api.twelvedata.com/time_series?symbol={pair}&interval=1min&apikey={API_KEY}"
    r = requests.get(url).json()
    if "values" not in r:
        return None
    df = pd.DataFrame(r['values']).astype(float)
    return df

def calculate_confidence(df, direction):
    score = 0
    ema9 = df['close'].ewm(span=9).mean().iloc[0]
    ema21 = df['close'].ewm(span=21).mean().iloc[0]
    if direction == "BUY" and ema9 > ema21:
        score += 20
    elif direction == "SELL" and ema9 < ema21:
        score += 20
    # Structure
    if direction == "BUY" and df['low'].iloc[1] < df['low'].iloc[0]:
        score += 20
    elif direction == "SELL" and df['high'].iloc[1] > df['high'].iloc[0]:
        score += 20
    # Candle momentum
    if direction == "BUY" and df['close'].iloc[0] > df['open'].iloc[0]:
        score += 20
    elif direction == "SELL" and df['close'].iloc[0] < df['open'].iloc[0]:
        score += 20
    # Volume
    if direction == "BUY" and df['volume'].iloc[0] > df['volume'].iloc[1]:
        score += 20
    elif direction == "SELL" and df['volume'].iloc[0] < df['volume'].iloc[1]:
        score += 20
    return score

def send_warning(pair, direction):
    message = f"⚠️ PREPARE TO ENTER\nPair: {pair}\nDirection: {direction}\nEntry in 45 seconds"
    bot.send_message(chat_id=CHAT_ID, text=message)

def send_signal(pair, direction, confidence):
    message = f"""👑👑👑👑👑👑
SIGNAL

💱 Pair: {pair} (OTC)
⏳ Expiration: {expiration}
💰 Trade Amount: ${trade_amount}
⬆️ Direction: {direction}

🔍 Analysis:
• EMA 9 {'above' if direction=='BUY' else 'below'} EMA 21
• {'Higher low' if direction=='BUY' else 'Lower high'} forming
• {'Bullish' if direction=='BUY' else 'Bearish'} candle
• Volume {'increasing' if direction=='BUY' else 'decreasing'}

🎯 Confidence: {confidence}%"""
    bot.send_message(chat_id=CHAT_ID, text=message)

# ---------------------------
# Telegram command handlers
# ---------------------------
def handle_command(command):
    global session_losses, session_signals, daily_wins, daily_losses
    if command == "/win":
        session_signals += 1
        daily_wins += 1
        bot.send_message(chat_id=CHAT_ID, text="✅ Win recorded")
    elif command == "/loss":
        session_losses += 1
        daily_losses += 1
        bot.send_message(chat_id=CHAT_ID, text="❌ Loss recorded")
        if session_losses >= max_losses:
            bot.send_message(chat_id=CHAT_ID, text="🛑 Session stopped. Too many losses.")
    elif command == "/stats":
        total_trades = session_signals + session_losses
        win_rate = (session_signals / total_trades * 100) if total_trades > 0 else 0
        bot.send_message(chat_id=CHAT_ID, text=f"📊 SESSION STATS\nWins: {session_signals}\nLosses: {session_losses}\nWin Rate: {win_rate:.1f}%\nTrading Status: {'ACTIVE' if session_losses < max_losses else 'STOPPED'}")

# ---------------------------
# Startup message
# ---------------------------
now = datetime.now()
hour = now.hour
if 8 <= hour < 12:
    session_name = 'morning'
elif 14 <= hour < 18:
    session_name = 'evening'
else:
    session_name = 'off-session'

bot.send_message(chat_id=CHAT_ID, text=f"""🤖 Bot started!
Current session: {session_name}
Max signals per session: {max_signals}
Trade amount: ${trade_amount}
Expiration: {expiration}
Confidence threshold: {confidence_threshold}%
Use /win or /loss to record results.
Use /stats to check session stats.
Happy trading! 📈""")

# ---------------------------
# Main loop
# ---------------------------
while True:
    now = datetime.now()
    hour = now.hour

    # Determine current session
    if 8 <= hour < 12:
        current_session = 'morning'
    elif 14 <= hour < 18:
        current_session = 'evening'
    else:
        current_session = None

    # Reset session counters at start of new session
    if current_session and (current_session != last_session_period or now.date() != last_session_date):
        session_signals = 0
        session_losses = 0
        last_session_date = now.date()
        last_session_period = current_session
        bot.send_message(chat_id=CHAT_ID, text=f"🌞 New {current_session} session started. Counters reset.")

    # Daily summary at 18:00
    if hour == 18 and now.minute == 0 and last_session_period != 'after_summary':
        total_trades = daily_wins + daily_losses
        win_rate = (daily_wins / total_trades * 100) if total_trades > 0 else 0
        bot.send_message(chat_id=CHAT_ID, text=f"📊 DAILY SUMMARY\nWins: {daily_wins}\nLosses: {daily_losses}\nWin Rate: {win_rate:.1f}%")
        daily_wins = 0
        daily_losses = 0
        last_session_period = 'after_summary'

    # Only scan if inside session and limits not reached
    if current_session and session_signals < max_signals and session_losses < max_losses:
        for pair in pairs:
            df = get_data(pair)
            if df is None or len(df) < 2:
                continue

            # Decide direction
            direction = None
            if df['close'].iloc[0] > df['open'].iloc[0] and df['close'].iloc[0] > df['close'].iloc[1]:
                direction = "BUY"
            elif df['close'].iloc[0] < df['open'].iloc[0] and df['close'].iloc[0] < df['close'].iloc[1]:
                direction = "SELL"

            if direction:
                confidence = calculate_confidence(df, direction)
                if confidence >= confidence_threshold:
                    send_warning(pair, direction)
                    time.sleep(45)
                    send_signal(pair, direction, confidence)
                    session_signals += 1

    time.sleep(60)