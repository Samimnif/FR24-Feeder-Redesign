import json

import requests
from bs4 import BeautifulSoup
from time import sleep

def get_aircraft_registration(icao):
    """
    This one isn't working yet...
    :param icao:
    :return:
    """
    url = f'https://globe.adsbexchange.com/?icao={icao}'
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("Failed to load page. REG")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    #print(soup)

    registration = soup.find_all('span', id="selected_registration")
    type = soup.find(id="selected_icaotype")
    desc = soup.find(id="selected_typedesc")
    print(registration, type, desc)
    return registration, type, desc

def get_aircraft_type(aircraft_type):
    url = f"https://learningzone.eurocontrol.int/ilp/customs/ATCPFDB/details.aspx?ICAO={aircraft_type}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to load page. TYPE {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    type = soup.find(id="MainContent_wsTypeLabel").get_text(strip=True)
    APC = soup.find(id="MainContent_wsAPCLabel").get_text(strip=True)
    WTC = soup.find(id="MainContent_wsWTCLabel").get_text(strip=True)

    return type, APC, WTC

def get_aircraft_code(aircraft_reg):
    url = f"https://www.flightradar24.com/data/aircraft/{aircraft_reg}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to load {aircraft_reg} page. {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    type = soup.find_all("span", class_="details")

    return type[3].get_text(strip=True)

if __name__ == '__main__':
    with open('db/missing-plane-data.json', 'r') as file:
        data = json.load(file)
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
                response = requests.post("http://127.0.0.1:3000/unidentified", data=sendData)#127.0.0.1
                if response.status_code == 200:
                    print("POST successful.", plane['icao'], plane['r'], plane['t'], plane['desc'])
                else:
                    print(f"POST failed. Status code: {response.status_code}")
                sleep(3.5)
            except:
                print("error in func")
    #     else:
    #         print("No Reg:", plane['icao'])
    #         try:
    #             plane['r'], plane['t'], plane['desc'] = get_aircraft_registration(plane['icao'])
    #             sendData = {
    #                 'icao': plane['icao'],
    #                 'registration': plane['r'],
    #                 'model': plane['t'],
    #                 'type': plane['desc']
    #             }
    #             response = requests.post("http://127.0.0.1:3000/unidentified", data=sendData)
    #             if response.status_code == 200:
    #                 print("POST successful.", plane['icao'], plane['r'], plane['t'], plane['desc'])
    #             else:
    #                 print(f"POST failed. Status code: {response.status_code}")
    #             sleep(3.5)
    #         except:
    #             print("error in func")