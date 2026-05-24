import requests, time
import pandas as pd
import io
### Retrive HTML as txt ###
def DWS_Data():
    #DWS government link:
    url = "https://www.dws.gov.za/Hydrology/Weekly/ProvinceWeek.aspx?region=G"

    header = {
        "User-Agent":(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    def get_with_retry(url, header, backoff=5, retries=4):
        for attempt in range(retries):
            try:
                ressponse = requests.get(url, headers=header, timeout=30)

                #Raises HTTPErorr if status 4XXX or 5XXX
                ressponse.raise_for_status()
                print(ressponse.status_code)

                #This text will be used for scrapping by beutifuleSoup
                html = ressponse.text
                return html
            except requests.exceptions.Timeout:
                print(f"Timed out on attempt {attempt+1}")
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    wait = backoff * (12**attempt)
                    print(f"Rate  Limited: waiting {wait}s")
                    time.sleep(wait)
                else:
                    raise
            except requests.exceptions.ConnectionError:
                print(f"Connection error on attempt {attempt + 1}")
                time.sleep(backoff)
            raise Exception(f"Failed after {retries}")
    html_txt = get_with_retry(url, header)
    ### Pandas html table scrapper section ###

    def DWS_panda_table(scrapper_data):
        string_io_object = io.StringIO(scrapper_data)
        tables = pd.read_html(string_io_object)
        return tables

    DWS_table = DWS_panda_table(html_txt)
    Damn_data = DWS_table[4]
    return Damn_data
print(DWS_Data())