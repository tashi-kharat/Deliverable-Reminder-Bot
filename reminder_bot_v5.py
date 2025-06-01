import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
from datetime import datetime, timedelta
import re
import dateparser
from dateparser.search import search_dates
import os
import webserver
from zoneinfo import ZoneInfo
import logging

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True  # Needed for reaction events

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

discord_token = os.environ['discordkey']
FRANKFURT_TZ = ZoneInfo("Europe/Berlin")
INDIA_TZ = ZoneInfo("Asia/Kolkata")

bot = commands.Bot(
    command_prefix='!',
    intents=intents
)

scheduler = AsyncIOScheduler()

action_verbs = [
    'submit', 'send', 'deliver', 'prepare', 'complete','make','fill','do', 'get', 
    'finish', 'share', 'create', 'post', 'upload', 'hand', 'make', 'perform', 'prepare'
]

timeframe_words = [
    'by', 'due','on', 'deadline', 'before', 'no later than', 
    'not later than', 'until', 'latest'
]

# --- Helper Functions ---

def get_text_after_timeframe_words(text, keywords):
    text_lower = text.lower()
    for keyword in keywords:
        idx = text_lower.find(keyword.lower())
        if idx != -1:
            after_keyword = text[idx + len(keyword):]
            return after_keyword.lstrip()
    return None

def extract_date(text):
    weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    now = datetime.now(INDIA_TZ)
    text_lower = text.strip().lower()

    # 1. Search for any weekday in the text
    match = None
    for i, day in enumerate(weekdays):
        if re.search(r'\b' + day + r'\b', text_lower):
            match = (day, i)
            break

    if match:
        weekday_num = match[1]
        days_ahead = (weekday_num - now.weekday() + 7) % 7
        days_ahead = days_ahead if days_ahead != 0 else 7  # Always next occurrence
        next_weekday = now + timedelta(days=days_ahead)
        # Set time to 20:00 IST
        next_weekday = next_weekday.replace(hour=20, minute=0, second=0, microsecond=0)
        # Ensure tzinfo is correct (ZoneInfo)
        next_weekday = next_weekday.replace(tzinfo=INDIA_TZ)
        return next_weekday

    # Fallback to dateparser for all other cases
    result = search_dates(
        text,
        settings={
            'PREFER_DATES_FROM': 'future',
            'RELATIVE_BASE': datetime.now(INDIA_TZ),
            'DATE_ORDER': 'DMY',
            'TIMEZONE': 'Asia/Kolkata',
            'RETURN_AS_TIMEZONE_AWARE': True
        },
        languages=['en']
    )
    if result:
        return result[0][1].astimezone(INDIA_TZ)
    return None

def has_explicit_user_mentions(message):
    for user in message.mentions:
        if user.mention in message.content:
            return True
    return False

def extract_time_from_text(text):
    # Look for time expressions using regex (e.g., 5pm, 17:00, 5:30 pm, etc.)
    time_patterns = [
        r'(\d{1,2}:\d{2}\s*[ap]m)',    # e.g., 5:30 pm
        r'(\d{1,2}\s*[ap]m)',          # e.g., 5pm
        r'(\d{1,2}:\d{2})',            # e.g., 17:00
        r'(\d{1,2})\s*o\'?clock',      # e.g., 5 o'clock
    ]
    for pattern in time_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def combine_date_and_time(date_obj, time_str):
    import re
    # Extract time from strings like "7pm" or "19:00"
    match = re.match(
        r'(\d{1,2})(?::(\d{2}))?\s*([ap]m)?', 
        time_str.strip().lower()
    )
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        ampm = match.group(3)
        
        # Convert to 24-hour format
        if ampm == 'pm' and hour != 12:
            hour += 12
        if ampm == 'am' and hour == 12:
            hour = 0
        
        # Apply time to date_obj WITH timezone
        return date_obj.astimezone(INDIA_TZ).replace(
            hour=hour, 
            minute=minute, 
            second=0, 
            microsecond=0
        )
    
    # Fallback for complex time strings
    dt = dateparser.parse(
        time_str,
        settings={
            'RELATIVE_BASE': date_obj,
            'TIMEZONE': 'Asia/Kolkata',
            'RETURN_AS_TIMEZONE_AWARE': True
        }
    )
    return dt.astimezone(INDIA_TZ) if dt else date_obj

# --- Reminder Job Tracking ---

reminder_jobs = {}  # {confirmation_message_id: {'job': job, 'type': 'dm'/'channel', ...}}

# --- Bot Events and Reminder Logic ---

@bot.event
async def on_ready():
    logger.info(f"Bot is ready as {bot.user}")
    scheduler.start()

async def send_reminder_dm(user_ids, message_link, duewhen):
    for user_id in user_ids:
        try:
            user = await bot.fetch_user(user_id)
            await user.send(
                f"⏰ **Reminder!** Hey! This task:{message_link} of yours is due {duewhen}\n"
                f"Hurry up! 😉"
            )
        except discord.Forbidden:
            logger.warning(f"User {user_id} has DMs disabled")
        except Exception as e:
            logger.error(f"Failed to DM user {user_id}: {e}")

async def send_confirmation_dm(user_ids, message_link, reminder_time, duewhen):
    for user_id in user_ids:
        try:
            user = await bot.fetch_user(user_id)
            msg = await user.send(
                f"I have scheduled a reminder for task:{message_link} on {reminder_time.strftime('%d %b %Y at %I:%M %p IST')}\n"
                f"*React to turn the reminder off!*"
            )
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            # Save the job/message context here (will be filled after job is scheduled)
            reminder_jobs[msg.id] = {
                'type': 'dm',
                'user_id': user_id,
                'message_id': msg.id,
                'channel_id': None,  # DM
                'job': None  # to be set after scheduling
            }
        except Exception as e:
            logger.error(f"Failed to send confirmation DM to user {user_id}: {e}")

async def send_channel_confirmation(channel_id, message_id, reminder_time, duewhen):
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            original_message = await channel.fetch_message(message_id)
            msg = await channel.send(
                f"I have scheduled a reminder for this task on {reminder_time.strftime('%d %b %Y at %I:%M %p IST')}\n"
                f"*React to turn the reminder off!*",
                reference=original_message
            )
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            reminder_jobs[msg.id] = {
                'type': 'channel',
                'user_id': None,
                'message_id': msg.id,
                'channel_id': channel_id,
                'job': None  # to be set after scheduling
            }
        except Exception as e:
            logger.error(f"Failed to send confirmation to channel: {e}")

async def send_channel_reminder(channel_id, message_id, duewhen, mention_text):
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            original_message = await channel.fetch_message(message_id)
            await channel.send(
                f"{mention_text} ⏰ **Reminder!** This task of yours is due {duewhen}\n"
                f"Hurry up! 😉",
                reference=original_message
            )
        except Exception as e:
            logger.error(f"Failed to send reminder to channel: {e}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if (
        ((message.mentions and has_explicit_user_mentions(message)) or message.mention_everyone) and
        any(re.search(r'\b' + re.escape(word) + r'\b', message.content.lower()) for word in action_verbs) and
        any(re.search(r'\b' + re.escape(word) + r'\b', message.content.lower()) for word in timeframe_words)
    ):
        mentioned_users = message.mentions
        after_by = get_text_after_timeframe_words(message.content, timeframe_words)
        due_date = extract_date(after_by)
        now = datetime.now(INDIA_TZ)

        try:
            if not due_date:
                raise ValueError("No valid date found")

            # Try to extract a time after the timeframe word
            time_str = extract_time_from_text(after_by) if after_by else None

            # If a time is mentioned, combine with the date
            if time_str:
                deadline_dt = combine_date_and_time(due_date, time_str)
                if deadline_dt < now:
                    return
                # Calculate reminder time: 2 hours before deadline
                reminder_time = deadline_dt - timedelta(hours=2)
                # If current time is already within 2 hours, set for 15 mins before deadline
                if reminder_time < now:
                    reminder_time = deadline_dt - timedelta(minutes=15)
                    duewhen = f"{deadline_dt.strftime('%d %b %Y at %I:%M %p IST')}"
                else:
                    duewhen = f"{deadline_dt.strftime('%d %b %Y at %I:%M %p IST')}"
            else:
                # Fallback to your standard logic
                if due_date.date() < now.date():
                    return
                if due_date.date() == now.date():
                    reminder_time = now.replace(hour=18, minute=0, second=0, microsecond=0)
                    duewhen = "today at 6 PM"
                    if reminder_time < now:
                        reminder_time = now.replace(hour=22, minute=0, second=0, microsecond=0)
                        duewhen = "today at 10 PM"
                else:
                    reminder_time = due_date.replace(hour=18, minute=0, second=0, microsecond=0)
                    duewhen = f"on {due_date.strftime('%d %b %Y')}"

            message_link = f"https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}"
            has_everyone = message.mention_everyone
            has_here = "@here" in message.content

            # If @here or @everyone, send in channel as a reply
            if has_everyone or has_here:
                await send_channel_confirmation(
                    message.channel.id,
                    message.id,
                    reminder_time,
                    duewhen
                )
                # Find the confirmation message (last message in channel)
                channel = bot.get_channel(message.channel.id)
                async for msg in channel.history(limit=1):
                    confirmation_msg = msg
                job = scheduler.add_job(
                    send_channel_reminder,
                    'date',
                    run_date=reminder_time,
                    args=[message.channel.id, message.id, duewhen, "@here" if has_here else "@everyone"]
                )
                # Save job reference
                if confirmation_msg.id in reminder_jobs:
                    reminder_jobs[confirmation_msg.id]['job'] = job
            else:
                await send_confirmation_dm(
                    [u.id for u in mentioned_users],
                    message_link,
                    reminder_time,
                    duewhen
                )
                # Find the confirmation DM message (for each user)
                for user in mentioned_users:
                    user_obj = await bot.fetch_user(user.id)
                    async for msg in user_obj.history(limit=1):
                        confirmation_msg = msg
                    job = scheduler.add_job(
                        send_reminder_dm,
                        'date',
                        run_date=reminder_time,
                        args=[[user.id], message_link, duewhen]
                    )
                    if confirmation_msg.id in reminder_jobs:
                        reminder_jobs[confirmation_msg.id]['job'] = job

        except Exception as e:
            logger.error(f"Error processing message {getattr(message, 'jump_url', 'unknown')}: {str(e)}")

# --- Reaction Event for Cancellation/Completion ---

@bot.event
async def on_reaction_add(reaction, user):
    # Ignore reactions from the bot itself
    if user == bot.user:
        return

    msg_id = reaction.message.id
    if msg_id in reminder_jobs and str(reaction.emoji) in ["❌", "✅"]:
        job_info = reminder_jobs.pop(msg_id, None)
        if job_info and job_info['job']:
            job_info['job'].remove()
            # Send cancellation confirmation
            if job_info['type'] == 'dm':
                # Only allow the user who received the DM to cancel
                if user.id == job_info['user_id']:
                    if str(reaction.emoji) == "❌":
                        await reaction.message.channel.send("Reminder cancelled 👍🏻.")
                    elif str(reaction.emoji) == "✅":
                        await reaction.message.channel.send("Task marked as completed! Reminder cancelled. Well done! 🎉")
            elif job_info['type'] == 'channel':
                channel = bot.get_channel(job_info['channel_id'])
                if channel:
                    if str(reaction.emoji) == "❌":
                        await channel.send(
                            f"Reminder cancelled by {user.mention}.👍🏻",
                            reference=reaction.message
                        )
                    elif str(reaction.emoji) == "✅":
                        await channel.send(
                            f"Task marked as completed by {user.mention}! Reminder cancelled. 🎉",
                            reference=reaction.message
                        )

if __name__ == "__main__":
    webserver.keep_alive()  # If you use a webserver for uptime
    asyncio.run(bot.start(discord_token))
