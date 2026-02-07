import requests
import os
import sys
import time
from colorama import Fore, Style, init

# Khởi tạo màu sắc
init(autoreset=True)

def clear():
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')

def banner():
    print(Fore.CYAN + """
    ██████╗ ██╗███╗   ██╗    ██████╗██╗  ██╗███████╗ ██████╗██╗  ██╗███████╗██████╗ 
    ██╔══██╗██║████╗  ██║   ██╔════╝██║  ██║██╔════╝██╔════╝██║ ██╔╝██╔════╝██╔══██╗
    ██████╔╝██║██╔██╗ ██║   ██║     ███████║█████╗  ██║     █████╔╝ █████╗  ██████╔╝
    ██╔══██╗██║██║╚██╗██║   ██║     ██╔══██║██╔══╝  ██║     ██╔═██╗ ██╔══╝  ██╔══██╗
    ██████╔╝██║██║ ╚████║██╗╚██████╗██║  ██║███████╗╚██████╗██║  ██╗███████╗██║  ██║
    ╚═════╝ ╚═╝╚═╝  ╚═══╝╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
    """ + Style.RESET_ALL)
    print(Fore.YELLOW + "    [+] BIN Lookup Tool - Worldwide Bank Identifier")
    print(Fore.YELLOW + "    [+] Coded by Gemini Code Assist")
    print(Fore.WHITE + "-" * 70)

def get_bin_info(bin_code, proxies=None):
    # Loại bỏ khoảng trắng nếu có và chỉ lấy 6 số đầu
    bin_code = bin_code.replace(" ", "").replace("-", "")[:6]
    
    if not bin_code.isdigit() or len(bin_code) < 6:
        print(Fore.RED + "[!] Vui lòng nhập ít nhất 6 chữ số.")
        return

    url = f"https://lookup.binlist.net/{bin_code}"
    headers = {
        'Accept-Version': '3',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    print(Fore.CYAN + f"[*] Đang tra cứu BIN: {bin_code}...")
    
    try:
        response = requests.get(url, headers=headers, proxies=proxies, timeout=20)
        
        if response.status_code == 404:
            print(Fore.RED + "[!] Không tìm thấy thông tin cho BIN này.")
            return
        elif response.status_code == 429:
            print(Fore.RED + "[!] Quá nhiều yêu cầu (Rate Limit). Vui lòng đợi một chút.")
            return
        
        data = response.json()
        
        # Trích xuất thông tin
        scheme = data.get('scheme', 'Unknown').upper()
        brand = data.get('brand', 'Unknown').upper()
        card_type = data.get('type', 'Unknown').upper()
        prepaid = data.get('prepaid')
        
        country_data = data.get('country', {})
        country_name = country_data.get('name', 'Unknown')
        country_emoji = country_data.get('emoji', '')
        currency = country_data.get('currency', 'Unknown')
        
        bank_data = data.get('bank', {})
        bank_name = bank_data.get('name', 'Unknown')
        bank_url = bank_data.get('url', 'N/A')
        bank_phone = bank_data.get('phone', 'N/A')

        # Hiển thị kết quả
        print(Fore.GREEN + "\n[+] KẾT QUẢ TRA CỨU:")
        print(Fore.WHITE + "-" * 40)
        print(f"{Fore.LIGHTYELLOW_EX}Ngân hàng (Bank): {Fore.WHITE}{bank_name}")
        print(f"{Fore.LIGHTYELLOW_EX}Quốc gia (Country): {Fore.WHITE}{country_name} {country_emoji}")
        print(f"{Fore.LIGHTYELLOW_EX}Loại thẻ (Type): {Fore.WHITE}{card_type}")
        print(f"{Fore.LIGHTYELLOW_EX}Tổ chức (Scheme): {Fore.WHITE}{scheme}")
        print(f"{Fore.LIGHTYELLOW_EX}Thương hiệu (Brand): {Fore.WHITE}{brand}")
        print(f"{Fore.LIGHTYELLOW_EX}Trả trước (Prepaid): {Fore.WHITE}{prepaid}")
        print(f"{Fore.LIGHTYELLOW_EX}Tiền tệ (Currency): {Fore.WHITE}{currency}")
        print(f"{Fore.LIGHTYELLOW_EX}Website: {Fore.WHITE}{bank_url}")
        print(f"{Fore.LIGHTYELLOW_EX}Phone: {Fore.WHITE}{bank_phone}")
        print(Fore.WHITE + "-" * 40 + "\n")

    except Exception as e:
        print(Fore.RED + f"[!] Lỗi kết nối: {str(e)}")

def main():
    clear()
    banner()
    
    p = input(Fore.LIGHTBLUE_EX + "Proxy (host:port:user:pass) [Enter=Skip]: " + Style.RESET_ALL).strip()
    
    proxies = None
    if p:
        if p.count(":") == 3:
            # Format: host:port:user:pass
            parts = p.split(':')
            fmt = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            proxies = {"http": fmt, "https": fmt}
        elif p.count(":") == 1:
            # Format: host:port
            proxies = {"http": f"http://{p}", "https": f"http://{p}"}
        else:
            print(Fore.RED + "[!] Định dạng proxy không hợp lệ, sẽ chạy không proxy.")

    while True:
        try:
            user_input = input(Fore.LIGHTBLUE_EX + "Nhập 6 số đầu của thẻ hoặc tên file (ví dụ: 6bin.txt) (hoặc 'exit' để thoát): " + Style.RESET_ALL).strip().strip('"')
            
            if user_input.lower() in ['exit', 'quit']:
                print(Fore.GREEN + "Tạm biệt!")
                sys.exit()
            
            if os.path.isfile(user_input):
                try:
                    with open(user_input, "r", encoding="utf-8") as f:
                        bins = [line.strip() for line in f if line.strip()]
                    print(Fore.YELLOW + f"[+] Đã tải {len(bins)} BIN từ file.")
                    for bin_code in bins:
                        get_bin_info(bin_code, proxies)
                        time.sleep(2) # Delay để tránh rate limit của API
                except Exception as e:
                    print(Fore.RED + f"[!] Lỗi đọc file: {e}")
            
            elif user_input:
                get_bin_info(user_input, proxies)
        except KeyboardInterrupt:
            print(Fore.RED + "\n[!] Đã dừng tool.")
            sys.exit()

if __name__ == "__main__":
    main()