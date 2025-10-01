from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    send_from_directory,
    send_file,
    abort,
)

from flask_cors import CORS, cross_origin

from base64 import encodebytes
import glob
import io
import os
from PIL import Image
import json
import numpy as np
import requests

from dotenv import load_dotenv

load_dotenv()

cwd = os.getcwd()

auth = None  # HTTPBasicAuth(os.environ.get("ORTHANC_USERNAME"), os.environ.get("ORTHANC_PASSWD"))
orthanc_server = os.environ.get("ORTHANC_SERVER")

# configuration
DEBUG = True

# instantiate the app
app = Flask(
    __name__,
    static_folder="frontend/dist/static",
    template_folder="frontend/dist",
    static_url_path="/static",
)
cors = CORS(app)
app.config["CORS_HEADERS"] = "Content-Type"
app.config.from_object(__name__)

# definitions
SITE = {"logo": "Stackoptica", "version": "2.0.0"}

OWNER = {
    "name": "Royal Belgian Institute of Natural Sciences",
}

# pass data to the frontend
site_data = {"site": SITE, "owner": OWNER}


# landing page
@app.route("/<id>")
def welcome(id):
    print(f"id : {id}")
    return render_template("index.html", **site_data)


def get_response_layers(instance):
    byte_arr = requests.get(
        url=f"{orthanc_server}/instances/{instance}/attachments/layers/data", auth=auth
    ).content
    return byte_arr


def get_response_depthmap(instance):
    byte_arr = requests.get(
        url=f"{orthanc_server}/instances/{instance}/attachments/depthmap/data",
        auth=auth,
    ).content
    return byte_arr


def get_response_thumbnail(instance):
    byte_arr = requests.get(
        url=f"{orthanc_server}/instances/{instance}/attachments/thumbnail/data",
        auth=auth,
    ).content
    return byte_arr


def get_response_image(instance):
    byte_arr = requests.get(
        url=f"{orthanc_server}/instances/{instance}/content/7fe0-0010/1", auth=auth
    ).content
    return byte_arr


# send single image
@app.route("/<id>/<image_id>/full-image")
@cross_origin()
def image(id, image_id):
    try:
        image_binary = get_response_image(image_id)
        return send_file(
            io.BytesIO(image_binary), mimetype="image/jpeg", as_attachment=False
        )
    except Exception as error:
        print(error)


# send layers data
@app.route("/<id>/<image_id>/layers")
@cross_origin()
def layers(id, image_id):
    try:
        image_binary = get_response_layers(image_id)
        return send_file(
            io.BytesIO(image_binary), mimetype="image/jpeg", as_attachment=False
        )
    except Exception as error:
        print(error)


# send deptmap image
@app.route("/<id>/<image_id>/depthmap")
@cross_origin()
def depthmap(id, image_id):
    try:
        image_binary = get_response_depthmap(image_id)
        return send_file(
            io.BytesIO(image_binary), mimetype="image/jpeg", as_attachment=False
        )
    except Exception as error:
        print(error)


# send single image
@app.route("/<id>/<image_id>/thumbnail")
@cross_origin()
def thumbnail(id, image_id):
    try:
        image_binary = get_response_thumbnail(image_id)
        return send_file(
            io.BytesIO(image_binary), mimetype="image/jpeg", as_attachment=False
        )
    except Exception as error:
        print(error)


# send StackData
@app.route("/<id>/images")
@cross_origin()
def images(id):
    response = requests.get(
        url=f"{orthanc_server}/series/{id}/instances-tags?simplify", auth=auth
    )
    if not response.ok:
        abort(404)
    orthanc_dict: dict = json.loads(response.content)

    to_jsonify = {}
    encoded_images = []
    for instance, tags in orthanc_dict.items():
        try:
            encoded_images.append(
                {
                    "name": instance,
                    "label": tags["UserContentLabel"],
                    "size": {
                        "width": tags["Columns"],
                        "height": tags["Rows"],
                    },
                    "depthmap": "",  # f"data:image/png;base64,{depth_bytes.decode('ascii')}",
                    "layers": "",  # f"data:image/png;base64,{layer_bytes.decode('ascii')}",
                }
            )
        except Exception as error:
            print(error)
            continue

    to_jsonify["images"] = encoded_images

    return jsonify(to_jsonify)


@app.route("/<id>/<image_id>/position")
@cross_origin()
def compute_landmark(id, image_id):
    x = float(request.args.get("x"))
    y = float(request.args.get("y"))

    layer = int(request.args.get("layer"))
    depth = int(request.args.get("depth"))

    response = requests.get(
        url=f"{orthanc_server}/instances/{image_id}/simplified-tags", auth=auth
    )
    if not response.ok:
        abort(404)

    tags: dict = json.loads(response.content)

    pixel_spacing = [float(x) for x in tags["PixelSpacing"].split("\\")]
    thickness = float(tags["SliceThickness"])
    number_images = int(tags["NumberOfFrames"])

    position = {
        "depth": {
            "x": x * pixel_spacing[0],
            "y": y * pixel_spacing[1],
            "z": thickness / 256 * depth,
        },
        "layer": {
            "x": x * pixel_spacing[0],
            "y": y * pixel_spacing[1],
            "z": layer * thickness / number_images,
        },
    }

    return jsonify(position)


if __name__ == "__main__":
    app.run()
