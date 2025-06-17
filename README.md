A smart Discord bot that helps teams keep track of deadlines and tasks by automatically setting reminders based on a certain combination of keywords in the messages.

🚀 Features
Natural Language Parsing: Understands due dates and times from messages (e.g., "by Monday", "by 3-06-2025", "until tomorrow 7 pm"). (dateparser library)

Automatic Reminders: Sets reminders for mentioned users, reminding them 2 hours before the deadline or 15 minutes before if already within 2 hours.

Flexible Time Handling: Handles various date formats, weekdays, and 12/24-hour times.

Reaction Management: Users can mark tasks as completed or cancel reminders using ✅ and ❌ reactions.

Default Time: If no time is specified, it defaults to 8 PM IST for due dates.

Robust Action Verb Matching: Only triggers on messages containing explicit action verbs (e.g., "submit", "send", "deliver") to avoid false positives.

Error Handling: Logs errors and informs users if a reminder cannot be set (e.g., if the reminder time is in the past).

📝 Project Overview
This bot is designed to help teams and groups on Discord stay organized by automating the process of setting reminders for tasks and deliverables. It parses messages for deadlines and automatically sends reminders to the appropriate users, reducing the risk of missed deadlines.

Hardcoded Words:

a) Task verbs - 
'submit', 'send', 'deliver', 'prepare', 'complete', 'make', 'fill', 'do', 'get', 'finish', 'share', 'create', 'post', 'upload', 'hand', 'make', 'perform', 'prepare'

b) deadline identifiers - 
'by', 'due', 'on', 'deadline', 'before', 'no later than', 'not later than', 'until', 'latest'

c) Compatible Dates & Time inputs - 
Days of the week, 'today', 'tomorrow', 'next week/month', dd/mm/yyyy, 'dd Month'
12 hr & 24 hr time format e.g. 6 pm or 18:00 

**Current limitation: 12hr time immediately preceded by dd.mm.yyyy not supported e.g. "....by 12/08/2025 8pm"
