# -*- coding: utf-8 -*-
"""
Created on Wed Jan 22 07:38:14 2025

@author: observatory
"""

import zwoasi as asi
import numpy as np
from PIL import Image

def initialize_zwo_sdk(sdk_path):
    """
    Initialize the ZWO ASI SDK.

    :param sdk_path: Path to the ASI SDK library (e.g., asi.dll, libasi.so, libasi.dylib).
    """
    asi.init(sdk_path)

def capture_image(camera_index=0, exposure_time_ms=100, gain=100, output_file="capture.png"):
    """
    Captures an image using a ZWO camera and saves it to a file.

    :param camera_index: Index of the camera (default: 0 for the first connected camera)
    :param exposure_time_ms: Exposure time in milliseconds
    :param gain: Gain value for the camera
    :param output_file: Output file path for the captured image
    """
    # Check connected cameras
    num_cameras = asi.get_num_cameras()
    if num_cameras == 0:
        print("No ZWO cameras detected.")
        return

    print(f"Number of cameras detected: {num_cameras}")

    # Get camera details
    camera = asi.Camera(camera_index)
    camera_info = camera.get_camera_property()
    print(f"Using camera: {camera_info['Name']}")

    # Configure camera settings
    camera.set_control_value(asi.ASI_EXPOSURE, exposure_time_ms * 1)  # Convert to microseconds
    camera.set_control_value(asi.ASI_GAIN, gain)
    camera.set_control_value(asi.ASI_BANDWIDTHOVERLOAD, 40)  # Optional: Adjust for your system
    camera.set_image_type(asi.ASI_IMG_RAW8)  # Use RAW8 image type

    # Start exposure
    print("Capturing image...")
    camera.start_exposure()
    camera_status = camera.get_exposure_status()

    if camera_status == asi.ASI_EXP_FAILED:
        print("Exposure failed!")
        return

    # Wait for exposure to complete
    while camera_status == asi.ASI_EXP_WORKING:
        camera_status = camera.get_exposure_status()
        print (camera_status)

    # Retrieve image data
    frame = camera.get_data_after_exposure()
    print(f"Frame size: {len(frame)} bytes")

    # Get image dimensions from ROI
    roi_format = camera.get_roi_format()
    #breakpoint()
    width, height = roi_format[0], roi_format[1]
    print(f"Image dimensions: Width={width}, Height={height}")

    # Ensure the frame size matches the expected dimensions
    expected_size = width * height
    if len(frame) != expected_size:
        print(f"Mismatch: Expected size={expected_size}, Actual size={len(frame)}")
        return

    # Save the frame as an image
    image_array = np.frombuffer(frame, dtype=np.uint8).reshape(height, width)
    image = Image.fromarray(image_array)
    image.save(output_file)
    print(f"Image saved to {output_file}")

    # Close the camera
    camera.close()

if __name__ == "__main__":
    # Provide the path to the ZWO ASI SDK
    SDK_PATH = "support_info/ASISDK/lib/x64/ASICamera2.dll"
    initialize_zwo_sdk(SDK_PATH)

    # Capture an image
    capture_image()