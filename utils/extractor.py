import cv2
import numpy as np
import os
from PIL import Image
import imagehash


def extract_slides(video_path, slides_folder="temp/slides", progress_callback=None):
    os.makedirs(slides_folder, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Cannot open video")

    # --- Video Properties ---
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30

    # --- TUNING PARAMETERS ---
    SAMPLE_RATE = 3                       # Check every 3rd frame
    STABLE_SECONDS = 3                    # Slide must be stable for 3 seconds
    CHANGE_PERCENT_THRESHOLD = 0.03       # 3% pixels changed = still considered stable (filters noise)
    
    # --- PREPROCESSING PARAMETERS ---
    RESIZE_W, RESIZE_H = 64, 64
    BLUR_KERNEL = (11, 11)

    # Calculate required frames
    MIN_STABLE_SAMPLES = int(STABLE_SECONDS * fps / SAMPLE_RATE)
    # The actual frame count required for a save (for the duration check)
    STABLE_FRAMES_REQUIRED = int(fps * STABLE_SECONDS) 

    # --- STATE VARIABLES ---
    frame_id = 0
    consecutive_stable_samples = 0
    slide_id = 1
    slide_paths = []
    
    # Critical variables for duplicate prevention and time-gating
    is_stable_slide_active = False          # True if a long, stable slide is currently being displayed
    last_stable_start_frame = None          # Stores the frame when stability was first confirmed
    last_stable_start_frame_id = -1         # Stores the frame_id when stability was first confirmed

    # --- Initialize First Frame ---
    ret, initial_frame = cap.read()
    if not ret:
        return []
        # We need a dedicated final check to save the last slide if it was stable
        pass # The initial frame handling covers this case effectively if the slide lasts long enough.
    cap.release()

# Remove duplicates before returning
    slide_paths = remove_duplicate_slides(slide_paths)

    return slide_paths

def remove_duplicate_slides(slide_paths, threshold=5):
    """
    Remove ALL duplicate slides (contiguous and non-contiguous) 
    by comparing perceptual hash (pHash) against all unique slides found so far.
    """
    if not slide_paths:
        return slide_paths
    
    # Store the hashes of all slides that are considered unique
    unique_hashes = set()
    
    # Store the file paths of all unique slides
    final_unique_paths = []

    for path in slide_paths:
        try:
            current_hash = imagehash.phash(Image.open(path))
        except FileNotFoundError:
            # Skip if file was removed by an earlier process (shouldn't happen here, but safe practice)
            continue
        
        is_duplicate = False
        
        # Compare current hash against all hashes in the unique set
        for unique_hash in unique_hashes:
            # imagehash overloads the subtraction operator for Hamming distance
            diff = abs(unique_hash - current_hash)
            
            if diff < threshold:
                is_duplicate = True
                break # Found a duplicate, stop comparing
        
        if is_duplicate:
            # Delete the file and do NOT add its path/hash to the unique lists
            os.remove(path)
        else:
            # It's a unique slide!
            final_unique_paths.append(path)
            unique_hashes.add(current_hash)
            
    return final_unique_paths