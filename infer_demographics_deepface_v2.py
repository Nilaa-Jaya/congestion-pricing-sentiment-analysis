#!/usr/bin/env python3
"""
Demographic Inference from YouTube Profile Images using DeepFace (IMPROVED)

This script analyzes YouTube channel profile images to infer demographic attributes:
- Age
- Gender  
- Race/Ethnicity (dominant race)

IMPROVEMENTS:
- Properly validates face detection before analysis
- Skips images with no real faces (logos, letters, etc.)
- Uses enforce_detection=True for accuracy

Input:
    - Directory containing profile images (filename = channel_id.jpg/png/etc.)
    
Output:
    - CSV file with columns: channel_id, image_path, face_detected, age, gender, race
"""

import os
import glob
import csv
from pathlib import Path

from deepface import DeepFace


def analyze_image(image_path):
    """
    Analyze a single image using DeepFace to detect face and infer demographics.
    
    This version PROPERLY validates face detection by:
    1. First attempting strict face detection
    2. Only analyzing demographics if a face is actually found
    
    Args:
        image_path: Path to the image file
        
    Returns:
        dict: Contains face_detected (bool), age, gender, race
    """
    try:
        # Step 1: Try to detect face with STRICT enforcement
        # This will throw an exception if no face is found
        result = DeepFace.analyze(
            img_path=image_path,
            actions=["age", "gender", "race"],
            enforce_detection=True,  # STRICT: Only analyze if face is detected
            detector_backend='opencv',  # Faster, good for profile images
            silent=True
        )
        
        # If we get here, a face was detected!
        
        # Handle both single result and list of results
        if isinstance(result, list):
            if len(result) == 0:
                return {
                    "face_detected": False,
                    "age": None,
                    "gender": None,
                    "race": None
                }
            # Take the first (most prominent) face
            result = result[0]
        
        # Extract demographics
        age = result.get("age")
        
        # Gender: extract dominant gender
        gender_dict = result.get("gender", {})
        if isinstance(gender_dict, dict):
            gender = max(gender_dict, key=gender_dict.get) if gender_dict else None
        else:
            gender = gender_dict
            
        # Race: get dominant race
        race = result.get("dominant_race")
        
        return {
            "face_detected": True,
            "age": age,
            "gender": gender,
            "race": race
        }
        
    except ValueError as e:
        # This means no face was detected (which is expected for logos/letters)
        if "Face could not be detected" in str(e) or "Detected face shape" in str(e):
            return {
                "face_detected": False,
                "age": None,
                "gender": None,
                "race": None
            }
        else:
            # Some other ValueError
            print(f"    ⚠️  ValueError: {e}")
            return {
                "face_detected": False,
                "age": None,
                "gender": None,
                "race": None
            }
            
    except Exception as e:
        # Any other error
        print(f"    ⚠️  Error analyzing image: {e}")
        return {
            "face_detected": False,
            "age": None,
            "gender": None,
            "race": None
        }


def process_images(image_dir, output_csv):
    """
    Process all images in a directory and save results to CSV.
    
    Args:
        image_dir: Directory containing profile images
        output_csv: Path to output CSV file
    """
    # Find all image files
    image_extensions = ["*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp", "*.gif"]
    image_paths = []
    
    for ext in image_extensions:
        image_paths.extend(glob.glob(os.path.join(image_dir, ext)))
    
    if not image_paths:
        print(f"❌ No images found in {image_dir}")
        return
    
    image_paths = sorted(image_paths)
    print(f"📊 Found {len(image_paths)} images in {image_dir}\n")
    
    results = []
    
    # Process each image
    for idx, image_path in enumerate(image_paths, 1):
        filename = os.path.basename(image_path)
        channel_id = os.path.splitext(filename)[0]
        
        print(f"[{idx}/{len(image_paths)}] Processing: {filename}")
        
        # Analyze image
        demographics = analyze_image(image_path)
        
        # Prepare result row
        row = {
            "channel_id": channel_id,
            "image_path": filename,
            "face_detected": demographics["face_detected"],
            "age": demographics["age"],
            "gender": demographics["gender"],
            "race": demographics["race"]
        }
        
        results.append(row)
        
        # Print results
        if demographics["face_detected"]:
            print(f"    ✓ FACE DETECTED - Age: {demographics['age']}, Gender: {demographics['gender']}, Race: {demographics['race']}")
        else:
            print(f"    ✗ No face detected (likely logo/letter/graphic)")
        
        print()
    
    # Save results to CSV
    output_path = Path(output_csv)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    fieldnames = ["channel_id", "image_path", "face_detected", "age", "gender", "race"]
    
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    
    # Print summary
    faces_detected = sum(1 for r in results if r["face_detected"])
    no_faces = len(results) - faces_detected
    
    print("=" * 60)
    print(f"✅ Analysis complete!")
    print(f"📈 Total images processed: {len(results)}")
    print(f"👤 Real faces detected: {faces_detected} ({faces_detected/len(results)*100:.1f}%)")
    print(f"🚫 No faces (logos/letters): {no_faces} ({no_faces/len(results)*100:.1f}%)")
    print(f"💾 Results saved to: {output_csv}")
    print("=" * 60)


def main():
    """Main entry point"""
    # Configuration
    IMAGE_DIR = "data/youtube_images/"
    OUTPUT_CSV = "data/deepface_demographics_v2.csv"
    
    print("=" * 60)
    print("🔍 DeepFace Demographic Inference (IMPROVED)")
    print("=" * 60)
    print(f"Input directory: {IMAGE_DIR}")
    print(f"Output CSV: {OUTPUT_CSV}")
    print("=" * 60)
    print()
    
    # Check if image directory exists
    if not os.path.exists(IMAGE_DIR):
        print(f"❌ Error: Image directory not found: {IMAGE_DIR}")
        print(f"Please create the directory and add images first.")
        return
    
    # Process images
    process_images(IMAGE_DIR, OUTPUT_CSV)


if __name__ == "__main__":
    main()
