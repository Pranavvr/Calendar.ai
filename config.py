
# Fallback only. Each user's real timezone is read from their primary Google
# Calendar at login and stored on users.timezone; this is used when that lookup
# failed or the user predates the column.
TIMEZONE       = "America/New_York"
MODEL_NAME     = "gpt-4o-mini"

# USD per 1M tokens, used only to estimate the cost of an agent run in logs.
# These are a local constant that upstream pricing can drift from at any time —
# re-check against current provider pricing when changing MODEL_NAME, and treat
# logged cost as an order-of-magnitude signal for spotting runaway loops rather
# than as billing data.
MODEL_PRICE_PER_1M_INPUT  = 0.15
MODEL_PRICE_PER_1M_OUTPUT = 0.60
RECURSION_LIMIT = 10

# Rate limit for POST /schedule, per user. An agent run costs money and takes
# 40-60s, so this is sized for a human working with the app rather than for
# throughput: comfortably above normal use, low enough to bound a retry loop.
SCHEDULE_RATE_LIMIT_REQUESTS = 10
SCHEDULE_RATE_LIMIT_WINDOW_SECONDS = 300  # 5 minutes
DAY_START_HOUR = 8    # 8am
DAY_END_HOUR   = 22   # 10pm
BUFFER_MINUTES = 15