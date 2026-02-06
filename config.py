import logging
from datetime import datetime
import os
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_CHANNELS = os.getenv('TELEGRAM_CHANNEL').split(',')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')

gdelt_urls = [
    ("http://data.gdeltproject.org/gdeltv2/masterfilelist.txt", "masterfilelist.txt"),
    ("http://data.gdeltproject.org/gdeltv2/masterfilelist-translation.txt", "masterfilelist_translation.txt")
]

YEAR = '/' + datetime.strftime(datetime.now(), "%Y%m") 

most_sources = os.getenv('MOST_SOURCES').split(',')

KEYWORDS = [w for w in os.getenv('KEYWORDS').split(',') if len(w) > 4]

# Set up logging configuration
logging.basicConfig(
    # filename='gdelt_parser.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# print(KEYWORDS)