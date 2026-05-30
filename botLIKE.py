import time
import re
import io
import sys
try:
    import pytesseract
    from PIL import Image
except ImportError:
    print("Please install missing modules:\n  pip install pytesseract Pillow")
    print("And ensure Tesseract is installed on your OS:\n  sudo apt install tesseract-ocr")
    sys.exit(1)

from playwright.sync_api import sync_playwright

def _check_and_close_ad(page):
    try:
        try:
            if "google" in page.url.lower() or "vignette" in page.url.lower():
                print(f"[!] Google ad detected in URL ({page.url}). Trying to close...")
        except Exception:
            pass

        # 1. First, handle the prompt to start viewing the ad
        try:
            ad_prompt = page.locator("text='View a short ad'")
            for i in range(ad_prompt.count()):
                if ad_prompt.nth(i).is_visible():
                    print("[*] Clicking 'View a short ad' automatically...")
                    ad_prompt.nth(i).click(timeout=5000, force=True)
                    print("[*] Ad opened. Waiting exactly 40 seconds for the ad to finish...")
                    time.sleep(40)
                    break
        except Exception:
            pass

        # 2. Check main page for 'Close' or dismiss buttons
        close_btn = page.locator("text=Close")
        for i in range(close_btn.count()):
            if close_btn.nth(i).is_visible():
                print("[*] Found 'Close' button on main page! Clicking it...")
                close_btn.nth(i).click(timeout=5000, force=True)
                time.sleep(2)
                
        dismiss_btn = page.locator("#dismiss-button")
        for i in range(dismiss_btn.count()):
            if dismiss_btn.nth(i).is_visible():
                print("[*] Found main page dismiss-button! Clicking it...")
                dismiss_btn.nth(i).click(timeout=5000, force=True)
                time.sleep(2)

        # 3. Check inside all iframes for 'Close' or dismissal buttons
        for frame in page.frames:
            try:
                f_btn = frame.locator("text=Close")
                for i in range(f_btn.count()):
                    if f_btn.nth(i).is_visible():
                        print("[*] Found 'Close' button inside an iframe! Clicking it...")
                        f_btn.nth(i).click(timeout=5000, force=True)
                        time.sleep(2)
                        
                f_dismiss = frame.locator("#dismiss-button")
                for i in range(f_dismiss.count()):
                    if f_dismiss.nth(i).is_visible():
                        print("[*] Found 'dismiss-button' inside an iframe! Clicking it...")
                        f_dismiss.nth(i).click(timeout=5000, force=True)
                        time.sleep(2)
            except Exception:
                pass
    except Exception as e:
        print(f"[-] Error while checking for ad: {e}")

def solve_captcha(page):
    print("[*] Checking for CAPTCHA...")
    while True:
        # Stop solving if the main menu is visible
        if page.locator("div.row").count() > 0 and page.locator("div.row").first.is_visible():
            print("[+] Logged in / CAPTCHA passed!")
            break
            
        # --- Handle Overlays / Popups ---
        if page.locator("text=Captcha code is incorrect").is_visible() or page.locator("text=incorrect").is_visible():
            print("[-] Incorrect CAPTCHA popup detected! Clicking Close and refreshing...")
            try:
                page.locator("text=Close").first.click(timeout=3000)
            except:
                pass
            time.sleep(1)
            page.reload()
            time.sleep(3)
            continue
            
        if page.locator("text=Unlock more content").is_visible() or page.locator("text=View a short ad").is_visible():
            print("[!] Ad pop-up detected.")
            _check_and_close_ad(page)
            time.sleep(2)
        # --------------------------------
        
        captcha_img = page.locator("img").first
        if not captcha_img.is_visible():
            time.sleep(1)
            continue
            
        try:
            print("[*] Found CAPTCHA image. Capturing for OCR...")
            img_bytes = captcha_img.screenshot()
            img = Image.open(io.BytesIO(img_bytes))
            img = img.convert('L')
            
            tex_ocr = pytesseract.image_to_string(img).strip()
            tex_ocr = re.sub(r'[^a-zA-Z0-9]', '', tex_ocr)
            
            if len(tex_ocr) < 3:
                print(f"[-] OCR failed or too short ('{tex_ocr}'). Reloading...")
                page.reload()
                time.sleep(3)
                continue
                
            print(f"[+] OCR extracted: '{tex_ocr}'. Submitting...")
            
            captcha_input = page.locator("input[type='text']:visible").first
            captcha_input.fill(tex_ocr)
            
            # Wait a little bit so it doesn't instantly submit (recording human delay)
            print("[*] Simulating human delay... waiting 3 seconds before hitting submit!")
            time.sleep(3)
            
            # Recheck for the ad popup just in case it popped up during our sleep
            if page.locator("text='Unlock more content'").is_visible():
                print("[!] Ad pop-up interrupted sleep! Handling ad...")
                continue
                
            submit_btn = page.locator("button.btn:visible").first
            submit_btn.click()
            time.sleep(3)
            
            # Immediately check if there is an error message
            if page.locator("text=incorrect").is_visible():
                print("[-] Captcha code was incorrect immediately after submit! Reloading...")
                try:
                    page.locator("text=Close").first.click(timeout=3000)
                except:
                    pass
                page.reload(wait_until="domcontentloaded")
                time.sleep(3)
                continue
                
            _check_and_close_ad(page)
            
        except Exception as e:
            if "tesseract is not installed" in str(e):
                print("[-] Tesseract OS package missing! Please type the CAPTCHA manually in the browser window.")
                print("    (To automate this, open a new terminal and run: sudo apt install tesseract-ocr)")
                # Wait for manual login
                page.wait_for_selector("div.row", timeout=120000)
                print("[+] Logged in / CAPTCHA passed manually!")
                break
            print(f"[-] CAPTCHA error: {e}")
            time.sleep(2)

def run(playwright):
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
    )
    
    page = context.new_page()
    page.goto("https://zefoy.com/")
    
    solve_captcha(page)

    service_name = "Hearts"  
    print(f"[*] Opening the '{service_name}' service...")

    try:
        # Use the specific class for the Hearts button
        btn_locator = page.locator("button.t-hearts-button")
        btn_locator.click(timeout=10000)
        print("[*] Clicked Hearts! Waiting 5 seconds before proceeding...")
        time.sleep(5)
        _check_and_close_ad(page)
    except Exception as e:
        print(f"[-] Could not find '{service_name}' button. Are we on the right page? Error: {e}")
        browser.close()
        return
    
    visible_input = page.locator("input[type='search']:visible")
    visible_input.wait_for(state="visible", timeout=30000)
    
    tiktok_url = "https://www.tiktok.com/@msfahmeed/video/7481443944979631366"
    visible_input.fill(tiktok_url)
    
    visible_search_btn = page.locator("button.btn-primary:visible")
    time.sleep(2)
    _check_and_close_ad(page)
    try:
        visible_search_btn.click(timeout=5000, force=True)
    except Exception:
        pass
    print("[*] Submitted the URL. Reading Zefoy's response...")
    time.sleep(2)
    _check_and_close_ad(page)
    
    check_count = 0
    while True:
        time.sleep(4) 
        
        # 1. Parse for Cooldown Timer
        # Example text: "Please wait 0 minute(s) 54 second(s) before trying again."
        active_panel = page.locator("div.card:visible").inner_text()
        
        if "views are sending" in active_panel.lower() or "hearts are sending" in active_panel.lower():
            print("[*] Actions are currently sending... waiting.")
            check_count = 0
            continue
            
        cooldown_match = re.search(r'wait.*?(\d+).*?minute.*?(\d+).*?second', active_panel, re.IGNORECASE)
        cooldown_match_sec = re.search(r'wait.*?(\d+).*?second', active_panel, re.IGNORECASE)
        
        if cooldown_match:
            mins, secs = int(cooldown_match.group(1)), int(cooldown_match.group(2))
            total_sleep = (mins * 60) + secs
            print(f"[!] Website is on cooldown... Sleeping for {total_sleep} seconds ({mins}m {secs}s).")
            
            time.sleep(total_sleep + 2) 
            print("[*] Cooldown finished! Resubmitting search...")
            check_count = 0
            time.sleep(2)
            _check_and_close_ad(page)
            try:
                visible_search_btn.click(timeout=5000, force=True)
            except Exception:
                pass
            time.sleep(2)
            _check_and_close_ad(page)
            continue
        elif cooldown_match_sec and "minute" not in active_panel.lower():
            secs = int(cooldown_match_sec.group(1))
            print(f"[!] Website is on short cooldown... Sleeping for {secs} seconds.")
            time.sleep(secs + 2)
            check_count = 0
            time.sleep(2)
            _check_and_close_ad(page)
            try:
                visible_search_btn.click(timeout=5000, force=True)
            except Exception:
                pass
            time.sleep(2)
            _check_and_close_ad(page)
            continue
            
        # 2. Look for the target action button
        try:
            action_btn = page.locator("form button.btn:visible").nth(1)
            
            if action_btn.is_visible() and "search" not in action_btn.inner_text().lower():
                b_text = action_btn.inner_text().strip()
                print(f"[+] Found target action button: '{b_text}'. Clicking it!")
                time.sleep(2)
                _check_and_close_ad(page)
                try:
                    action_btn.click(timeout=5000, force=True)
                except Exception:
                    pass
                print("[*] Action triggered! Waiting 10s for success message...")
                time.sleep(10)
                _check_and_close_ad(page)
                check_count = 0
                continue
        except Exception:
            pass # No second button found yet
            
        print("[*] Checking state... (no cooldown or action button found yet)")
        check_count += 1
        if check_count >= 3:
            print("[*] No state change after 3 checks. Re-clicking search button...")
            time.sleep(2)
            _check_and_close_ad(page)
            try:
                visible_search_btn.click(timeout=5000, force=True)
            except Exception:
                pass
            _check_and_close_ad(page)
            check_count = 0

    print("[+] Automation complete. Leaving browser open.")
    # Keep the process alive so the browser doesn't automatically close
    while True:
        time.sleep(1)

if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
