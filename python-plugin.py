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


def get_response_layers(instance) -> bytearray:
    return orthanc.RestApiGet(f"/instances/{instance}/attachments/layers/data")


def get_response_depthmap(instance) -> bytearray:
    return orthanc.RestApiGet(f"/instances/{instance}/attachments/depthmap/data")


def compute_landmark(output, uri, **request):
    if request["method"] == "GET":
        instanceId = request["groups"][0]

        x = float(request.args.get("x"))
        y = float(request.args.get("y"))

        orthanc.LogWarning(f"Compute position of ({x};{y}) at {instanceId}")

        layer = int(request.args.get("layer"))
        depth = int(request.args.get("depth"))

        tags = json.loads(
            orthanc.RestApiGet(f"/instances/{instanceId}/simplified-tags")
        )

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

        output.AnswerBuffer(json.dumps(position, indent=3), "application/json")
    else:
        output.SendMethodNotAllowed("GET")


orthanc.RegisterRestCallback("/depthoptica/(.*)/position", compute_landmark)


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


# send layers image
def layers(output, uri, **request):
    if request["method"] == "GET":
        instanceId = request["groups"][0]
        orthanc.LogWarning(f"Request layers image of {instanceId}")
        try:
            instanceId = request["groups"][0]
            image_binary = get_response_layers(instanceId)
            output.AnswerBuffer(image_binary, "image/jpeg")
        except Exception as error:
            orthanc.LogError(error)
    else:
        output.SendMethodNotAllowed("GET")


orthanc.RegisterRestCallback("/depthoptica/(.*)/layers", layers)


# send depthmap image
def depthmap(output, uri, **request):
    if request["method"] == "GET":
        instanceId = request["groups"][0]
        orthanc.LogWarning(f"Request depthmap image of {instanceId}")
        try:
            instanceId = request["groups"][0]
            image_binary = get_response_depthmap(instanceId)
            output.AnswerBuffer(image_binary, "image/jpeg")
        except Exception as error:
            orthanc.LogError(error)
    else:
        output.SendMethodNotAllowed("GET")


orthanc.RegisterRestCallback("/depthoptica/(.*)/depthmap", depthmap)


# send images
def images(output, uri, **request):
    if request["method"] == "GET":
        seriesId = request["groups"][0]
        orthanc.LogWarning(f"Request depthoptica camera images of {seriesId}")
        try:
            orthanc_dict = json.loads(
                orthanc.RestApiGet(f"/series/{seriesId}/instances-tags?simplify")
            )

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
            to_jsonify["thumbnails"] = True
            output.AnswerBuffer(json.dumps(to_jsonify), "application/json")
        except ValueError as e:
            orthanc.LogError(e)
    else:
        output.SendMethodNotAllowed("GET")


orthanc.RegisterRestCallback("/depthoptica/(.*)/images", images)
extension = """
    const DEPTHOPTICA_PLUGIN_SOP_CLASS_UID = '1.2.840.10008.5.1.4.1.1.77.1.4'
    $('#series').live('pagebeforeshow', function() {
      var seriesId = $.mobile.pageData.uuid;
    
      GetResource('/series/' + seriesId, function(series) {
        GetResource('/instances/' + series['Instances'][0] + '/tags?simplify', function(instance) {

          if (instance['SOPClassUID'] == DEPTHOPTICA_PLUGIN_SOP_CLASS_UID) {
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
