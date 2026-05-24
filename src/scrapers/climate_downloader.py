from playwright.sync_api import sync_playwright
import requests
import time

def document_downloader():
    url = "https://www.weathersa.co.za/home/recentclimate"
    with sync_playwright() as p:
        headless = False
        browser = p.chromium.launch(headless=headless)

        #open tab
        page = browser.new_page()
        page.goto(url)

        #get daily rainfall data from weather SA
        with page.context.expect_page() as new_page:
            page.click("text=Daily Rainfall")
        
        new_page = new_page.value
        page.wait_for_load_state("networkidle")
        pdf_URL = new_page.url
        print("PDF URL: {pdf_URL}")

        #Download the pdf
        response = requests.get(pdf_URL, verify=False)
        with open("src/resources/SA-rain-data.pdf", "wb") as file:
            file.write(response.content)
        print("Rain data pdf downloaded")
    
document_downloader()

