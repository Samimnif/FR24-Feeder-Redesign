from flask import Flask, render_template, request, redirect, url_for, Response
import json
import urllib.request, json
import os
import uuid
from datetime import datetime
from functools import wraps
import csv

# Initialize dictionaries to store data from CSV files
csv1_data = {}
csv2_data = {}
csv3_data = {}

# Read and process the CSV file
with open('db/reg-country.csv', 'r') as file3:
    reader = csv.DictReader(file3)
    for row in reader:
        prefix = row['prefix']
        country = row['Country']
        codeAlpha = row['Alpha-2']
        csv3_data[prefix] = {'country':country, 'code':codeAlpha}

# Read and process the first CSV file
with open('db/flightaware-20220928.csv', 'r') as file1:
    reader = csv.DictReader(file1)
    for row in reader:
        icao24 = row['icao24']
        r = row['r']
        t = row['t']
        desc = row['desc']
        csv1_data[icao24] = {'r': r, 't': t, 'desc': desc}

# Read and process the second CSV file
with open('db/vrs.csv', 'r') as file2:
    reader = csv.DictReader(file2)
    for row in reader:
        icao24 = row['icao24']
        r = row['r']
        t = row['t']
        csv2_data[icao24] = {'r': r, 't': t}

# Combine the dictionaries and remove duplicates
combined_data = {**csv1_data, **csv2_data}

# Print the combined data
#for icao24, data in combined_data.items():
#    print(f"icao24: {icao24}, r: {data.get('r', '')}, t: {data.get('t', '')}, desc: {data.get('desc', '')}")


app = Flask(__name__)
url = 'http://fr24.local:8754/flights.json'

def get_alpha(registration_code):
    global csv3_data
    # Split the registration code to extract the prefix
    split_code = registration_code.split('-')
    if len(split_code) > 1:
        prefix = split_code[0]
        print(prefix)
        # Look up the alpha code from the dictionary
        if prefix in csv3_data:
            return csv3_data[prefix]['code'],csv3_data[prefix]['country']
    else:
        print("First two ",registration_code[0:2])
        print("First ",registration_code[0])
        if registration_code[0:2] in csv3_data:
            return csv3_data[registration_code[0:2]]['code'],csv3_data[registration_code[0:2]]['country']
        elif registration_code[0] in csv3_data:
            return csv3_data[registration_code[0]]['code'],csv3_data[registration_code[0]]['country']
    return None  # Return None if no matching prefix is found

def get_data():
    global combined_data
    response = urllib.request.urlopen(url)
    data = json.loads(response.read())
    for i in data:
        print(i.upper())
        if i.upper() in combined_data:
            data[i].append(combined_data[i.upper()].get('r', ''))#17 Registration code
            data[i].append(combined_data[i.upper()].get('t', ''))#18 Model Number
            data[i].append(combined_data[i.upper()].get('desc', ''))#19 Aircraft type
            if data[i][17] != '':
                prefixCode = get_alpha(data[i][17])
                if prefixCode != None:
                    data[i].append(prefixCode[0].lower())#20 Code Alpha
                    data[i].append(prefixCode[1])#21 Country
                print(prefixCode)
        else:
            print(f"Couldn't find this ICAO: {i}")
    print(data)
    return data

@app.route('/')
def index():
    return render_template('home.html', flights=get_data())

@app.route('/flights', methods=['POST'])
def flights():
    return get_data()

if __name__ == '__main__':
    app.run(host="0.0.0.0",port="80", debug=True)