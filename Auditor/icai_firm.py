import os,re,csv
import pandas as pd
from playwright.sync_api import sync_playwright

EMAIL = "leiffowelloja-3076@yopmail.com"
PASSWORD = "*Dqy*cQQeEjS58"

INPUT_FILE="Auditor/data/profile_links_firm.csv"
OUTPUT_FILE="Auditor/data/firm_details.csv"

os.makedirs(os.path.dirname(OUTPUT_FILE),exist_ok=True)

if not os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE,"w",newline="",encoding="utf-8-sig") as f:
        csv.writer(f).writerow(["Profile URL","Firm Name","Mobile","Website","Email","Constitution Date","No of Partners","Location","City","State","Country","Specialization","City Preference","Social Links"])

urls=pd.read_csv(INPUT_FILE).iloc[:,0].dropna().tolist()

with sync_playwright() as p:
    browser=p.chromium.launch(headless=False,slow_mo=300)
    page=browser.new_page()
    page.goto("https://caconnect.icai.org/login")
    page.fill("input[type=email]",EMAIL)
    page.fill("input[type=password]",PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(5000)

    for url in urls:
        try:
            page.goto(url,wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            details={}
            blocks=page.locator("div.height-450").first.locator("div.col-md-6")
            for i in range(blocks.count()):
                try:
                    b=blocks.nth(i)
                    k=b.locator("h5").inner_text().strip()
                    if not k: continue
                    details[k]=b.inner_text().replace(k,"").strip()
                except:
                    pass

            try:
                website=page.locator("//h5[contains(text(),'Website')]/following-sibling::p/a").get_attribute("href") or ""
            except:
                website=""

            location=details.get("Location","")
            try:
                h=page.locator("section.profile-head h4").inner_text()
                h=re.sub(r"\d{10,}.*","",h).strip()
                if h: location=h
            except:
                pass

            parts=[x.strip() for x in location.split(",") if x.strip()]
            city=parts[0].title() if len(parts)>0 else ""
            state=parts[1].title() if len(parts)>1 else ""
            country=parts[2].upper() if len(parts)>2 else ""

            specs=[x.strip() for x in page.locator("div.scr button.special-btn").all_inner_texts() if x.strip()]
            prefs=list(dict.fromkeys([x.strip() for x in page.locator("div.height-160 button.special-btn").all_inner_texts() if x.strip()]))

            social=[]
            a=page.locator("div.stmedia a")
            for i in range(a.count()):
                social.append(f"{a.nth(i).inner_text().replace('•','').strip()}: {a.nth(i).get_attribute('href') or ''}")

            with open(OUTPUT_FILE,"a",newline="",encoding="utf-8-sig") as f:
                csv.writer(f).writerow([
                    url,
                    details.get("Firm Name","").title(),
                    details.get("Mobile",""),
                    website.lower(),
                    details.get("Email","").lower(),
                    details.get("Constitution Date",""),
                    details.get("No of Partners",""),
                    location.title(),
                    city,state,country,
                    ", ".join(specs),
                    ", ".join(prefs),
                    ", ".join(social)
                ])
        except Exception as e:
            print(e)
    browser.close()

print("Done")