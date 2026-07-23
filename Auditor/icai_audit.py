# from playwright.sync_api import sync_playwright

# with sync_playwright() as p:
#     browser = p.chromium.launch(headless=False)
#     page = browser.new_page()

#     try:
#         response = page.goto(
#             "https://caconnect.icai.org/trending-member-firm/1",
#             wait_until="domcontentloaded",
#             timeout=60000
#         )

#         if response:
#             print("Status:", response.status)
#             print("URL:", response.url)
#             page.reload(wait_until="domcontentloaded")

#     except Exception as e:
#         print(e)

#     page.wait_for_timeout(80000)

from playwright.sync_api import sync_playwright
import csv
import time
URL = "https://caconnect.icai.org/trending-member-firm/2"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    response = page.goto(
        URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    # Refresh (your site needs it)
    page.reload(wait_until="domcontentloaded")
    time.sleep(100)
    page.wait_for_timeout(5000)

    # Get all profile links
    # links = page.locator("a[href*='/memberProfile/']")  # memberProfile
    links = page.locator("a[href*='/firmProfile/']")      #firmProfile

    print("Total Profiles:", links.count())

    with open("profile_links.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Profile URL"])

        for i in range(links.count()):
            href = links.nth(i).get_attribute("href")

            if href:
                if href.startswith("/"):
                    href = "https://caconnect.icai.org" + href

                print(href)
                writer.writerow([href])
    time.sleep(200)
    browser.close()

print("Saved to profile_links.csv")