import os
os.environ['PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH'] = '/usr/bin/google-chrome-stable'
os.environ['PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD'] = '1'
from src.scrapers.climate_downloader import document_downloader
document_downloader()