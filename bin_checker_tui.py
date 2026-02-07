import os
import sys
import time
import requests
import threading
import math
import random
import csv
from concurrent.futures import ThreadPoolExecutor
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

# Configuration
BINLIST_API = "https://lookup.binlist.net/{}"
HEADERS = {
    'Accept-Version': '3',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
# Fix: Define the missing APIS list that is used in check_single_bin
APIS = [
    {"url": "https://lookup.binlist.net/{}", "type": "binlist"},
    {"url": "https://data.handyapi.com/bin/{}", "type": "handyapi"},
    {"url": "https://api.paystack.co/decision/bin/{}", "type": "paystack"}
]
ROWS_PER_PAGE = 20

class BinCheckerTUI:
    def __init__(self, bin_file, proxy_file=None):
        self.bin_list = self.load_bins(bin_file)
        self.proxies = self.load_proxies(proxy_file) if proxy_file else []
        self.results = {}  # bin -> info dict
        self.valid_count = 0
        self.lock = threading.Lock()
        self.running = True
        self.current_page = 1
        self.total_pages = math.ceil(len(self.bin_list) / ROWS_PER_PAGE) if self.bin_list else 1
        self.processed_count = 0
        self.csv_file = "valid_bins.csv"
        self.init_csv()

    def init_csv(self):
        with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["BIN", "BRAND", "COUNTRY", "TYPE", "LEVEL", "BANK"])

    def save_to_csv(self, bin_code, data):
        with open(self.csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([bin_code, data.get('brand'), data.get('country'), data.get('type'), data.get('level'), data.get('bank')])
    
    @staticmethod
    def check_luhn(card_number):
        """
        Kiểm tra tính hợp lệ của dãy số theo thuật toán Luhn (Modulo 10).
        Trả về True nếu hợp lệ, False nếu không hợp lệ.
        """
        try:
            # Chuyển chuỗi thành danh sách các số nguyên và loại bỏ khoảng trắng/dấu gạch ngang
            digits = [int(d) for d in str(card_number).replace(" ", "").replace("-", "")]
            
            if not digits:
                return False

            # 1. Tách chữ số kiểm tra (chữ số cuối cùng)
            check_digit = digits.pop()
            
            # 2. Đảo ngược danh sách các chữ số còn lại
            digits.reverse()
            
            total_sum = 0
            
            # 3. Duyệt qua từng chữ số
            for i, digit in enumerate(digits):
                if i % 2 == 0:
                    digit *= 2
                    # Nếu tích > 9, cộng các chữ số của tích (hoặc trừ đi 9)
                    if digit > 9:
                        digit -= 9
                total_sum += digit
            
            # 4. Cộng chữ số kiểm tra vào tổng cuối cùng
            total_sum += check_digit
            
            # 5. Nếu tổng chia hết cho 10 thì dãy số hợp lệ
            return total_sum % 10 == 0
        except Exception:
            return False

    @staticmethod
    def abbreviate_country(name):
        """Viết tắt một số quốc gia tên dài để tiết kiệm diện tích hiển thị"""
        name = name.upper()
        mapping = {
            "UNITED ARAB EMIRATES": "UAE",
            "UNITED STATES": "USA",
            "UNITED KINGDOM": "UK",
            "UNITED STATES OF AMERICA": "USA",
            "RUSSIAN FEDERATION": "RUSSIA",
            "KOREA, REPUBLIC OF": "SOUTH KOREA",
            "VIRGIN ISLANDS (US)": "VI(US)",
            "VIRGIN ISLANDS (BRITISH)": "VI(UK)"
        }
        return mapping.get(name, name)

    def load_bins(self, file_path):
        if not os.path.exists(file_path):
            return []
        with open(file_path, 'r', encoding='utf-8') as f:
            # Extract first 6 digits, remove non-digits
            bins = []
            for line in f:
                clean_line = ''.join(filter(str.isdigit, line.strip()))
                
                # Nếu là chuỗi số dài (CC full), check Luhn để lọc rác
                if len(clean_line) >= 13 and not self.check_luhn(clean_line):
                    continue

                if len(clean_line) >= 6:
                    bins.append(clean_line[:6])
            return list(set(bins)) # Dedup

    def load_proxies(self, file_path):
        if not file_path or not os.path.exists(file_path):
            return []
        with open(file_path, 'r', encoding='utf-8') as f:
            proxies = []
            for line in f:
                line = line.strip()
                if not line: continue
                
                # Format: host:port:user:pass (ZingProxy style)
                # ZingProxy often uses hyphens in username, so simply splitting by ':' is safest if count is 3
                parts = line.split(":")
                if len(parts) == 4:
                    host, port, user, password = parts[0], parts[1], parts[2], parts[3]
                    fmt = f"http://{user}:{password}@{host}:{port}"
                    proxies.append({"http": fmt, "https": fmt})
                elif "@" in line:
                     # Already formatted user:pass@host:port
                     proxies.append({"http": f"http://{line}", "https": f"http://{line}"})
                else:
                     # IP:Port only
                     proxies.append({"http": f"http://{line}", "https": f"http://{line}"})
            return proxies

    def get_proxy(self):
        if not self.proxies:
            return None
        return random.choice(self.proxies)

    def check_single_bin(self, bin_code):
        if not self.running: return

        # Try up to 3 different proxies (or 1 attempt if no proxies)
        max_retries = 3 if self.proxies else 1
        
        for attempt in range(max_retries):
            proxy = self.get_proxy()
            
            # Shuffle APIs to try all of them before declaring proxy dead
            current_apis = list(APIS)
            random.shuffle(current_apis)
            
            proxy_working = False
            
            for api_info in current_apis:
                api_url = api_info["url"].format(bin_code)
                try:
                    response = requests.get(api_url, headers=HEADERS, proxies=proxy, timeout=10)
                    
                    # If we get a response, proxy is working
                    proxy_working = True
                    
                    with self.lock:
                        if response.status_code == 200:
                            data = response.json()
                            
                            # Normalize Data based on API type
                            if api_info["type"] == "binlist":
                                res_data = {
                                    "brand": data.get('brand', 'UNKNOWN').upper(),
                                    "country": data.get('country', {}).get('name', 'UNKNOWN').upper(),
                                    "type": data.get('type', 'UNKNOWN').upper(),
                                    "level": "STANDARD", 
                                    "bank": data.get('bank', {}).get('name', 'UNKNOWN').upper()
                                }
                            elif api_info["type"] == "handyapi":
                                 res_data = {
                                    "brand": data.get('Scheme', 'UNKNOWN').upper(),
                                    "country": data.get('Country', {}).get('Name', 'UNKNOWN').upper(),
                                    "type": data.get('Type', 'UNKNOWN').upper(),
                                    "level": data.get('CardTier', 'STANDARD').upper(),
                                    "bank": data.get('Issuer', 'UNKNOWN').upper()
                                }
                            elif api_info["type"] == "paystack":
                                d = data.get('data', {})
                                res_data = {
                                    "brand": d.get('brand', 'UNKNOWN').upper(),
                                    "country": d.get('country_name', 'UNKNOWN').upper(),
                                    "type": d.get('card_type', 'UNKNOWN').upper(),
                                    "level": d.get('sub_brand', 'STANDARD').upper() if d.get('sub_brand') else "STANDARD",
                                    "bank": d.get('bank', 'UNKNOWN').upper()
                                }
                            else:
                                res_data = {"brand": "UNK", "country": "UNK", "type": "UNK", "level": "UNK", "bank": "UNK"}

                            self.results[bin_code] = res_data
                            self.valid_count += 1
                            self.save_to_csv(bin_code, res_data)
                        elif response.status_code == 404:
                                self.results[bin_code] = {"brand": "N/A", "country": "N/A", "type": "INVALID", "level": "N/A", "bank": "N/A"}
                        elif response.status_code == 429:
                            # Rate limited - Mark as blocked so user knows
                            self.results[bin_code] = {"brand": "RATE", "country": "LIMIT", "type": "RETRY", "level": "429", "bank": "API BLOCKED IP"}
                        else:
                            # Failed request (timeout or other error)
                            self.results[bin_code] = {"brand": "ERROR", "country": "TIMEOUT", "type": "ERROR", "level": "ERR", "bank": "CHECK PROXY"}
                    
                    self.processed_count += 1
                    return # Success
                except Exception:
                    continue # Try next API
            
            # If all APIs failed for this proxy, remove it
            if not proxy_working and proxy:
                with self.lock:
                    if proxy in self.proxies:
                        self.proxies.remove(proxy)
            
            if not proxy:
                break

        # If all retries failed
        with self.lock:
            if bin_code not in self.results:
                self.results[bin_code] = {"brand": "ERROR", "country": "FAIL", "type": "ERROR", "level": "ERR", "bank": "ALL PROXIES DIED"}
        
        self.processed_count += 1

    def fetch_data(self):
        """Background worker to fetch BIN data"""
        # Determine workers based on proxies
        # If proxies available -> Use 150 threads (aggressive)
        # If no proxies -> Use 1 thread to respect rate limit (or user risks ban)
        workers = 150 if self.proxies else 1
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Convert to list to map, but check running status inside
            list(executor.map(self.check_single_bin, self.bin_list))

    def draw_ui(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # Colors
        BORDER = Fore.LIGHTBLUE_EX
        TITLE = Fore.LIGHTMAGENTA_EX
        HEADER_TXT = Fore.CYAN
        TEXT = Fore.WHITE
        SUCCESS = Fore.LIGHTGREEN_EX
        FAIL = Fore.LIGHTRED_EX
        PENDING = Fore.YELLOW
        
        # Header
        # Adjusted width to be more compact (approx 113 chars)
        UI_WIDTH = 113
        print(BORDER + "╔" + "═"*(UI_WIDTH-2) + "╗")
        title = "MASS BIN CHECK PREVIEW"
        print(BORDER + "║" + TITLE + title.center(UI_WIDTH-2) + BORDER + "║")
        
        # Page Info
        start_idx = (self.current_page - 1) * ROWS_PER_PAGE
        end_idx = min(start_idx + ROWS_PER_PAGE, len(self.bin_list))
        
        # Highlight stats
        valid_txt = f"{SUCCESS}{self.valid_count}{TEXT}"
        proxy_txt = f"{Fore.LIGHTCYAN_EX}{len(self.proxies)}{TEXT}"
        
        page_info = f"Page {self.current_page}/{self.total_pages} • Rows {start_idx+1}-{end_idx} • Valid: {valid_txt} • Proxies: {proxy_txt}"
        # Adjust center width calculation because escape codes add hidden length
        visible_length = len(f"Page {self.current_page}/{self.total_pages} • Rows {start_idx+1}-{end_idx} • Valid: {self.valid_count} • Proxies: {len(self.proxies)}")
        padding = (UI_WIDTH - 2 - visible_length) // 2
        
        print(BORDER + "║" + " " * padding + page_info + " " * (UI_WIDTH - 2 - visible_length - padding) + BORDER + "║")
        print(BORDER + "╚" + "═"*(UI_WIDTH-2) + "╝")

        # Table Header
        # BIN | BRAND | COUNTRY | TYPE | LEVEL | BANK
        header_fmt = "{:<8} | {:<15} | {:<25} | {:<10} | {:<10} | {:<30}"
        print(HEADER_TXT + header_fmt.format("BIN", "BRAND", "COUNTRY", "TYPE", "LEVEL", "BANK"))
        print(Fore.LIGHTBLACK_EX + "-" * UI_WIDTH)

        # Table Rows
        current_batch = self.bin_list[start_idx:end_idx]
        
        with self.lock:
            for bin_code in current_batch:
                info = self.results.get(bin_code)
                if info:
                    if info['type'] == 'INVALID':
                         row_color = FAIL
                         print(row_color + header_fmt.format(
                            bin_code, 
                            "INVALID", 
                            "N/A", 
                            "N/A", 
                            "N/A", 
                            "N/A"
                        ))
                    elif info['type'] == 'RETRY':
                         # Rate limit row
                         print(FAIL + header_fmt.format(
                            bin_code, 
                            "RATE LIMIT", 
                            "API BLOCK", 
                            "RETRY", 
                            "429", 
                            "Try Proxies/VPN"
                        ))
                    else:
                        # Success row with multi-colors
                        bin_c = Fore.LIGHTWHITE_EX
                        brand_c = Fore.LIGHTCYAN_EX
                        country_c = Fore.LIGHTYELLOW_EX
                        type_c = Fore.LIGHTGREEN_EX
                        level_c = Fore.LIGHTBLUE_EX
                        bank_c = Fore.WHITE
                        
                        country_display = self.abbreviate_country(info['country'])
                        
                        # Custom format for mixed colors
                        print(f"{bin_c}{bin_code:<8} {Fore.LIGHTBLACK_EX}| "
                              f"{brand_c}{info['brand'][:15]:<15} {Fore.LIGHTBLACK_EX}| "
                              f"{country_c}{country_display[:25]:<25} {Fore.LIGHTBLACK_EX}| "
                              f"{type_c}{info['type'][:10]:<10} {Fore.LIGHTBLACK_EX}| "
                              f"{level_c}{info.get('level', 'UNK')[:10]:<10} {Fore.LIGHTBLACK_EX}| "
                              f"{bank_c}{info['bank'][:30]}")
                else:
                    # Pending
                    print(PENDING + header_fmt.format(bin_code, "...", "...", "...", "...", "WAITING..."))

        # Progress Bar
        total = len(self.bin_list)
        if total > 0:
            percent = self.processed_count / total
            bar_len = 50
            filled = int(bar_len * percent)
            bar = "█" * filled + "-" * (bar_len - filled)
            print(f"\n{Fore.CYAN}Progress: [{bar}] {percent:.1%} ({self.processed_count}/{total})")

        # Footer
        print("\n" + Fore.LIGHTBLACK_EX + "[" + Fore.WHITE + "N" + Fore.LIGHTBLACK_EX + "] Next Page  " + 
              "[" + Fore.WHITE + "P" + Fore.LIGHTBLACK_EX + "] Prev Page  " + 
              "[" + Fore.WHITE + "Q" + Fore.LIGHTBLACK_EX + "] Quit: " + Style.RESET_ALL, end="")
        sys.stdout.flush()

    def run(self):
        # Start fetcher thread
        t = threading.Thread(target=self.fetch_data)
        t.daemon = True
        t.start()

        while self.running:
            self.draw_ui()
            
            # Non-blocking input handling for Windows to allow UI refresh
            if os.name == 'nt':
                import msvcrt
                # Wait up to 1 second for input, then refresh
                start_time = time.time()
                while time.time() - start_time < 1.0:
                    if msvcrt.kbhit():
                        ch = msvcrt.getch().decode('utf-8', errors='ignore').lower()
                        if ch == 'q':
                            self.running = False
                            return
                        elif ch == 'p':
                            if self.current_page > 1: self.current_page -= 1; break
                        elif ch == 'n':
                            if self.current_page < self.total_pages: self.current_page += 1; break
                    time.sleep(0.05)
            else:
                # Fallback for Linux/Mac (still blocking but functional)
                choice = input().strip().lower()
                if choice == 'q': self.running = False
                elif choice == 'p' and self.current_page > 1: self.current_page -= 1
                elif choice == 'n' or choice == '': 
                    if self.current_page < self.total_pages: self.current_page += 1

if __name__ == "__main__":
    # Check for file argument or default to 6bin.txt or ask user
    target_file = "6bin.txt"
    proxy_file = "proxy.txt"

    if len(sys.argv) > 1:
        target_file = sys.argv[1]
    
    if not os.path.exists(target_file):
        print(f"File {target_file} not found. Please create it or provide a file path.")
        target_file = input("Enter path to BIN file: ").strip().strip('"')
    
    # Check for proxy file
    if not os.path.exists(proxy_file):
         p_input = input("Enter path to Proxy file (Enter to skip): ").strip().strip('"')
         if p_input:
             proxy_file = p_input
         else:
             proxy_file = None

    if os.path.exists(target_file):
        app = BinCheckerTUI(target_file, proxy_file)
        app.run()
    else:
        print("File not found.")
