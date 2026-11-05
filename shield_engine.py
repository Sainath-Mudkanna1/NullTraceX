import os
import cv2
import numpy as np
from PIL import Image

def calculate_psnr(original_array, shielded_array):
    """Calculates Peak Signal-to-Noise Ratio (PSNR) between original and shielded images."""
    mse = np.mean((original_array.astype(np.float32) - shielded_array.astype(np.float32)) ** 2)
    if mse == 0:
        return 100.0
    max_pixel = 255.0
    psnr = 20 * np.log10(max_pixel / np.sqrt(mse))
    return round(float(psnr), 2)

def apply_nulltracex_shield(image_path, output_path, mode="global", noise_scale_factor=1.0):
    """
    NullTraceX Dual-Engine Processing Suite with Automatic Fallback Protection.
    """
    raw_img = Image.open(image_path).convert("RGB")
    
    # Memory guardrail: constrain max image bounds to 1000px
    max_size = (1000, 1000)
    raw_img.thumbnail(max_size, Image.Resampling.LANCZOS)
    
    original_array = np.array(raw_img, dtype=np.uint8)
    h, w, c = original_array.shape
    
    if mode == "targeted":
        try:
            gray = cv2.cvtColor(original_array, cv2.COLOR_RGB2GRAY)
            face_cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            face_cascade = cv2.CascadeClassifier(face_cascade_path)
            
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
            shielded_array = original_array.copy()
            faces_detected_count = len(faces)
            
            for (x, y, fw, fh) in faces:
                face_roi = shielded_array[y:y+fh, x:x+fw]
                small_face = cv2.resize(face_roi, (max(1, fw // 10), max(1, fh // 10)), interpolation=cv2.INTER_LINEAR)
                pixelated_face = cv2.resize(small_face, (fw, fh), interpolation=cv2.INTER_NEAREST)
                shielded_array[y:y+fh, x:x+fw] = pixelated_face
                
            metrics_summary = f"Targeted Redaction Active: {faces_detected_count} face(s) successfully masked."
        except Exception as cv_err:
            # Fallback if cascade fails to initialize in local environment
            print(f"OpenCV Cascade warning: {cv_err}, falling back to noise perturbation.")
            img_float = original_array.astype(np.float32)
            noise = np.random.normal(loc=0.0, scale=10.0 * noise_scale_factor, size=(h, w, c))
            shielded_array = np.clip(img_float + noise, 0, 255).astype(np.uint8)
            metrics_summary = "Targeted Engine Fallback: Applied Adversarial Noise."
    else:
        # Global Adversarial Noise Shield Mode
        img_float = original_array.astype(np.float32)
        fine_noise = np.random.normal(loc=0.0, scale=10.0 * noise_scale_factor, size=(h, w, c))
        
        coarse_small = np.random.normal(loc=0.0, scale=8.0 * noise_scale_factor, size=(h // 4 or 1, w // 4 or 1, c))
        coarse_img = Image.fromarray(np.clip(coarse_small, 0, 255).astype(np.uint8))
        coarse_noise = np.array(coarse_img.resize((w, h), Image.Resampling.BILINEAR), dtype=np.float32)
        
        combined_noise = fine_noise + coarse_noise
        shielded_array = np.clip(img_float + combined_noise, 0, 255).astype(np.uint8)
        metrics_summary = "Global Adversarial Noise Injection & EXIF Sanitization Applied."

    # Compute quantitative PSNR score
    psnr_score = calculate_psnr(original_array, shielded_array)
    
    # Save protected image
    shielded_img = Image.fromarray(shielded_array, mode="RGB")
    shielded_img.save(output_path, "JPEG", quality=92, optimize=True)
    
    return psnr_score, metrics_summary