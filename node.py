import asyncio
import time
import uuid
from loguru import logger
import httpx
import cloudscraper

PING_INTERVAL = 60
NOTIFICATION_INTERVAL = 1800
RETRIES = 60

DOMAIN_API = {
    "SESSION": "http://api.nodepay.ai/api/auth/session",
    "PING": "https://nw.nodepay.org/api/network/ping"
}

CONNECTION_STATES = {
    "CONNECTED": 1,
    "DISCONNECTED": 2,
    "NONE_CONNECTION": 3
}

DEFAULT_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

status_connect = CONNECTION_STATES["NONE_CONNECTION"]
browser_id = None
account_info = {}
last_ping_time = {}
last_notification_time = 0

BOT_TOKEN = "7761568719:AAHZceTGz-Y8Fskdg5ZZpBeYNN-SYgySZ14"
CHAT_ID = "7053916798"

def uuidv4():
    return str(uuid.uuid4())

def valid_resp(resp):
    if not resp or "code" not in resp or resp["code"] < 0:
        raise ValueError("Invalid response")
    return resp

async def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
            response.raise_for_status()
            logger.info("Pesan berhasil dikirim ke Telegram.")
    except Exception as e:
        logger.error(f"Gagal mengirim pesan ke Telegram: {e}")

async def render_profile_info(token):
    global browser_id, account_info

    try:
        np_session_info = load_session_info()

        if not np_session_info:
            browser_id = uuidv4()  # Generate new browser_id
            response = await call_api(DOMAIN_API["SESSION"], {}, token)
            valid_resp(response)
            account_info = response.get("data", {})
            if account_info.get("uid"):
                save_session_info(account_info)
                await start_ping(token)
            else:
                handle_logout()
        else:
            account_info = np_session_info
            await start_ping(token)
    except Exception as e:
        logger.error(f"Error in render_profile_info: {e}")
        if "500 Internal Server Error" in str(e) or "keepalive ping timeout" in str(e):
            logger.info("Clearing invalid session.")
            handle_logout()
        else:
            logger.error(f"Unexpected error: {e}")

async def call_api(url, data, token):
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": DEFAULT_USER_AGENT,
        "Content-Type": "application/json",
        "Origin": "chrome-extension://lgmpfmgeabnnlemejacfljbmonaomfmm",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
    }
    async with httpx.AsyncClient() as client:
        try:
#            scraper = cloudscraper.create_scraper()
#            response = scraper.post(url, json=data, headers=headers, timeout=30)
            response = await client.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            return valid_resp(response.json())
        except httpx.RequestError as e:
            logger.error(f"Request error during API call: {e}")
            raise ValueError(f"Failed API call to {url}")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise ValueError(f"Failed API call to {url}")
            
async def start_ping(token):
    global last_notification_time, account_info

    try:
        while True:
            
            np_session_info = load_session_info()
            if not np_session_info:
                response = await call_api(DOMAIN_API["SESSION"], {}, token)
                valid_resp(response)
                account_info = response.get("data", {})
            else:
                account_info = np_session_info

            await ping(token)

            
            current_time = time.time()
            if current_time - last_notification_time >= NOTIFICATION_INTERVAL:
                uuid = account_info.get('uid', 'Tidak diketahui')
                balance = account_info.get('balance', {})
                current_amount = balance.get('current_amount', 'Tidak diketahui')
                total = balance.get('total_collected', 'Tidak diketahui')
                message = (
                    f"📊Status koneksi: {status_connect}\n"
                    f"🪪Akun: {uuid}\n\n"
                    f"💵Penghasilan: {current_amount}\n"
                    f"💰Total Saldo: {total}"
                )
                await send_telegram_message(message)
                last_notification_time = current_time

            await asyncio.sleep(PING_INTERVAL)
    except asyncio.CancelledError:
        logger.info("Ping task was cancelled.")
    except Exception as e:
        logger.error(f"Error in start_ping: {e}")


async def ping(token):
    global last_ping_time, RETRIES, status_connect

    current_time = time.time()
    if last_ping_time.get("last_ping_time") and (current_time - last_ping_time["last_ping_time"]) < PING_INTERVAL:
        logger.info("Skipping ping, not enough time elapsed.")
        return

    last_ping_time["last_ping_time"] = current_time

    try:
        data = {
            "id": account_info.get("uid"),
            "browser_id": browser_id,
            "timestamp": int(current_time),
            "version": "2.2.7"
        }

        response = await call_api(DOMAIN_API["PING"], data, token)
        if response.get("code") == 0:
            logger.info(f"Ping successful: {response}")
            RETRIES = 0
            status_connect = CONNECTION_STATES["CONNECTED"]
        else:
            handle_ping_fail(response)
    except Exception as e:
        logger.error(f"Ping failed: {e}")
        handle_ping_fail(None)

def handle_ping_fail(response):
    global RETRIES, status_connect

    RETRIES += 1
    if response and response.get("code") == 403:
        handle_logout()
    else:
        status_connect = CONNECTION_STATES["DISCONNECTED"]

def handle_logout():
    global status_connect, account_info

    status_connect = CONNECTION_STATES["NONE_CONNECTION"]
    account_info = {}
    logger.info("Session cleared and user logged out.")

def save_session_info(data):
    pass

def load_session_info():
    return {}

async def main():
    token = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiIxMzA3NzA1ODM3Mjg3ODk5MTM2IiwiaWF0IjoxNzM1MTE4Mjk0LCJleHAiOjE3MzYzMjc4OTR9.PCOWAJC5kF0tgjbe94WmNbA54To9cNKatZdJbK1NrzSx0iYRqy7qz_qUpG4lgaC8BSFAKn7n-F4Z4B5q_dPfeg"
    if not token:
        logger.error("Token cannot be empty. Exiting.")
        return

    try:
        await render_profile_info(token)
    except Exception as e:
        logger.error(f"Error in main: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Program terminated.")
