import cv2
import numpy as np
import os
from PIL import Image
import imagehash


def extract_slides(video_path, slides_folder="temp/slides"):
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
    
    # Process initial frame for comparison
    prev_small = cv2.resize(initial_frame, (RESIZE_W, RESIZE_H))
    prev_small = cv2.GaussianBlur(prev_small, BLUR_KERNEL, 0)
    prev_gray = cv2.cvtColor(prev_small, cv2.COLOR_BGR2GRAY)
    
    # Treat the first frame as the first stable frame
    last_stable_start_frame = initial_frame.copy() 
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_id += 1
        current_original_frame = frame.copy() # Store original frame for potential save

        # --- Sampling ---
        if frame_id % SAMPLE_RATE != 0:
            continue

        # --- Preprocessing ---
        small = cv2.resize(current_original_frame, (RESIZE_W, RESIZE_H))
        small = cv2.GaussianBlur(small, BLUR_KERNEL, 0)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

        # --- Difference Calculation ---
        diff = cv2.absdiff(prev_gray, gray)
        _, mask = cv2.threshold(diff, 15, 255, cv2.THRESH_BINARY) # Threshold to detect "changed" pixels

        changed = np.count_nonzero(mask)
        total = RESIZE_W * RESIZE_H
        change_percent = changed / total

        # --- Stability Check ---
        if change_percent < CHANGE_PERCENT_THRESHOLD:
            # Frame is stable
            consecutive_stable_samples += 1
        else:
            # Frame is actively changing (slide transition or animation)
            consecutive_stable_samples = 0
            is_stable_slide_active = False # New change has started

        # --- Slide Saving Logic (Duplicate Prevention) ---

        # Condition 1: Stable for the required number of *samples*
        if consecutive_stable_samples >= MIN_STABLE_SAMPLES:
            
            # Save the slide ONLY if this is the FIRST time we crossed the stability threshold
            if not is_stable_slide_active:
                
                # Check if the slide also meets the minimum time duration requirement
                # Note: We save the frame *before* the current frame_id, because the stable period was confirmed
                # over the previous samples. We need to save the frame at the start of the stability.
                
                slide_path = f"{slides_folder}/slide_{slide_id}.jpg"
                cv2.imwrite(slide_path, last_stable_start_frame) # Save the representative frame
                slide_paths.append(slide_path)
                slide_id += 1
                
                is_stable_slide_active = True # LOCK: Prevent saving again until a change breaks the stability
                last_stable_start_frame_id = frame_id # Mark the end of the transition period

        # --- Update previous state for next sampled frame ---
        prev_gray = gray
        
        # If the slide is NOT stable, update the representative frame to the *current* original frame
        # This frame will become the start of the next potential stable slide.
        if not is_stable_slide_active:
            last_stable_start_frame = current_original_frame.copy()

    cap.release()

    
    if is_stable_slide_active:
        # Save the last stable frame (since the loop ended, no new change will break stability)
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