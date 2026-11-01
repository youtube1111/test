#!/usr/bin/env python3
import os
import random
import time
import logging
import requests
from requests.adapters import HTTPAdapter, Retry

# ------------------------------------------------------------
# تنظیمات پایه
# ------------------------------------------------------------
YOUTUBE_BASE = "https://www.youtube.com/watch?v=rql0nQ6mWSs"
PROXY_FILE = "proxies.txt"
CHECK_INTERVAL = 3600  # هر ساعت
DEFAULT_TIMEOUT = 30   # ثانیه
MAX_RETRIES = 3

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ------------------------------------------------------------
# ساخت session با retry
# ------------------------------------------------------------
session = requests.Session()
adapter = HTTPAdapter(
    max_retries=Retry(
        total=MAX_RETRIES,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False,
    )
)
session.mount("http://", adapter)
session.mount("https://", adapter)

# ------------------------------------------------------------
# دریافت پراکسی تصادفی از فایل
# ------------------------------------------------------------
def get_random_proxy():
    if not os.path.exists(PROXY_FILE):
        logging.warning(f"فایل {PROXY_FILE} پیدا نشد! بدون پراکسی ادامه می‌دهیم.")
        return None
    with open(PROXY_FILE, "r") as f:
        proxies = [line.strip() for line in f if line.strip()]
    if not proxies:
        logging.warning("لیست پراکسی خالی است. بدون پراکسی ادامه می‌دهیم.")
        return None
    return random.choice(proxies)

# ------------------------------------------------------------
# تست پراکسی قبل از استفاده
# ------------------------------------------------------------
def test_proxy(proxy_url):
    try:
        resp = session.get(
            "https://www.google.com",  # تست سریع
            proxies={"http": proxy_url, "https": proxy_url},
            timeout=DEFAULT_TIMEOUT,
        )
        return resp.status_code == 200
    except Exception as e:
        logging.warning(f"پراکسی {proxy_url} نامعتبر: {e}")
        return False

# ------------------------------------------------------------
# بازدید ویدیو
# ------------------------------------------------------------
def fetch_video(video_id, proxy=None):
    url = f"{YOUTUBE_BASE}{video_id}"
    headers = {
        "User-Agent": random.choice(
            [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            ]
        )
    }

    proxies = {"http": proxy, "https": proxy} if proxy else {}

    try:
        resp = session.get(url, headers=headers, proxies=proxies, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 200:
            logging.info(f"✅ بازدید موفق برای {video_id} (پراکسی: {proxy or 'direct'})")
            return True
        else:
            logging.warning(f"⚠️ کد وضعیت {resp.status_code} برای {video_id}")
            return False
    except requests.exceptions.ProxyError as e:
        logging.error(f"❌ خطا در ارتباط با پراکسی {proxy}: {e}")
        return False
    except Exception as e:
        logging.error(f"❌ خطای عمومی: {e}")
        return False

# ------------------------------------------------------------
# حلقه اصلی
# ------------------------------------------------------------
def main():
    # لیست ID ویدیوها
    video_ids = ["2BdoajgFDtc", "ueZLEXwFlDM", "3k6FYvrUQkQ", "y0hCW06P4nc", "5XeLdcNrSo4"]

    logging.info("شروع فرآیند بازدید اتوماتیک...")

    while True:
        for vid in video_ids:
            proxy = get_random_proxy()
            if proxy and not test_proxy(proxy):
                # اگر پراکسی نامعتبر بود، بدون پراکسی امتحان کن
                proxy = None
            fetch_video(vid, proxy)

        logging.info(f"چرخه بازدید تمام شد. در {CHECK_INTERVAL} ثانیه دیگر ادامه می‌دهیم...")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
