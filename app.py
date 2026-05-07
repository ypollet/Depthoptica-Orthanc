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
import math

from scipy.ndimage import gaussian_filter1d

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

@app.route("/<id>/<image_id>/profile")
@cross_origin()
def compute_profile(id, image_id):
    if request["method"] == "GET":
        instanceId = request["groups"][0]
        x1 = float(request.args.get("x1"))
        y1 = float(request.args.get("y1"))

        x2 = float(request.args.get("x2"))
        y2 = float(request.args.get("y2"))

        threshold = request.args.get("threshold", "") or "" # String or None
        smooth_str = request.args.get("smooth", "true")
        match smooth_str.lower():
            case "false":
                smooth = False
            case _:
                smooth = True
        
        response = requests.get(
            url=f"{orthanc_server}/instances/{image_id}/simplified-tags", auth=auth
        )
        if not response.ok:
            abort(404)

        tags: dict = json.loads(response.content)
        
        attachments = json.loads(orthanc.RestApiGet(f"/instances/{instanceId}/attachments"))
        if "heightmap" not in attachments:
            return
        height_bytes = orthanc.RestApiGet(f"/instances/{instanceId}/attachments/heightmap/data")
    
        heightmap = cv2.imdecode(np.asarray(bytearray(height_bytes)), cv2.IMREAD_GRAYSCALE | cv2.IMREAD_ANYDEPTH)

        edges = None
        if "edges" in attachments:
            edges_bytes = orthanc.RestApiGet(f"/instances/{instanceId}/attachments/edges/data")
            edges = cv2.imdecode(np.asarray(bytearray(edges_bytes)), cv2.IMREAD_GRAYSCALE)
            
            image_thresholds = json.loads(
                orthanc.RestApiGet(f"/instances/{instanceId}/metadata/edges_thresholds")
            )
        
        mask = None
        if "mask" in attachments:
            mask_bytes = orthanc.RestApiGet(f"/instances/{instanceId}/attachments/mask/data")
            mask = cv2.imdecode(np.asarray(bytearray(mask_bytes)), cv2.IMREAD_GRAYSCALE)
        subLandmarks = []
        
        edge_threshold = image_thresholds[threshold] if (edges is not None and threshold in image_thresholds) else 0
        list_distances = wu_line(x1, y1, x2, y2, heightmap, mask, edges, edge_threshold)

        pixel_spacing = [float(x) for x in tags["PixelSpacing"].split("\\")]
        thickness = float(tags["SliceThickness"])

        graphs_segments = []
        if len(list_distances) > 0:
            first_segment, _ = list_distances[0]

            last_segment, _ = list_distances[-1]
            start =  {
                    "x": first_segment[0]["x"] * pixel_spacing[0],
                    "y": first_segment[0]["y"]  * pixel_spacing[1],
                    "z": (thickness / (2**(heightmap.itemsize*8)) * first_segment[0]["z"])
                }

            end =  {
                    "x": last_segment[-1]["x"] * pixel_spacing[0],
                    "y": last_segment[-1]["y"]  * pixel_spacing[1],
                    "z": (thickness / (2**(heightmap.itemsize*8)) * last_segment[-1]["z"])
                }
            
            
            
            for distance in list_distances:
                subLandmarks, distance = distance[0], distance[1]
                subLandmarks = [ {
                    "x": i["x"] * pixel_spacing[0],
                    "y": i["y"]  * pixel_spacing[1],
                    "z": (thickness / (2**(heightmap.itemsize*8)) * i["z"])
                } for i in subLandmarks]

                line_3d = [ {
                    "x": i["x"] - start["x"],
                    "y": i["y"] - start["y"],
                    "z": i["z"]
                } for i in subLandmarks]

                # Smooth line

                line_2d = np.array([
                    [math.sqrt(point["x"]**2 + point["y"]**2), point["z"]] 
                    for point in line_3d])
                if smooth:
                    
                    line_2d = smooth_array(line_2d, distance)

                graphs_segments.append([{
                    "x": point[0],
                    "y": point[1]
                } for point in line_2d.tolist()])
        else:
            start =  {
                    "x": x1 * pixel_spacing[0],
                    "y": y1  * pixel_spacing[1],
                    "z": 0
                }
            end =  {
                        "x": x2 * pixel_spacing[0],
                        "y": y2  * pixel_spacing[1],
                        "z": 0
                    }
        subLandmarks = [ {
                "x": i["x"] * pixel_spacing[0],
                "y": i["y"]* pixel_spacing[1],
                "z": thickness / (2**(heightmap.itemsize*8)) * i["z"],
            } for i in subLandmarks]

        start = subLandmarks[0]
        line_3d = [ {
            "x": i["x"] - start["x"],
            "y": i["y"] - start["y"],
            "z": i["z"]
        } for i in subLandmarks]

        # Smooth line

        line_2d = np.array([
            [math.sqrt(point["x"]**2 + point["y"]**2), point["z"]] 
            for point in line_3d])
        
        if smooth:
            line_2d = smooth_array(line_2d, distance)

        graph = [{
            "x": point[0],
            "y": point[1]
        } for point in line_2d.tolist()]   

        output.AnswerBuffer(json.dumps({
                "start": subLandmarks[0],
                "end" : subLandmarks[-1],
                "subLandmarkSegments": graph
            }, indent=3), "application/json")
    else:
        output.SendMethodNotAllowed("GET")

def wu_line(x0, y0, x1, y1, heightmap : np.ndarray, mask : np.ndarray | None, edges : np.ndarray | None, threshold = 0):
    horizontal = abs(y1 - y0) < abs(x1 - x0) # if x is longer than y
    
    inverse = x1 < x0 if horizontal else y1 < y0
    if inverse:
        # has to be a positive vector so swap start 
        # !!! need to inverse list order
        x0, x1 = x1, x0
        y0, y1 = y1, y0

    dx = x1 - x0
    dy = y1 - y0

    distance = dx if horizontal else dy
    numerator = dy if horizontal else dx

    gradient = numerator/distance if distance != 0 else 1

    list_distances = []

    

    # get integer point before start point
    ratio_start = int(x0) - x0 if horizontal else int(y0) - y0
    start_point = {
        "x" : int(x0) if horizontal else x0 + gradient*ratio_start,
        "y" : y0 + gradient*ratio_start if horizontal else int(y0)
    }

    start = 0
    length_line = int(distance)+1
    while start < length_line:

        list_pixels, distance, end = handle_distance(start, length_line, inverse, start_point, gradient, horizontal, heightmap, mask, edges, threshold)
        if len(list_pixels) > 0:  #not empty
            list_distances.append((list_pixels, distance))
        
        start = end 
    
    return list_distances


def handle_distance(i, length_line, inverse, start_point, gradient, horizontal, heightmap, mask, edges, threshold):
    list_pixels = []
    list_i = [] # get distance of each pixels added, to get the 2 furthest points
    while i < length_line:
        # iterate from int before start point to int after end point
        x = start_point["x"] + i if horizontal else start_point["x"] + i*gradient
        y = start_point["y"] + i*gradient if horizontal else start_point["y"] + i
        ix, iy = int(x), int(y)

        i += 1
        if masked(ix, iy, mask):
            break
        
        dist = y - iy  if horizontal else x - ix # swap dist if steep
        depth = getRatioedPixelHeight(ix, iy, 1.0 - dist, heightmap) + getRatioedPixelHeight(ix, iy+1, dist, heightmap) if horizontal else getRatioedPixelHeight(ix, iy, 1.0 - dist, heightmap) + getRatioedPixelHeight(ix+1, iy, dist, heightmap)
        isEdge = edges[iy,ix] >= threshold if edges is not None else True
        if isEdge:
            list_i.append(i-1)
            list_pixels.append(
                {
                    "x": x,
                    "y": y,
                    "z": depth,
                }
        )
        
    

    if inverse:
        list_pixels.reverse()
    
    return list_pixels, list_i[-1] - list_i[0] if len(list_i) else 0, i
    

def masked(x : int, y : int, mask : np.ndarray | None):
    return mask is not None and not mask[y,x]

def getRatioedPixelHeight(x : int, y : int, ratio : float, heightmap : np.ndarray):
    return heightmap[y,x] * ratio


def smooth_array(array, distance : float):
    x, y = array.T
    t = np.linspace(0, 1, len(x))
    t2 = np.linspace(0, 1, int(distance)*10)
    t3 = np.linspace(0, 1, 100)

    x2 = np.interp(t3, t, x)
    y2 = np.interp(t3, t, y)
    sigma = 1#int(distance)/10
    x3 = x2
    y3 = gaussian_filter1d(y2, sigma)

    """x4 = np.interp(t3, t2, x3).reshape((-1,1))
    y4 = np.interp(t3, t2, y3).reshape((-1,1))"""


    return np.concatenate((x3.reshape((-1,1)),y3.reshape((-1,1))),1)

if __name__ == "__main__":
    app.run()
