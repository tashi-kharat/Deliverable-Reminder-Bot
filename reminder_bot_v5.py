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

# Enable required intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Not strictly needed now, but safe to keep

discord_token = os.environ['discordkey']
FRANKFURT_TZ = ZoneInfo("Europe/Berlin")
INDIA_TZ = ZoneInfo("Asia/Kolkata")


bot = commands.Bot(
    command_prefix='!',
    intents=intents
)

scheduler = AsyncIOScheduler()

action_verbs = [
    'submit', 'send', 'deliver', 'prepare', 'complete','make', 'get', 
    'finish', 'share', 'create', 'post', 'upload', 'hand'
]

timeframe_words = [
    'by', 'due','on', 'deadline', 'before', 'no later than', 
    'not later than', 'until', 'latest'
]

def get_text_after_timeframe_words(text, keywords):
    try:
        text_lower = text.lower()
        for keyword in keywords:
            idx = text_lower.find(keyword.lower())
            if idx != -1:
                after_keyword = text[idx + len(keyword):]
                return after_keyword.lstrip()
        return None
    except Exception:
        return None

def extract_date(text):
    result = search_dates(
        text,
        settings={
            'PREFER_DATES_FROM': 'future',
            'RELATIVE_BASE': datetime.now(FRANKFURT_TZ),
            'DATE_ORDER': 'DMY',
            'TIMEZONE': 'Europe/Berlin',
            'RETURN_AS_TIMEZONE_AWARE': True
        },
        languages=['en']
    )
    if result:
        return result[0][1].astimezone(FRANKFURT_TZ)
    return None

@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}")
    scheduler.start()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Only trigger if all three conditions are met
    if (
        message.mentions and
        any(word in message.content.lower() for word in action_verbs) and
        any(word in message.content.lower() for word in timeframe_words)
    ):
        mentioned_users = [user for user in message.mentions]
        after_by = get_text_after_timeframe_words(message.content, timeframe_words)
        due_date = extract_date(after_by)
        mentioned_mentions = ', '.join(user.mention for user in mentioned_users)
        now = datetime.now(FRANKFURT_TZ)

        try:
            if due_date.date() == now.date():
                # Due date is today, set reminder for 6 PM today
                reminder_time = now.replace(hour=22, minute=30, second=0, microsecond=0).astimezone(FRANKFURT_TZ)
                reminder_day = ""
                whentext = "today"
                digit = 6
                duewhen = "today"
            
            else:
                reminder_time = due_date - timedelta(days=1)
                reminder_day = reminder_time.date()
                reminder_time = reminder_time.replace(hour=22, minute=35, second=0, microsecond=0).astimezone(FRANKFURT_TZ)
                whentext = "a day prior i.e. "
                digit = 4
                duewhen = "tomorrow"

            scheduler.add_job(
                send_reminder_channel,
                'date',
                run_date=reminder_time,
                args=[message.channel.id, message.id, mentioned_mentions, duewhen]
            )

            await message.channel.send(
                f"A reminder has been set for this task {whentext}{reminder_day} at {digit}PM"
            )

        except (ValueError, TypeError, AttributeError):
            print(f"A date could not be found for the action message https://discord.com/channels/{message.guild.id}/{message.channel.id}/{message.id}")

async def send_reminder_channel(channel_id, message_id, mentioned_mentions, duewhen):
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            original_message = await channel.fetch_message(message_id)
            await original_message.reply(
                f"Hey {mentioned_mentions}, just a friendly reminder this work of yours is due {duewhen}! Hurry up! 😉"
            )
        except Exception as e:
            print(f"Failed to reply to message: {e}")

if __name__ == "__main__":
    webserver.keep_alive()
    asyncio.run(bot.start(discord_token))
