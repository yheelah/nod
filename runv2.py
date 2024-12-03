import asyncio
import cloudscraper
import time
from loguru import logger
from concurrent.futures import ThreadPoolExecutor
from curl_cffi import requests
from colorama import Fore, Style
from colorama import init as colorama_init
colorama_init(autoreset=True)


BANNER = f"""
{Fore.CYAN}[+]=========================[+]
{Fore.CYAN}[+]NODEPAY PROXY SCRIPT V2.2[+]
{Fore.CYAN}[+]  FARMING & DAILY CLAIM  [+]
{Fore.CYAN}[+]=========================[+]
"""

print(BANNER)

PING_INTERVAL = 60
KEEP_ALIVE_INTERVAL = 300
DOMAIN_API = {
    "SESSION": "http://api.nodepay.ai/api/auth/session",
    "PING": ["https://nw.nodepay.org/api/network/ping"]
}

CONNECTION_STATES = {
    "CONNECTED": 1,
    "DISCONNECTED": 2,
    "NONE_CONNECTION": 3
}

# Global variables for KeepAlive
wakeup = None
isFirstStart = False
isAlreadyAwake = False
firstCall = None
lastCall = None
timer = None

def letsStart():
    """Fungsi untuk memulai KeepAlive secara independen"""
    global wakeup, isFirstStart, isAlreadyAwake, firstCall, lastCall, timer

    if wakeup is None:
        isFirstStart = True
        isAlreadyAwake = True
        firstCall = time.time()
        lastCall = firstCall
        timer = KEEP_ALIVE_INTERVAL  # Interval KeepAlive dalam detik

        wakeup = asyncio.get_event_loop().call_later(timer, keepAlive)
        logger.info(">>> KeepAlive has been started.")

def keepAlive():
    """Fungsi yang akan dijalankan secara periodik untuk KeepAlive"""
    global lastCall, timer, wakeup

    now = time.time()
    lastCall = now
    logger.info(f">>> KeepAlive executed at {now:.3f}")

    # Reschedule KeepAlive
    wakeup = asyncio.get_event_loop().call_later(timer, keepAlive)

class AccountInfo:
    def __init__(self, token, proxies):
        self.token = token
        self.proxies = proxies
        self.status_connect = CONNECTION_STATES["NONE_CONNECTION"]
        self.account_data = {}
        self.retries = 0
        self.last_ping_status = 'Waiting...'
        self.browser_id = {
            'ping_count': 0,
            'successful_pings': 0,
            'score': 0,
            'start_time': time.time(),
            'last_ping_time': None
        }

    def reset(self):
        self.status_connect = CONNECTION_STATES["NONE_CONNECTION"]
        self.account_data = {}
        self.retries = 3

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

async def load_tokens():
    try:
        with open('tokens.txt', 'r') as file:
            tokens = file.read().splitlines()
        return tokens
    except Exception as e:
        logger.error(f"Failed to load tokens: {e}")
        raise SystemExit("Exiting due to failure in loading tokens")

async def call_api(url, data, account_info, proxy):
    headers = {
        "Authorization": f"Bearer {account_info.token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://app.nodepay.ai/",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "chrome-extension://lgmpfmgeabnnlemejacfljbmonaomfmm"
    }

    proxy_config = {
        "http": proxy,
        "https": proxy
    }

    try:
        response = scraper.post(url, json=data, headers=headers, proxies=proxy_config, timeout=60)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Error during API call for token {account_info.token} with proxy {proxy}: {e}")
        raise ValueError(f"Failed API call to {url}")

    return response.json()

async def render_profile_info(account_info):
    try:
        for proxy in account_info.proxies:
            try:
                response = await call_api(DOMAIN_API["SESSION"], {}, account_info, proxy)
                if response.get("code") == 0:
                    account_info.account_data = response["data"]
                    if account_info.account_data.get("uid"):
                        await start_ping(account_info)
                        return
                else:
                    logger.warning(f"Session failed for token {account_info.token} using proxy {proxy}")
            except Exception as e:
                logger.error(f"Failed to render profile info for token {account_info.token} using proxy {proxy}: {e}")

        logger.error(f"All proxies failed for token {account_info.token}")
    except Exception as e:
        logger.error(f"Error in render_profile_info for token {account_info.token}: {e}")

async def start_ping(account_info):
    try:
        logger.info(f"Starting ping for token {account_info.token}")
        while True:
            for proxy in account_info.proxies:
                try:
                    await asyncio.sleep(PING_INTERVAL)
                    await ping(account_info, proxy)
                except Exception as e:
                    logger.error(f"Ping failed for token {account_info.token} using proxy {proxy}: {e}")
    except asyncio.CancelledError:
        logger.info(f"Ping task for token {account_info.token} was cancelled")
    except Exception as e:
        logger.error(f"Error in start_ping for token {account_info.token}: {e}")

async def ping(account_info, proxy):
    for url in DOMAIN_API["PING"]:
        try:
            data = {
                "id": account_info.account_data.get("uid"),
                "browser_id": account_info.browser_id,
                "timestamp": int(time.time())
            }
            response = await call_api(url, data, account_info, proxy)
            if response["code"] == 0:
                logger.info(Fore.GREEN + f"Ping successful for token {account_info.token} using proxy {proxy}" + Style.RESET_ALL)
                return
        except Exception as e:
            logger.error(f"Ping failed for token {account_info.token} using URL {url} and proxy {proxy}: {e}")

def process_account(token, proxies):
    account_info = AccountInfo(token, proxies)
    asyncio.run(render_profile_info(account_info))

async def main():
    letsStart()  # Memulai KeepAlive
    tokens = await load_tokens()

    # Membaca proxy dari file local_proxies.txt
    try:
        with open('local_proxies.txt', 'r') as file:
            proxies = file.read().splitlines()
    except Exception as e:
        logger.error(f"Failed to load proxies: {e}")
        raise SystemExit("Exiting due to failure in loading proxies")

    with ThreadPoolExecutor(max_workers=3000) as executor:
        futures = []
        for token in tokens:
            futures.append(executor.submit(process_account, token, proxies))

        for future in futures:
            future.result()

def dailyclaim():
    try:
        with open('tokens.txt', 'r') as file:
            local_data = file.read().splitlines()
            for tokenlist in local_data:
                url = f"https://api.nodepay.org/api/mission/complete-mission?"
                headers = {
                    "Authorization": f"Bearer {tokenlist}",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
                    "Content-Type": "application/json",
                    "Origin": "https://app.nodepay.ai",
                    "Referer": "https://app.nodepay.ai/"
                }
                
                data = {
                    "mission_id":"1"
                }

                response = requests.post(url, headers=headers, json=data, impersonate="chrome110")
                
                # Tambahkan pengecekan status kode HTTP
                if response.status_code != 200:
                    logger.error(f"Failed request with status code: {response.status_code}")
                    continue

                # Log isi respons
                logger.debug(f"Response content: {response.content}")

                try:
                    is_success = response.json().get('success')
                    if is_success == True:
                        logger.info('Claim Reward Success!')
                        logger.info(response.json())
                    else:
                        logger.info('Reward Already Claimed! Or Something Wrong!')
                except ValueError as e:
                    logger.error(f"Failed to parse JSON response: {e}")
    except requests.exceptions.RequestException as e:
        print(f"Error : {e}")

if __name__ == '__main__':
    try:
        dailyclaim()
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Program terminated by user.")
