from flask import Flask, render_template, request, redirect, url_for, Response
import json
import os
import uuid
from datetime import datetime
from functools import wraps

app = Flask(__name__)

@app.route('/')
def index():
    
    return render_template('home.html')

if __name__ == '__main__':
    app.run(host="0.0.0.0",port="80", debug=True)