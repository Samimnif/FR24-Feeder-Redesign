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
import threading
from datetime import datetime, timedelta
from io import StringIO
import aircraft_lookup

# SQLite database setup
DATABASE = 'db/plane_history.db'


def create_table():
    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS plane_history
                          (
                              timestamp
                              TEXT,
                              icao24
                              TEXT,
                              data
                              TEXT
                          )''')
        # Remove any duplicate (timestamp, icao24) rows before adding the unique index
        cursor.execute("""DELETE
                          FROM plane_history
                          WHERE rowid NOT IN (SELECT MAX(rowid)
                                              FROM plane_history
                                              GROUP BY
                              timestamp
                              , icao24)""")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ts_icao ON plane_history (timestamp, icao24)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_icao ON plane_history (icao24)")


def save_to_database(timestamp, flights):
    """Upsert all current flights in one connection/transaction."""
    rows = [(timestamp, d[0], json.dumps(d)) for d in flights.values()]
    with sqlite3.connect(DATABASE) as connection:
        connection.executemany(
            "INSERT OR REPLACE INTO plane_history (timestamp, icao24, data) VALUES (?, ?, ?)", rows)


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


flightData = {}

# Aircraft info lives in db/aircraft.db (built from the CSVs on first run)
create_table()
aircraft_lookup.build()
csv3_data = aircraft_lookup.load_countries()

# Missing-aircraft list: load once, keep only the ICAO set in memory,
# and write the JSON only when something new was added.
MISSING_JSON = 'db/missing-plane-data.json'
_missing_lock = threading.Lock()


def _load_missing():
    try:
        with open(MISSING_JSON, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


missing_icaos = {p['icao'] for p in _load_missing()}
_pending_missing = []

app = Flask(__name__)
url = os.environ.get('FEEDER_URL', 'http://192.168.0.106:8754/flights.json')

# Initialize the BackgroundScheduler
scheduler = BackgroundScheduler()


def get_data_and_save():
    global flightData
    flightData = get_data()
    # Save the data to the database
    # plane_data = json.loads(flightData)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_to_database(timestamp, flightData)
    flush_suggestions()


# Schedule the get_data_and_save function to run every 10 seconds
scheduler.add_job(get_data_and_save, 'interval', seconds=30, max_instances=1, coalesce=True)
scheduler.start()


# Define a signal handler to gracefully shut down the scheduler
def shutdown_scheduler(signal, frame):
    print("Shutting down the scheduler...")
    scheduler.shutdown()
    sys.exit(0)


# Register the signal handler for SIGTERM and SIGINT
signal.signal(signal.SIGTERM, shutdown_scheduler)
signal.signal(signal.SIGINT, shutdown_scheduler)


def add_suggestion(icao, r, t, des):
    with _missing_lock:
        if icao in missing_icaos:
            return
        missing_icaos.add(icao)
        _pending_missing.append({"icao": icao, "r": r, "t": t, "des": des})


def flush_suggestions():
    """Append newly seen unknown aircraft to the JSON file in one write."""
    with _missing_lock:
        if not _pending_missing:
            return
        data = _load_missing()
        data.extend(_pending_missing)
        _pending_missing.clear()
        with open(MISSING_JSON, 'w') as file:
            json.dump(data, file, indent=2)


def get_alpha(registration_code):
    global csv3_data
    # Split the registration code to extract the prefix
    split_code = registration_code.split('-')
    if len(split_code) > 1:
        prefix = split_code[0]
        # print(prefix)
        # Look up the alpha code from the dictionary
        if prefix in csv3_data:
            return csv3_data[prefix]['code'], csv3_data[prefix]['country']
    else:
        # print("First two ",registration_code[0:2])
        # print("First ",registration_code[0])
        if registration_code[0:2] in csv3_data:
            return csv3_data[registration_code[0:2]]['code'], csv3_data[registration_code[0:2]]['country']
        elif registration_code[0] in csv3_data:
            return csv3_data[registration_code[0]]['code'], csv3_data[registration_code[0]]['country']
    return None  # Return None if no matching prefix is found


def get_data():
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read())
    except Exception as e:
        print(f"Feeder unreachable: {e}")
        return flightData
    for i in data:
        # print(i.upper())
        if data[i][16][0:3] != "PTR":
            data[i].append(data[i][16][0:3])  # 17 Callsign ICAO ID
        else:
            data[i].append("POE")
        info = aircraft_lookup.lookup(i)
        if info is not None:
            data[i].append(info['r'])  # 18 Registration code
            data[i].append(info['t'])  # 19 Model Number
            data[i].append(info['desc'])  # 20 Aircraft type
            if data[i][18] != '':
                prefixCode = get_alpha(data[i][18])
                if prefixCode != None:
                    data[i].append(prefixCode[0].lower())  # 21 Code Alpha
                    data[i].append(prefixCode[1])  # 22 Country
                # print(prefixCode)
            if data[i][18] == '' or data[i][19] == '' or data[i][20] == '':
                p_code = data[i][19]
                p_type = data[i][20]
                # if data[i][18] != '':
                #     p_code = get_aircraft_code(data[i][18])
                #     p_type = get_aircraft_type(p_code)[0]
                add_suggestion(i, data[i][18], p_code, p_type)
        else:
            add_suggestion(i, '', '', '')
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
    # return jsonify(get_planes_last_hour())


@app.route('/unidentified', methods=['GET', 'POST'])
def unidentified():
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
                writer.writerow(
                    {'ICAO': icao, 'Registration': registration, 'Model': model, 'Aircraft Type': aircraft_type})
            aircraft_lookup.add_contribution(icao, registration, model, aircraft_type)

            # Remove from missing-plane-data.json
            with _missing_lock:
                ufo = [plane for plane in _load_missing() if plane['icao'] != icao]
                with open(MISSING_JSON, 'w') as f:
                    json.dump(ufo, f, indent=2)

    # Load and paginate the data
    ufo = _load_missing()

    total = len(ufo)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_ufo = ufo[start:end]

    total_pages = (total + per_page - 1) // per_page  # ceiling division
    # Generate page range: 2 before to 2 after current page, within bounds
    start_range = max(1, page - 2)
    end_range = min(total_pages, page + 2)
    page_range = list(range(start_range, end_range + 1))

    return render_template('contribute.html', ufo=paginated_ufo, page=page, total_pages=total_pages,
                           page_range=page_range, total=total)


@app.route('/export_data')
def export_data():
    return render_template('export_data.html', planes=get_planes_all())


@app.route('/download_csv')
def download_csv():
    def generate():
        with sqlite3.connect(DATABASE) as connection:
            cursor = connection.execute("SELECT * FROM plane_history")
            buf = StringIO()
            writer = csv.writer(buf)
            writer.writerow([c[0] for c in cursor.description])
            for row in cursor:
                writer.writerow(row)
                if buf.tell() > 64 * 1024:
                    yield buf.getvalue()
                    buf.seek(0);
                    buf.truncate()
            yield buf.getvalue()

    return Response(generate(), mimetype='text/csv',
                    headers={"Content-disposition": "attachment; filename=your_data.csv"})


@app.route('/download_xml')
def download_xml():
    from xml.sax.saxutils import escape
    def generate():
        yield '<?xml version="1.0" ?>\n<data>\n'
        with sqlite3.connect(DATABASE) as connection:
            for row in connection.execute("SELECT * FROM plane_history"):
                cols = ''.join(f'    <col{i}>{escape(str(c))}</col{i}>\n' for i, c in enumerate(row))
                yield f'  <entry>\n{cols}  </entry>\n'
        yield '</data>\n'

    return Response(generate(), mimetype="text/xml",
                    headers={"Content-disposition": "attachment; filename=data.xml"})


@app.route('/about')
def about():
    return render_template('about.html')


if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG') == '1'
    app.run(host="0.0.0.0", port=3000, debug=debug, use_reloader=False)
    # app.run(debug=True)