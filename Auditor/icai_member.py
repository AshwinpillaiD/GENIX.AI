import os
import re
import csv
import pandas as pd
from playwright.sync_api import sync_playwright

EMAIL = "leiffowelloja-3076@yopmail.com"
PASSWORD = "*Dqy*cQQeEjS58"

INPUT_FILE = "Auditor/data/profile_links_CA.csv"
OUTPUT_FILE = "Auditor/data/member_details.csv"

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

if not os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow([
            "Profile URL","Member Name","Mobile","Website","Email",
            "Location","City","State","Country",
            "Specialization","City Preference","Social Links"
        ])

df = pd.read_csv(INPUT_FILE)
urls = df.iloc[:,0].dropna().tolist()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context()
    page = context.new_page()

    print("Opening login page...")
    page.goto("https://caconnect.icai.org/login", wait_until="domcontentloaded")
    page.fill("input[type='email']", EMAIL)
    page.fill("input[type='password']", PASSWORD)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(5000)
    print("Login successful")

    for idx, url in enumerate(urls, start=1):
        print(f"[{idx}/{len(urls)}] {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)

            details = {}

            blocks = page.locator("div.height-450").first.locator("div.col-md-6")
            for i in range(blocks.count()):
                try:
                    b = blocks.nth(i)
                    key = b.locator("h5").inner_text().strip()
                    if not key:
                        continue
                    val = b.inner_text().replace(key, "").strip()
                    details[key] = val
                except:
                    pass

            try:
                website = page.locator("//h5[contains(text(),'Website')]/following-sibling::p/a").get_attribute("href") or ""
            except:
                website = ""

            specialization = [x.strip() for x in page.locator("div.scr button.special-btn").all_inner_texts() if x.strip()]
            city_pref = [x.strip() for x in page.locator("div.height-160 button.special-btn").all_inner_texts() if x.strip()]

            social = []
            links = page.locator("div.stmedia a")
            for i in range(links.count()):
                name = links.nth(i).inner_text().replace("•","").strip()
                href = links.nth(i).get_attribute("href") or ""
                social.append(f"{name}: {href}")

            location = details.get("Location","").strip()
            city = state = country = ""

            try:
                header = page.locator("section.profile-head h4").inner_text()
                header = re.sub(r"\d{10,}.*","",header).strip()
                if header:
                    location = header
            except:
                pass

            parts = [p.strip() for p in location.split(",") if p.strip()]
            if len(parts) > 0: city = parts[0]
            if len(parts) > 1: state = parts[1]
            if len(parts) > 2: country = parts[2]

            email = details.get("Email", "").strip().lower()
            row = [
                url,
                details.get("Member Name",""),
                details.get("Mobile",""),
                website,
                email,
                location,
                city,
                state,
                country,
                ", ".join(specialization),
                ", ".join(city_pref),
                ", ".join(social)
            ]

            with open(OUTPUT_FILE,"a",newline="",encoding="utf-8-sig") as f:
                csv.writer(f).writerow(row)

            print("Saved:", details.get("Member Name",""))

        except Exception as e:
            print("Error:", e)
            with open(OUTPUT_FILE,"a",newline="",encoding="utf-8-sig") as f:
                csv.writer(f).writerow([url,"","","","","","","","","","",""])

    browser.close()

print("Completed")
print("Output:", OUTPUT_FILE)