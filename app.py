from flask import Flask, render_template, request, redirect, url_for, Response
import json
import urllib.request, json
import os
import uuid
from datetime import datetime
from functools import wraps

app = Flask(__name__)
url = 'http://fr24.local:8754/flights.json'

def get_data():
    response = urllib.request.urlopen(url)
    data = json.loads(response.read())
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