import requests
import time
import random
from bs4 import BeautifulSoup
import logging

# تنظیمات اولیه
YOUTUBE_API_URL = "https://www.youtube.com/watch?v=rql0nQ6mWSs" # برای نمونه از این URL استفاده می‌کنیم
PROXY_LIST_FILE = "proxies.txt" # فایل لیست پروکسی‌ها
CHECK_INTERVAL = 3600 # هر ساعت (ثانیه)

# تنظیم لاگینگ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def get_random_proxy():
    """خواندن لیست پروکسی‌ها و انتخاب تصادفی یکی"""
    try:
        with open(PROXY_LIST_FILE, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
            if not proxies:
                raise Exception("لیست پروکسی خالی است")
            return random.choice(proxies)
    except FileNotFoundError:
        logging.error("فایل proxies.txt پیدا نشد!")
        return None

def fetch_video_views(video_id, proxy=None):
    """شبیه‌سازی بازدید از ویدیو"""
    url = f"{YOUTUBE_API_URL}{video_id}"
    
    # هدرهای تصادفی برای شبیه‌سازی مرورگر
    headers = {
        'User-Agent': random.choice([
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        ])
    }
    
    # پارامترهای پروکسی
    proxies = {
        'http': f'http://{proxy}',
        'https': f'http://{proxy}'
    } if proxy else {}

    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=10)
        if response.status_code == 200:
            logging.info(f"بازدید موفق برای ویدیو {video_id} با پروکسی {proxy}")
            return True
        else:
            logging.warning(f"خطا در بازدید از ویدیو {video_id}: کد وضعیت {response.status_code}")
            return False
    except Exception as e:
        logging.error(f"خطا در ارتباط با پروکسی {proxy}: {e}")
        return False

def main():
    # لیست ID ویدیوهایی که می‌خواهید بازدید بزنید (مثال)
    video_ids = ["2BdoajgFDtc", "ueZLEXwFlDM", "3k6FYvrUQkQ", "y0hCW06P4nc", "5XeLdcNrSo4"] # IDهای واقعی خود را جایگزین کنید
    
    logging.info("شروع فرآیند بازدید اتوماتیک...")
    
    while True:
        for video_id in video_ids:
            proxy = get_random_proxy()
            if proxy:
                fetch_video_views(video_id, proxy)
        
        logging.info(f"چرخه بازدید تمام شد. {CHECK_INTERVAL} ثانیه دیگر تکرار می‌شود...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
