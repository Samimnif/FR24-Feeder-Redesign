import json
import requests
from bs4 import BeautifulSoup
from time import sleep

with open('db/missing-plane-data.json', 'r') as file:
    data = json.load(file)

def get_aircraft_type(aircraft_type):
    url = f"https://learningzone.eurocontrol.int/ilp/customs/ATCPFDB/details.aspx?ICAO={aircraft_type}"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("Failed to load page.")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    type = soup.find(id="MainContent_wsTypeLabel").get_text(strip=True)
    APC = soup.find(id="MainContent_wsAPCLabel").get_text(strip=True)
    WTC = soup.find(id="MainContent_wsWTCLabel").get_text(strip=True)

    return type, APC, WTC

def get_aircraft_code(aircraft_reg):
    url = f"https://www.flightradar24.com/data/aircraft/{aircraft_reg}"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("Failed to load page.")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    type = soup.find_all("span", class_="details")

    return type[3].get_text(strip=True)

# print(get_aircraft_type('A319'))
# print((get_aircraft_code('c-fyns')))
for plane in data:
    if plane['r'] != "":
        try:
            plane['t'] = get_aircraft_code(plane['r'])
            plane['desc'] = get_aircraft_type(plane['t'])[0]
            sendData = {
                'icao': plane['icao'],
                'registration': plane['r'],
                'model': plane['t'],
                'type': plane['desc']
            }
            response = requests.post("http://127.0.0.1:3000/unidentified", data=sendData)
            if response.status_code == 200:
                print("POST successful.", plane['icao'], plane['r'], plane['t'], plane['desc'])
            else:
                print(f"POST failed. Status code: {response.status_code}")
            sleep(3.5)
        except:
            print("error in func")