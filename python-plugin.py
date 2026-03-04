# Depthoptica - Viewer of stacked images - Orthanc Plugin

# Copyright (C) 2024-2025 Yann Pollet, Royal Belgian Institute of Natural Sciences

#

# This program is free software: you can redistribute it and/or

# modify it under the terms of the GNU Affero General Public License

# as published by the Free Software Foundation, either version 3 of

# the License, or (at your option) any later version.

#

# This program is distributed in the hope that it will be useful, but

# WITHOUT ANY WARRANTY; without even the implied warranty of

# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU

# Affero General Public License for more details.

#

# You should have received a copy of the GNU Affero General Public License

# along with this program. If not, see <http://www.gnu.org/licenses/>.

import json
import numpy as np
import cv2
from scipy.ndimage import gaussian_filter1d
import math

import orthanc

###############################################################################
#                                                                             #
# ------------------------------- DEPTHOPTICA ------------------------------- #
#                                                                             #
###############################################################################


def get_response_image(instance) -> bytearray:
    return orthanc.RestApiGet(f"/instances/{instance}/content/7fe0-0010/1")


def get_response_thumbnail(instance) -> bytearray:
    return orthanc.RestApiGet(f"/instances/{instance}/attachments/thumbnail/data")


def get_response_edges(instance) -> bytearray:
    return orthanc.RestApiGet(f"/instances/{instance}/attachments/edges/data")


def get_response_depthmap(instance) -> bytearray:
    return orthanc.RestApiGet(f"/instances/{instance}/attachments/depthmap/data")


# send single image
def image(output, uri, **request):
    if request["method"] == "GET":
        instanceId = request["groups"][0]
        orthanc.LogWarning(f"Request full image of {instanceId}")
        try:
            instanceId = request["groups"][0]
            image_binary = get_response_image(instanceId)
            output.AnswerBuffer(image_binary, "image/jpeg")
        except Exception as error:
            orthanc.LogError(error)
    else:
        output.SendMethodNotAllowed("GET")


orthanc.RegisterRestCallback("/depthoptica/(.*)/full-image", image)


# send thumbnail
def thumbnail(output, uri, **request):
    if request["method"] == "GET":
        instanceId = request["groups"][0]
        orthanc.LogWarning(f"Request thumbnail image of {instanceId}")
        try:
            instanceId = request["groups"][0]
            image_binary = get_response_thumbnail(instanceId)
            output.AnswerBuffer(image_binary, "image/jpeg")
        except Exception as error:
            orthanc.LogError(error)
    else:
        output.SendMethodNotAllowed("GET")


orthanc.RegisterRestCallback("/depthoptica/(.*)/thumbnail", thumbnail)


# send images
def images(output, uri, **request):
    if request["method"] == "GET":
        instanceId = request["groups"][0]
        orthanc.LogWarning(f"Request depthoptica camera images of {seriesId}")
        try:
            orthanc_dict = json.loads(
                orthanc.RestApiGet(f"/series/{instanceId}/instances-tags?simplify")
            )

            metadata_dict = json.loads(
                orthanc.RestApiGet(f"/series/{instanceId}/metadata?expand")
            )

            image_thresholds = metadata_dict["edges"]

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
                            "edgeThresholds": list(image_thresholds.keys()) if image_thresholds is not None else None
                        }
                    )
                except Exception as error:
                    print(error)
                    continue

            to_jsonify["images"] = encoded_images
            to_jsonify["thumbnails"] = True
            output.AnswerBuffer(json.dumps(to_jsonify), "application/json")
        except ValueError as e:
            orthanc.LogError(e)
    else:
        output.SendMethodNotAllowed("GET")

def compute_landmark(output, uri, **request):
    if request["method"] == "GET":
        instanceId = request["groups"][0]

        x = float(request.args.get("x"))
        y = float(request.args.get("y"))

        orthanc.LogWarning(f"Compute position of ({x};{y}) at {instanceId}")

        tags = json.loads(
            orthanc.RestApiGet(f"/instances/{instanceId}/simplified-tags")
        )

        height_bytes = orthanc.RestApiGet(f"/instances/{instanceId}/attachments/depthmap/data")
        im = cv2.imdecode(height_bytes, cv2.IMREAD_GRAYSCALE | cv2.IMREAD_ANYDEPTH)

        pixel_spacing = [float(x) for x in tags["PixelSpacing"].split("\\")]
        thickness = float(tags["SliceThickness"])
        depth = im[round(y)][round(x)]
        position = {
                "x": x * pixel_spacing[0],
                "y": y * pixel_spacing[1],
                "z": thickness / (2**(im.itemsize*8)) * depth,
            }

        output.AnswerBuffer(json.dumps(position, indent=3), "application/json")
    else:
        output.SendMethodNotAllowed("GET")


orthanc.RegisterRestCallback("/depthoptica/(.*)/position", compute_landmark)

def compute_profile(output, uri, **request):
    if request["method"] == "GET":
        instanceId = request["groups"][0]
        x1 = float(request.args.get("x1"))
        y1 = float(request.args.get("y1"))

        x2 = float(request.args.get("x2"))
        y2 = float(request.args.get("y2"))

        threshold = request.args.get("threshold") or "" # String or None
        
        tags = json.loads(
                orthanc.RestApiGet(f"/instances/{instanceId}/simplified-tags")
            )
        
        metadata_dict = json.loads(
                orthanc.RestApiGet(f"/series/{instanceId}/metadata?expand")
            )

        image_thresholds = metadata_dict["edges"]
        
        attachments = orthanc.RestApiGet(f"/instances/{instanceId}/attachments")
        if "heightmap" not in attachments:
            return
        height_bytes = orthanc.RestApiGet(f"/instances/{instanceId}/attachments/heightmap/data")
        heightmap = cv2.imdecode(height_bytes, cv2.IMREAD_GRAYSCALE | cv2.IMREAD_ANYDEPTH)

        edges = None
        if "edges" in attachments:
            edges_bytes = orthanc.RestApiGet(f"/instances/{instanceId}/attachments/edges/data")
            edges = cv2.imdecode(edges_bytes, cv2.IMREAD_GRAYSCALE)



        subLandmarks = []
        
        edge_threshold = image['edges']["threshold"][threshold] if (edges is not None and threshold in image_thresholds) else 0
        subLandmarks, distance = wu_line(x1, y1, x2, y2, heightmap, edges, edge_threshold)

        pixel_spacing = [float(x) for x in tags["PixelSpacing"].split("\\")]
        thickness = float(tags["SliceThickness"])
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
        
        smoothed_array = smooth(line_2d, distance)

        graph = [{
            "x": point[0],
            "y": point[1]
        } for point in smoothed_array.tolist()]   

        output.AnswerBuffer(json.dumps({
                "start": subLandmarks[0],
                "end" : subLandmarks[-1],
                "subLandmarks": graph
            }, indent=3), "application/json")
    else:
        output.SendMethodNotAllowed("GET")

def wu_line(x0, y0, x1, y1, heightmap : np.ndarray, edges : np.ndarray | None, threshold = 0):
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

    list_pixels =  []

    # get integer point before start point
    ratio_start = int(x0) - x0 if horizontal else int(y0) - y0
    start_x = int(x0) if horizontal else x0 + gradient*ratio_start
    start_y = y0 + gradient*ratio_start if horizontal else int(y0)
    for i in range(0, int(distance)+1):
        
        # iterate from int before start point to int after end point
        x = start_x + i if horizontal else start_x + i*gradient
        y = start_y + i*gradient if horizontal else start_y + i
        ix, iy = int(x), int(y)
        dist = y - iy  if horizontal else x - ix # swap dist if steep
        depth = getRatioedPixelHeight(ix, iy, 1.0 - dist, heightmap) + getRatioedPixelHeight(ix, iy+1, dist, heightmap) if horizontal else getRatioedPixelHeight(ix, iy, 1.0 - dist, heightmap) + getRatioedPixelHeight(ix+1, iy, dist, heightmap)
        isEdge = edges[iy,ix] >= threshold if edges is not None else True
        if isEdge:
            list_pixels.append(
                {
                    "x": x,
                    "y": y,
                    "z": depth,
                }
        )
    # Handle start point
    list_pixels[0] = {
                "x": x0,
                "y": y0,
                "z": list_pixels[0]["z"] * (1-abs(ratio_start)) + list_pixels[1]["z"] * abs(ratio_start),
            }
    
    
    # Handle end point
    ratio_end = math.ceil(x1) - x1 if horizontal else math.ceil(y1) - y1
    list_pixels[-1] = {
                "x": x1,
                "y": y1,
                "z": list_pixels[-1]["z"] * (1-abs(ratio_end)) + list_pixels[-2]["z"] * abs(ratio_end),
            }

    if inverse:
        list_pixels.reverse()
    
    
    return list_pixels, distance

def getRatioedPixelHeight(x : int, y : int, ratio : float, heightmap : np.ndarray):
    return heightmap[y,x] * ratio

def smooth(array, distance : float):
    x, y = array.T
    t = np.linspace(0, 1, len(x))
    t2 = np.linspace(0, 1, int(distance)*10)
    t3 = np.linspace(0, 1, 100)

    x2 = np.interp(t2, t, x)
    y2 = np.interp(t2, t, y)
    sigma = int(distance)/10
    x3 = x2
    y3 = gaussian_filter1d(y2, sigma)

    x4 = np.interp(t3, t2, x3).reshape((-1,1))
    y4 = np.interp(t3, t2, y3).reshape((-1,1))


    return np.concatenate((x4,y4),-1)


orthanc.RegisterRestCallback("/depthoptica/(.*)/images", images)
extension = """
    const DEPTHOPTICA_PLUGIN_SOP_CLASS_UID = '1.2.840.10008.5.1.4.1.1.77.1.4'
    $('#series').live('pagebeforeshow', function() {
      var seriesId = $.mobile.pageData.uuid;
    
      GetResource('/series/' + seriesId, function(series) {
        GetResource('/instances/' + series['Instances'][0] + '/tags?simplify', function(instance) {

          if (instance['SOPClassUID'] == DEPTHOPTICA_PLUGIN_SOP_CLASS_UID && instance.contains('SliceThickness')) {
            $('#depthoptica-button').remove();

            var b = $('<a>')
                .attr('id', 'depthoptica-button')
                .attr('data-role', 'button')
                .attr('href', '#')
                .attr('data-icon', 'search')
                .attr('data-theme', 'e')
                .text('Depthoptica Viewer')
                .button();

            b.insertAfter($('#series-info'));
            b.click(function(e) {
              window.open('../depthoptica/ui/index.html?series=' + seriesId);
            })
          }
        });
      });
    });
    """
orthanc.ExtendOrthancExplorer(extension)
