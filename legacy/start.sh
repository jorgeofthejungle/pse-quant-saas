#!/bin/bash
# Start all PSE Quant SaaS processes in one container

echo "Starting PSE Quant SaaS..."

# Start scheduler in background
python scheduler.py &
SCHEDULER_PID=$!
echo "Scheduler started (PID $SCHEDULER_PID)"

# Start Discord bot in background
python discord/bot.py &
BOT_PID=$!
echo "Discord bot started (PID $BOT_PID)"

# Start dashboard in foreground (keeps container alive)
python dashboard/app.py
