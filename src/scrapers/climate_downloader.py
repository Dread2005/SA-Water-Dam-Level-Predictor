from playwright.sync_api import sync_playwright
import requests
import ee
from datetime import date
from pathlib import Path
import pandas as pd
import time
import json

def document_downloader():
    url1 = "https://www.weathersa.co.za/home/recentclimate"
    with sync_playwright() as p:
        ### -WEATHER SA RAIN DATA- ###

        headless = False
        browser = p.chromium.launch(headless=headless)
 
        #open tab
        page = browser.new_page()
        page.goto(url1)

        #get daily rainfall data from weather SA
        with page.context.expect_page() as new_page:
            page.click("text=Daily Rainfall")
        
        new_page = new_page.value
        page.wait_for_load_state("networkidle")

        time.sleep(4)
        
        pdf_URL = new_page.url
        print(f"PDF URL: {pdf_URL}")

        #Download the pdf
        response = requests.get(pdf_URL, verify=False)
        
        with open("src/resources/SA-rain-data.pdf", "wb") as file:
            file.write(response.content)
        print("Rain data pdf downloaded")

    ### NASA CHIRPS DATA- ###

    #Checks if Earth Engin is authenticated
    auth = False
    def is_ee_authenticated() -> bool:
        credentials_path = Path.home()/".config"/"earthengine"/"credentials"
        return credentials_path.exists()
    
    if not is_ee_authenticated():
        print("not authenticate")
        ee.Authenticate()

    print("Authentication completed")
    today = date.today()
    current_day = str(today.day)
    current_month = str(today.month)
    current_year = str(today.year)

    ee.Initialize(project="global-calling-450111-e2")

    sa_region = ee.Geometry.Rectangle([16.5, -35.0, 33.0, -22.0])
    chirps = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
    rainfall_data = chirps.filterDate("2000-01-01", f"{current_year}-{current_month}-{current_day}").filterBounds(sa_region)
    
    #get Mean rainfall over SA for each image(day)
    def extract_mean(image):
        mean = image.reduceRegion(
            reducer = ee.Reducer.mean(),
            geometry = sa_region,
            scale = 5000)
        date_str = image.date().format("YYYY-MM-dd")

        return image.set({
                        "date": date_str, 
                        "mean_rainfall": mean.get("precipitation")
                        })
    
    daily_means = rainfall_data.map(extract_mean)

    #Convert to pandas DataFrame
    values = daily_means.reduceColumns(
        ee.Reducer.toList(2), ["date", "mean_rainfall"]).get("list").getInfo()
    
    rainfall_json = {
        "data": values
    }
    
    with open("src/resources/rainfall.json", "w", encoding="utf-8") as file:
        json.dump(rainfall_json, file, indent=4)
    
    
    # df = pd.DataFrame(values, columns = ["date", "mean_rainfall"])
    # df["date"] = pd.to_datetime(df["date"])
    # df = df.sort_values("date")

    # print(df.head())
    # print(df.info())
    # print(df.describe())
document_downloader()

