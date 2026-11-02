#!/usr/bin/env python3
import asyncio, random, logging, os, sys, traceback
import aiohttp
from bs4 import BeautifulSoup

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
YOUTUBE_BASE   = "https://www.youtube.com/watch?v="
VIEW_DURATION   = 300          # 5 minutes per video
MAX_CONCURRENCY = 100
PROXY_TIMEOUT   = 10
DEFAULT_TIMEOUT = 30
MAX_RETRIES     = 3

HEADERS = {
    "User-Agent": random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    ]),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ------------------------------------------------------------------
# Helpers – fetch proxy list
# ------------------------------------------------------------------
async def fetch_proxies_from_url(session: aiohttp.ClientSession, url: str) -> list[str]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                logging.warning(f"URL {url} returned {resp.status}")
                return []
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            table = soup.find("table")
            if not table:
                logging.warning(f"No table found on {url}")
                return []
            proxies = []
            for row in table.tbody.find_all("tr"):
                cols = row.find_all("td")
                if len(cols) < 2:
                    continue
                ip = cols[0].text.strip()
                port = cols[1].text.strip()
                proxies.append(f"{ip}:{port}")
            return proxies
    except Exception as exc:
        logging.error(f"Failed to fetch proxies from {url}: {exc}")
        return []

async def gather_all_proxies() -> list[str]:
    urls = [
        "https://free-proxy-list.net/ssl-proxy.html",
        "https://free-proxy-list.net/anonymous-proxy.html",
        "https://www.sslproxies.org/",
        "https://www.us-proxy.org/",
        "https://www.proxyscan.io/proxy/list?type=https",
        "https://www.proxyscan.io/proxy/list?type=http",
    ]
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_proxies_from_url(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
    all_proxies = {p for sublist in results for p in sublist}
    logging.info(f"Fetched {len(all_proxies)} proxies from the web")
    return list(all_proxies)

# ------------------------------------------------------------------
# Helpers – proxy checker
# ------------------------------------------------------------------
def format_proxy(proxy: str) -> str:
    """Return full proxy URL usable by aiohttp."""
    if "://" in proxy:
        return proxy
    # Try HTTP first
    return f"http://{proxy}"

async def is_proxy_working(proxy: str, session: aiohttp.ClientSession) -> bool:
    proxy_url = format_proxy(proxy)
    try:
        async with session.get(
                "https://api.ipify.org?format=json",
                proxy=proxy_url,
                timeout=aiohttp.ClientTimeout(total=PROXY_TIMEOUT),
                ssl=False,
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                logging.debug(f"Proxy {proxy} works → IP {data.get('ip')}")
                return True
            logging.debug(f"Proxy {proxy} returned status {resp.status}")
            return False
    except Exception as exc:
        logging.debug(f"Proxy {proxy} failed: {exc}")
        return False

async def check_proxies_concurrently(proxies: list[str]) -> list[str]:
    valid = []
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENCY, verify_ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [asyncio.create_task(is_proxy_working(p, session)) for p in proxies]
        for proxy, task in zip(proxies, tasks):
            if await task:
                valid.append(proxy)
    logging.info(f"{len(valid)} proxies are working out of {len(proxies)}")
    return valid

# ------------------------------------------------------------------
# Helpers – youtube view
# ------------------------------------------------------------------
async def fetch_video(video_id: str, session: aiohttp.ClientSession, proxies: list[str]) -> bool:
    for attempt in range(1, MAX_RETRIES + 1):
        proxy = random.choice(proxies) if proxies else None
        proxy_url = format_proxy(proxy) if proxy else None
        try:
            async with session.get(
                    f"{YOUTUBE_BASE}{video_id}",
                    proxy=proxy_url,
                    headers=HEADERS,
                    timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
                    ssl=False,          # only for the proxy
            ) as resp:
                if resp.status == 200:
                    logging.info(f"✅ Success: {video_id} (Proxy: {proxy or 'Direct'})")
                    await asyncio.sleep(VIEW_DURATION)
                    return True
                if resp.status in (403, 429):
                    logging.warning(f"{video_id} status {resp.status} – retrying with new proxy")
                    await asyncio.sleep(2 * attempt)
                    continue
                logging.warning(f"{video_id} returned status {resp.status}")
                return False
        except Exception as exc:
            logging.error(f"Attempt {attempt} – Error fetching {video_id}: {exc}")
            await asyncio.sleep(1 * attempt)
    return False

async def run_cycle(video_ids: list[str], proxies: list[str]):
    semaphore = asyncio.Semaphore(5)   # max 5 concurrent views
    async with aiohttp.ClientSession() as session:
        async def sem_task(vid):
            async with semaphore:
                return await fetch_video(vid, session, proxies)

        tasks = [asyncio.create_task(sem_task(v)) for v in video_ids]
        await asyncio.gather(*tasks)

# ------------------------------------------------------------------
# main()
# ------------------------------------------------------------------
def main():
    proxies = asyncio.run(gather_all_proxies())
    valid_proxies = asyncio.run(check_proxies_concurrently(proxies))
    if not valid_proxies:
        logging.warning("No working proxies found – falling back to direct connections.")
        valid_proxies = [None]

    video_ids = [
        "2BdoajgFDtc", "ueZLEXwFlDM", "3k6FYvrUQkQ",
        "y0hCW06P4nc", "5XeLdcNrSo4"
    ]

    logging.info("Starting automated view script with 5‑minute duration per video.")
    try:
        asyncio.run(run_cycle(video_ids, valid_proxies))
        logging.info("Cycle complete – script finished.")
    except KeyboardInterrupt:
        logging.info("Script stopped by user.")
    finally:
        sys.exit(0)

if __name__ == "__main__":
    main()
