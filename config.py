from dotenv import load_dotenv
import os

load_dotenv()

settings = {
    'DISCORD_TOKEN': os.getenv('DISCORD_TOKEN', ''),
    'PREFIX': os.getenv('COMMAND_PREFIX', '!'),
    'SCAN_INTERVAL': int(os.getenv('SCAN_INTERVAL', '60')),
    'HELIUS_API_KEY': os.getenv('HELIUS_API_KEY', ''),
    'BIRDEYE_API_KEY': os.getenv('BIRDEYE_API_KEY', ''),
    'ALERT_CHANNEL_ID': os.getenv('ALERT_CHANNEL_ID', ''),
}
