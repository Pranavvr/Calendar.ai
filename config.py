
# Fallback only. Each user's real timezone is read from their primary Google
# Calendar at login and stored on users.timezone; this is used when that lookup
# failed or the user predates the column.
TIMEZONE       = "America/New_York"
MODEL_NAME     = "gpt-4o-mini"
RECURSION_LIMIT = 10
DAY_START_HOUR = 8    # 8am
DAY_END_HOUR   = 22   # 10pm
BUFFER_MINUTES = 15