import os

# Telegram Bot Token from environment variable
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

# ISS Mimic URL
ISS_MIMIC_URL = 'https://iss-mimic.github.io/Mimic/index'

# How often to check the urine tank level (in seconds)
CHECK_INTERVAL = 60

# Database to store subscriber chat IDs (using simple file for this example)
SUBSCRIBERS_FILE = 'data/subscribers.txt'

# Minimum change in urine tank level to trigger notification (%)
MIN_CHANGE_THRESHOLD = 0.5 