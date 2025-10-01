# Stackoptica - 3D Viewer on calibrated images - Orthanc Plugin

# Copyright (C) 2024 Yann Pollet, Royal Belgian Institute of Natural Sciences

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

# along with this program. If not, see <https://www.gnu.org/licenses/>.

from io import BytesIO
import PIL
import datetime
import pydicom
from pydicom.valuerep import VR
import glob
import json
import requests
import os

path_to_project = "data/insect"
SOURCE = f"{path_to_project}/*.jpg"
calib_file = f"{path_to_project}/depth.json"
images = sorted(glob.glob(SOURCE))
i = 0


with open(calib_file, "rb") as f:
    depth_dict = json.load(f)

images = sorted(depth_dict["stacked"].keys())
study_uid = pydicom.uid.generate_uid()
print(study_uid)
series_uid = pydicom.uid.generate_uid()

thumbnails_width = 1500
thumbnails_height = 1000

images = depth_dict["stacked"]

now = datetime.datetime.now()

for image_name in images:
    image = f"{path_to_project}/{image_name}"
    image_data = images[image_name]["data"]

    ds = pydicom.dataset.Dataset()
    ds.PatientName = "Geonemus^goeffroyi^focus"
    ds.PatientID = "Geonemus12457454"
    ds.PatientBirthDate = "20200914"
    ds.PatientSex = "O"

    ds.StudyDate = now.strftime("%Y%m%d")
    ds.StudyTime = now.strftime("%H%M%S")

    ds.ImageType = ["DERIVED", "SECONDARY"]
    ds.UserContentLabel = image_data["label"]
    ds.Laterality = "L"
    ds.LossyImageCompression = "01"
    ds.Modality = "XC"  # External-camera photography
    ds.SOPClassUID = pydicom.uid.VLPhotographicImageStorage
    ds.SOPInstanceUID = pydicom.uid.generate_uid()
    ds.SeriesInstanceUID = series_uid
    ds.StudyInstanceUID = study_uid

    ds.AccessionNumber = None
    ds.ReferringPhysicianName = None
    ds.SeriesNumber = None
    ds.StudyID = None
    ds.StudyDescription = "Focus_stacking test"
    ds.SeriesDescription = "5x MP-E 65mm"
    ds.InstanceNumber = None
    ds.Manufacturer = None
    ds.AcquisitionContextSequence = None
    ds.InstanceNumber = i + 1

    # Basic encapsulation of color JPEG
    # httpss://pydicom.github.io/pydicom/stable/tutorials/pixel_data/compressing.html

    with open(image, "rb") as f:
        frames = [f.read()]
        ds.PixelData = pydicom.encaps.encapsulate(frames)

    with PIL.Image.open(image) as im:
        ds.Rows = im.size[1]
        ds.Columns = im.size[0]

        im.thumbnail((thumbnails_width, thumbnails_height))
        thumbnail_buffer = BytesIO()
        im.save(thumbnail_buffer, format="JPEG")

    with PIL.Image.open(
        f"{path_to_project}/{depth_dict['stacked'][image_name]['layers']}"
    ) as im:
        layers_buffer = BytesIO()
        im.save(layers_buffer, format="JPEG")

    with PIL.Image.open(
        f"{path_to_project}/{depth_dict['stacked'][image_name]['depthmap']}"
    ) as im:
        depthmap_buffer = BytesIO()
        im.save(depthmap_buffer, format="JPEG")

    ds.PlanarConfiguration = 0
    ds.SamplesPerPixel = 3
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PhotometricInterpretation = "YBR_FULL_422"

    ds.PixelSpacing = image_data["PixelRatio"]
    ds.NumberOfFrames = (image_data["Zmax"] - image_data["Zmin"]) / image_data["step"]
    ds.SliceThickness = image_data["Zmax"] - image_data["Zmin"]

    ds["PixelData"].VR = "OB"  # always for encapsulated pixel data
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    meta = pydicom.dataset.FileMetaDataset()
    meta.TransferSyntaxUID = pydicom.uid.JPEGBaseline8Bit
    ds.file_meta = meta

    out: BytesIO = BytesIO()
    ds.save_as(out, write_like_original=False)

    response = requests.post("http://localhost:8042/instances", out.getvalue())

    response.raise_for_status()

    uuid = response.json()["ID"]
    series_uuid = response.json()["ParentSeries"]

    r = requests.put(
        f"http://localhost:8042/instances/{uuid}/attachments/thumbnail",
        data=thumbnail_buffer.getvalue(),
    )

    r = requests.put(
        f"http://localhost:8042/instances/{uuid}/attachments/layers",
        data=layers_buffer.getvalue(),
    )

    r = requests.put(
        f"http://localhost:8042/instances/{uuid}/attachments/depthmap",
        data=depthmap_buffer.getvalue(),
    )

    i += 1
