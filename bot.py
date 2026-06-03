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


def _close_vignette_ad(page):
    """Handles the zefoy.com/#google_vignette overlay ad."""
    try:
        if "#google_vignette" not in page.url:
            return
    except Exception:
        return

    print("[!] Google vignette ad detected. Closing...")
    for _ in range(30):
        try:
            for selector in ["text=Close", "[aria-label='Close']", ".dismiss-button"]:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=500):
                    btn.click(timeout=3000, force=True)
                    print("[+] Vignette ad closed.")
                    time.sleep(1)
                    return
        except Exception:
            pass
        time.sleep(1)
    print("[-] Could not close vignette ad.")


def _close_fullscreen_ad(page):
    """Handles the zefoy.com/#goog_fullscreen_ad page."""
    try:
        if "#goog_fullscreen_ad" not in page.url:
            return
    except Exception:
        return

    print("[!] Fullscreen ad page detected. Waiting for Close button...")

    for _ in range(120):
        try:
            for selector in [
                "div.continue-prompt-text",
                "#dismiss-button",
                "text=Close",
                "[aria-label='Close']",
            ]:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=500):
                    btn.click(timeout=3000, force=True)
                    print(f"[+] Clicked Close on fullscreen ad via '{selector}'")
                    time.sleep(2)
                    try:
                        page.wait_for_url("*zefoy.com*", timeout=8000)
                    except Exception:
                        pass
                    print("[+] Back on Zefoy main page.")
                    return
        except Exception:
            pass

        try:
            for frame in page.frames:
                for selector in [
                    "div.continue-prompt-text",
                    "#dismiss-button",
                    "text=Close",
                ]:
                    try:
                        btn = frame.locator(selector).first
                        if btn.is_visible(timeout=500):
                            btn.click(timeout=3000, force=True)
                            print(f"[+] Clicked Close in iframe via '{selector}'")
                            time.sleep(2)
                            try:
                                page.wait_for_url("*zefoy.com*", timeout=8000)
                            except Exception:
                                pass
                            print("[+] Back on Zefoy main page.")
                            return
                    except Exception:
                        pass
        except Exception:
            pass

        time.sleep(1)

    print("[-] Timed out waiting for fullscreen ad Close button.")


def _close_all_ads(page):
    """Call this before every action — closes any ad type."""
    _close_vignette_ad(page)
    _close_fullscreen_ad(page)


def _dismiss_unlock_modal(page):
    """Blocks until the 'Unlock more content' modal is gone."""
    _close_all_ads(page)

    try:
        if not page.locator("text=Unlock more content").is_visible(timeout=4000):
            return
    except Exception:
        return

    print("[!] 'Unlock more content' modal detected. Clicking the ad play button...")
    print("[*] Waiting 5 seconds for modal to fully load...")
    time.sleep(5)

    clicked = False

    for selector in [
        "button.fc-rewarded-ad-button",
        "button.fc-list-item-button",
        ".fc-list-item-button",
        ".fc-rewarded-ad-button",
        "[class*='fc-rewarded-ad-button']",
        "[class*='fc-list-item-button']",
    ]:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=2000):
                btn.click(timeout=3000, force=True)
                clicked = True
                print(f"[*] Clicked ad trigger via '{selector}'")
                break
        except Exception:
            pass

    if not clicked:
        for frame in page.frames:
            for selector in [
                "button.fc-rewarded-ad-button",
                "button.fc-list-item-button",
                "[class*='fc-rewarded']",
            ]:
                try:
                    btn = frame.locator(selector).first
                    if btn.is_visible(timeout=1500):
                        btn.click(timeout=3000, force=True)
                        clicked = True
                        print(f"[*] Clicked ad trigger in iframe via '{selector}'")
                        break
                except Exception:
                    pass
            if clicked:
                break

    if not clicked:
        print("[-] Could not click ad trigger. Trying JS click as last resort...")
        try:
            page.evaluate("""
                const btn = document.querySelector('button.fc-rewarded-ad-button')
                         || document.querySelector('button.fc-list-item-button')
                         || document.querySelector('[class*="fc-rewarded"]');
                if (btn) btn.click();
            """)
            clicked = True
            print("[*] JS click executed.")
        except Exception as e:
            print(f"[-] JS click failed: {e}")

    print("[*] Waiting 45 seconds for ad to play through...")
    time.sleep(45)

    _close_all_ads(page)

    print("[*] Ad done. Looking for close button...")
    for attempt in range(10):
        _close_all_ads(page)

        dismissed = False

        for selector in [
            "button.fc-close",
            ".fc-close-button",
            "[class*='fc-close']",
            "button[aria-label='Close']",
            "text=Close",
            "#dismiss-button",
            "text=Done",
            "text=Continue",
            "div.continue-prompt-text",
        ]:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click(timeout=3000, force=True)
                    print(f"[+] Dismissed modal via '{selector}'")
                    dismissed = True
                    time.sleep(1)
                    break
            except Exception:
                pass

        if not dismissed:
            for frame in page.frames:
                for selector in [
                    "button.fc-close", ".fc-close-button",
                    "[class*='fc-close']", "text=Close",
                    "#dismiss-button", "text=Done",
                    "div.continue-prompt-text",
                ]:
                    try:
                        btn = frame.locator(selector).first
                        if btn.is_visible(timeout=1000):
                            btn.click(timeout=3000, force=True)
                            print(f"[+] Dismissed modal in iframe via '{selector}'")
                            dismissed = True
                            time.sleep(1)
                            break
                    except Exception:
                        pass
                if dismissed:
                    break

        try:
            if not page.locator("text=Unlock more content").is_visible(timeout=2000):
                print("[+] Modal fully dismissed!")
                return
        except Exception:
            return

        print(f"[*] Modal still present, retry {attempt + 1}/10...")
        time.sleep(2)

    print("[-] Could not dismiss modal after 10 attempts. Continuing anyway.")


def solve_captcha(page):
    print("[*] Checking for CAPTCHA...")
    while True:
        _close_all_ads(page)

        if page.locator("div.row").count() > 0 and page.locator("div.row").first.is_visible():
            if not page.locator("input#captchatoken").is_visible(timeout=1000):
                print("[+] Logged in / CAPTCHA passed!")
                break

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
            print("[!] Ad pop-up detected during CAPTCHA phase.")
            _dismiss_unlock_modal(page)
            time.sleep(2)

        captcha_img = page.locator("img").first
        if not captcha_img.is_visible():
            time.sleep(1)
            continue

        try:
            print("[*] Found CAPTCHA image. Capturing for OCR...")
            img_bytes = captcha_img.screenshot()
            img = Image.open(io.BytesIO(img_bytes))
            img = img.convert('L')

            tex_ocr = pytesseract.image_to_string(img, config='--psm 8').strip()
            tex_ocr = re.sub(r'[^a-zA-Z0-9]', '', tex_ocr)
            if len(tex_ocr) < 3:
                tex_ocr = pytesseract.image_to_string(img, config='--psm 6').strip()
                tex_ocr = re.sub(r'[^a-zA-Z0-9]', '', tex_ocr)

            if len(tex_ocr) < 3:
                print(f"[-] OCR failed or too short ('{tex_ocr}'). Reloading...")
                page.reload()
                time.sleep(3)
                continue

            print(f"[+] OCR extracted: '{tex_ocr}'. Submitting...")

            captcha_input = page.locator("input#captchatoken").first
            captcha_input.wait_for(state="visible", timeout=5000)
            tex_ocr = re.sub(r'[^a-z]', '', tex_ocr.lower())
            if len(tex_ocr) < 3:
                print(f"[-] OCR result invalid after lowercase filter ('{tex_ocr}'). Reloading...")
                page.reload()
                time.sleep(3)
                continue

            print(f"[+] Cleaned OCR: '{tex_ocr}'. Filling input via JS...")
            page.evaluate(f"""
                const inp = document.querySelector('input#captchatoken');
                if (inp) {{
                    inp.value = '{tex_ocr}';
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            """)
            time.sleep(0.5)

            actual_val = page.eval_on_selector('input#captchatoken', 'el => el.value')
            print(f"[*] Input value after JS fill: '{actual_val}'")
            if not actual_val:
                print("[-] JS fill failed, trying Playwright fill as fallback...")
                captcha_input.click()
                time.sleep(0.3)
                captcha_input.fill(tex_ocr)
                time.sleep(0.3)

            print("[*] Simulating human delay... waiting 3 seconds before hitting submit!")
            time.sleep(3)

            if page.locator("text=Unlock more content").is_visible():
                print("[!] Ad pop-up interrupted sleep! Handling ad...")
                _dismiss_unlock_modal(page)
                continue

            submit_btn = page.locator("button.btn:visible").first
            submit_btn.click()
            time.sleep(3)

            if page.locator("text=incorrect").is_visible():
                print("[-] Captcha code was incorrect immediately after submit! Reloading...")
                try:
                    page.locator("text=Close").first.click(timeout=3000)
                except:
                    pass
                page.reload(wait_until="domcontentloaded")
                time.sleep(3)
                continue

            _dismiss_unlock_modal(page)

        except Exception as e:
            if "tesseract is not installed" in str(e):
                print("[-] Tesseract OS package missing! Please type the CAPTCHA manually in the browser window.")
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

    print("[*] Checking for post-login ad modal...")
    _dismiss_unlock_modal(page)
    _close_all_ads(page)

    service_name = "Views"
    print(f"[*] Opening the '{service_name}' service...")

    for attempt in range(5):
        _dismiss_unlock_modal(page)
        _close_all_ads(page)

        if page.locator("input#captchatoken").is_visible(timeout=2000):
            print("[!] Page reset to CAPTCHA after ad. Re-solving...")
            solve_captcha(page)
            _dismiss_unlock_modal(page)
            _close_all_ads(page)

        try:
            btn_locator = page.locator("button.t-views-button")
            btn_locator.wait_for(state="visible", timeout=8000)
            btn_locator.click(timeout=5000, force=True)
            print("[*] Clicked Views! Waiting 3 seconds...")
            time.sleep(3)
            _dismiss_unlock_modal(page)
            _close_all_ads(page)
            print("[+] Views service opened.")
            break
        except Exception as e:
            print(f"[-] Attempt {attempt + 1}/5 failed: {e}")
            if attempt == 4:
                print("[-] Could not open Views after 5 attempts. Exiting.")
                browser.close()
                return
            time.sleep(2)

    visible_input = page.locator("input[type='search']:visible")
    visible_input.wait_for(state="visible", timeout=30000)

    tiktok_url = "https://www.tiktok.com/@msfahmeed/video/7481443944979631366"
    visible_input.fill(tiktok_url)

    visible_search_btn = page.locator("button.btn-primary:visible")
    time.sleep(2)
    _dismiss_unlock_modal(page)
    _close_all_ads(page)
    try:
        visible_search_btn.click(timeout=5000, force=True)
    except Exception:
        pass
    print("[*] Submitted the URL. Reading Zefoy's response...")
    time.sleep(2)
    _dismiss_unlock_modal(page)
    _close_all_ads(page)

    check_count = 0
    while True:
        time.sleep(4)
        _close_all_ads(page)

        if page.locator("input#captchatoken").is_visible(timeout=1000):
            print("[!] Session reset to CAPTCHA! Re-solving...")
            solve_captcha(page)
            _dismiss_unlock_modal(page)
            _close_all_ads(page)
            visible_input.fill(tiktok_url)
            try:
                visible_search_btn.click(timeout=5000, force=True)
            except Exception:
                pass
            continue

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
            print(f"[!] Cooldown: sleeping {total_sleep}s ({mins}m {secs}s).")
            time.sleep(total_sleep + 2)
            print("[*] Cooldown finished! Resubmitting...")
            check_count = 0
            time.sleep(2)
            _dismiss_unlock_modal(page)
            _close_all_ads(page)
            try:
                visible_search_btn.click(timeout=5000, force=True)
            except Exception:
                pass
            time.sleep(2)
            _dismiss_unlock_modal(page)
            _close_all_ads(page)
            continue

        elif cooldown_match_sec and "minute" not in active_panel.lower():
            secs = int(cooldown_match_sec.group(1))
            print(f"[!] Short cooldown: sleeping {secs}s.")
            time.sleep(secs + 2)
            check_count = 0
            time.sleep(2)
            _dismiss_unlock_modal(page)
            _close_all_ads(page)
            try:
                visible_search_btn.click(timeout=5000, force=True)
            except Exception:
                pass
            time.sleep(2)
            _dismiss_unlock_modal(page)
            _close_all_ads(page)
            continue

        try:
            action_btn = page.locator("form button.btn:visible").nth(1)
            if action_btn.is_visible() and "search" not in action_btn.inner_text().lower():
                b_text = action_btn.inner_text().strip()
                print(f"[+] Found action button: '{b_text}'. Clicking!")
                time.sleep(2)
                _dismiss_unlock_modal(page)
                _close_all_ads(page)
                try:
                    action_btn.click(timeout=5000, force=True)
                except Exception:
                    pass
                print("[*] Action triggered! Waiting 10s...")
                time.sleep(10)
                _dismiss_unlock_modal(page)
                _close_all_ads(page)
                check_count = 0
                continue
        except Exception:
            pass

        print("[*] No cooldown or action button found yet.")
        check_count += 1
        if check_count >= 3:
            print("[*] No state change after 3 checks. Re-clicking search...")
            time.sleep(2)
            _dismiss_unlock_modal(page)
            _close_all_ads(page)
            try:
                visible_search_btn.click(timeout=5000, force=True)
            except Exception:
                pass
            _dismiss_unlock_modal(page)
            _close_all_ads(page)
            check_count = 0

    print("[+] Automation complete.")
    while True:
        time.sleep(1)


if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)

