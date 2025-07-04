from flask import Flask, render_template, request, redirect, url_for, Response, jsonify, send_file
from apscheduler.schedulers.background import BackgroundScheduler
import json
import urllib.request, json
import os
import uuid
from datetime import datetime
from functools import wraps
import csv
import signal
import sys
import sqlite3
from datetime import datetime, timedelta
from io import StringIO
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

# SQLite database setup
DATABASE = 'db/plane_history.db'
def create_table():
    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS plane_history (
                            timestamp TEXT,
                            icao24 TEXT,
                            data TEXT
                        )''')

def save_to_database(timestamp, data):
    icao24 = data[0]
    
    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.cursor()

        # Check if an entry with the same timestamp and ICAO24 already exists
        cursor.execute("SELECT * FROM plane_history WHERE timestamp=? AND icao24=?", (timestamp, icao24))
        existing_entry = cursor.fetchone()

        if existing_entry:
            # If it exists, update the data
            cursor.execute("UPDATE plane_history SET data=? WHERE timestamp=? AND icao24=?", (json.dumps(data), timestamp, icao24))
        else:
            # If it doesn't exist, insert a new entry
            cursor.execute("INSERT INTO plane_history (timestamp, icao24, data) VALUES (?, ?, ?)", (timestamp, icao24, json.dumps(data)))

def get_planes_last_hour():
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=1)

    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.cursor()

        # Retrieve distinct planes within the last hour with first and last timestamps
        cursor.execute("""
            SELECT icao24, MIN(timestamp) as first_appeared, MAX(timestamp) as last_appeared, data
            FROM plane_history
            WHERE timestamp BETWEEN ? AND ?
            GROUP BY icao24
            ORDER BY first_appeared DESC
        """, (start_time.strftime("%Y-%m-%d %H:%M:%S"), end_time.strftime("%Y-%m-%d %H:%M:%S")))

        planes_last_hour = cursor.fetchall()

    # Transform the data if needed (e.g., converting JSON strings back to dictionaries)
    transformed_planes = [
        {'icao24': row[0], 'first_appeared': row[1], 'last_appeared': row[2], 'data': json.loads(row[3])}
        for row in planes_last_hour
    ]

    return transformed_planes

def get_planes_all():
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=1)

    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.cursor()

        # Retrieve distinct planes within the last hour with first and last timestamps
        cursor.execute("""
            SELECT icao24, MIN(timestamp) as first_appeared, MAX(timestamp) as last_appeared, data
            FROM plane_history
            GROUP BY icao24
            ORDER BY first_appeared DESC
        """)
        planes_history = cursor.fetchall()

    # Transform the data if needed (e.g., converting JSON strings back to dictionaries)
    transformed_planes = [
        {'icao24': row[0], 'first_appeared': row[1], 'last_appeared': row[2], 'data': json.loads(row[3])}
        for row in planes_history
    ]

    return transformed_planes

# Initialize dictionaries to store data from CSV files
csv1_data = {}
csv2_data = {}
csv3_data = {}
flightData = {}

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

# Initialize the BackgroundScheduler
scheduler = BackgroundScheduler()

def get_data_and_save():
    global flightData
    flightData = get_data()
    # Save the data to the database
    #plane_data = json.loads(flightData)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    for icao24 in flightData:
        print("Here", flightData[icao24])
        save_to_database(timestamp, flightData[icao24])

# Schedule the get_data_and_save function to run every 10 seconds
scheduler.add_job(get_data_and_save, 'interval', seconds=30)
scheduler.start()

# Define a signal handler to gracefully shut down the scheduler
def shutdown_scheduler(signal, frame):
    print("Shutting down the scheduler...")
    scheduler.shutdown()
    sys.exit(0)

# Register the signal handler for SIGTERM and SIGINT
signal.signal(signal.SIGTERM, shutdown_scheduler)
signal.signal(signal.SIGINT, shutdown_scheduler)

def add_suggestion(icao,r,t,des):
    with open('db/missing-plane-data.json', 'r') as file:
        data = json.load(file)
    icao_exists = any(item['icao'] == icao for item in data)
    if not icao_exists:
        data.append({"icao":icao, "r":r, "t":t,"des":des})
        with open('db/missing-plane-data.json', 'w') as file:
            json.dump(data, file, indent=4)

def get_alpha(registration_code):
    global csv3_data
    # Split the registration code to extract the prefix
    split_code = registration_code.split('-')
    if len(split_code) > 1:
        prefix = split_code[0]
        #print(prefix)
        # Look up the alpha code from the dictionary
        if prefix in csv3_data:
            return csv3_data[prefix]['code'],csv3_data[prefix]['country']
    else:
        #print("First two ",registration_code[0:2])
        #print("First ",registration_code[0])
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
        #print(i.upper())
        if data[i][16][0:3] != "PTR":
            data[i].append(data[i][16][0:3])#17 Callsign ICAO ID
        else:
            data[i].append("POE")
        if i.upper() in combined_data:
            #print(combined_data[i.upper()])
            data[i].append(combined_data[i.upper()].get('r', ''))#18 Registration code
            data[i].append(combined_data[i.upper()].get('t', ''))#19 Model Number
            data[i].append(combined_data[i.upper()].get('desc', ''))#20 Aircraft type
            if data[i][18] != '':
                prefixCode = get_alpha(data[i][18])
                if prefixCode != None:
                    data[i].append(prefixCode[0].lower())#21 Code Alpha
                    data[i].append(prefixCode[1])#22 Country
                #print(prefixCode)
            if data[i][18] == '' or data[i][19] == '' or data[i][20] == '':
                add_suggestion(i,data[i][18], data[i][19], data[i][20])
        else:
            add_suggestion(i,'', '', '')
            print(f"Couldn't find this ICAO: {i}")
    print(data)
    return data

@app.errorhandler(404) 
def not_found(e): 
  return render_template("404.html") 

@app.route('/')
def index():
    return render_template('home.html', flights=flightData)

@app.route('/flights', methods=['POST'])
def flights():
    return flightData

@app.route('/history')
def history():
    return render_template('history.html', planes=get_planes_last_hour())
    #return jsonify(get_planes_last_hour())

@app.route('/unidentified', methods=['GET', 'POST'])
def unidentified():
    global combined_data
    per_page = 30  # You can tweak this
    page = int(request.args.get('page', 1))

    # Handle form submission
    if request.method == 'POST':
        icao = request.form.get('icao')
        registration = request.form.get('registration')
        model = request.form.get('model')
        aircraft_type = request.form.get('type')

        if icao and registration and model and aircraft_type:
            with open('db/contributions.csv', 'a+', newline='') as csvfile:
                fieldnames = ['ICAO', 'Registration', 'Model', 'Aircraft Type']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writerow({'ICAO': icao, 'Registration': registration, 'Model': model, 'Aircraft Type': aircraft_type})
                combined_data[icao.upper()] = {
                    'r': registration,
                    't': model,
                    'desc': aircraft_type
                }

            # Remove from missing-plane-data.json
            with open("db/missing-plane-data.json", 'r') as f:
                ufo = json.load(f)
            ufo = [plane for plane in ufo if plane['icao'] != icao]
            with open("db/missing-plane-data.json", 'w') as f:
                json.dump(ufo, f, indent=2)

    # Load and paginate the data
    with open("db/missing-plane-data.json", 'r') as f:
        ufo = json.load(f)

    total = len(ufo)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_ufo = ufo[start:end]

    total_pages = (total + per_page - 1) // per_page  # ceiling division
    # Generate page range: 2 before to 2 after current page, within bounds
    start_range = max(1, page - 2)
    end_range = min(total_pages, page + 2)
    page_range = list(range(start_range, end_range + 1))

    return render_template('contribute.html', ufo=paginated_ufo, page=page, total_pages=total_pages, page_range=page_range, total=total)

    with open("db/missing-plane-data.json", 'r') as f:
        ufo = json.load(f)
    return render_template('contribute.html', ufo=ufo)

@app.route('/export_data')
def export_data():
    
    return render_template('export_data.html', planes=get_planes_all())

@app.route('/download_csv')
def download_csv():
    
    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.cursor()

        # Fetch data from your SQLite table
        cursor.execute("SELECT * FROM plane_history")
        data = cursor.fetchall()

        # Prepare CSV data
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([i[0] for i in cursor.description])  # Write headers
        writer.writerows(data)

        # Set up response headers
        output.seek(0)
    return Response(
            output,
            mimetype='text/csv',
            headers={"Content-disposition":
                    "attachment; filename=your_data.csv"})

@app.route('/download_xml')
def download_xml():
    # Connect to your SQLite database
    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.cursor()

        # Fetch data from your SQLite table
        cursor.execute("SELECT * FROM plane_history")
        data = cursor.fetchall()

        # Create XML structure
        root = Element('data')
        for row in data:
            entry = SubElement(root, 'entry')
            for i, col in enumerate(row):
                SubElement(entry, 'col%d' % i).text = str(col)

        # Convert XML to string
        xml_string = tostring(root, encoding='utf-8', method='xml')

        # Prettify XML string (optional)
        xml_string = minidom.parseString(xml_string).toprettyxml(indent="  ")

    return Response(
        xml_string,
        mimetype="text/xml",
        headers={"Content-disposition":
                 "attachment; filename=data.xml"})

@app.route('/about')
def about():
    return render_template('about.html')

if __name__ == '__main__':
    create_table()
    app.run(host="0.0.0.0",port="3000", debug=True)
    #app.run(debug=True)