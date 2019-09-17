from flask import Flask,request,jsonify
from flask_cors import CORS, cross_origin
from scripts import *    
import requests
import io
import os

app = Flask(__name__ ,static_folder='static', static_url_path='')

cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'

@app.route('/')
def root():
    return app.send_static_file('index.html')

@app.route("/get_grid", methods=['POST'])
@cross_origin()
def home():
    url = request.environ.get('HTTP_ORIGIN', 'default value')
    content = request.get_json(force=True)
    h = 100
    w = 65.95092024539878
    name = content["name"]
    bound = content["bound"]
    email = content["email"]
    grid = run_all(bound,h,w,name,email)
    headers = {'content-type': "application/json",'cache-control': "no-cache"}
    url = "https://cityio.media.mit.edu/api/table/update/"+name
    response = requests.request("POST", url, data=json.dumps(grid), headers=headers)
    print(response)
    if(response.json()["status"] == "ok"):
        return('success')
    else:
        return('404')

if __name__ == "__main__":
    app.run(host= '0.0.0.0',port=80)
