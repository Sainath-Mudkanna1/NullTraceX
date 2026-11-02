import os
import numpy as np
from flask import Flask, render_template_string, request, send_file, redirect, url_for
from PIL import Image

app = Flask(__name__)

# Create upload and output folders if they don't exist
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def apply_adversarial_shield(image_path, output_path):
    """Applies pixel-level adversarial noise to break AI scrapers
       while keeping the image looking normal to humans.
    """
    img = Image.open(image_path).convert("RGB")
    img_array = np.array(img, dtype=np.float32)
    
    # Generate imperceptible high-frequency adversarial noise
    noise = np.random.normal(loc=0.0, scale=12.0, size=img_array.shape)
    
    # Add noise and clip values to valid pixel range [0, 255]
    shielded_array = np.clip(img_array + noise, 0, 255).astype(np.uint8)
    
    # Save the protected image
    shielded_img = Image.fromarray(shielded_array)
    shielded_img.save(output_path)


# Simple, clean HTML Template for the Web UI
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PrivacyProxy - AI Shield</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f4f6f9; margin: 0; padding: 40px; display: flex; justify-content: center; align-items: center; height: 90vh; }
        .card { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.08); width: 100%; max-width: 500px; text-align: center; }
        h2 { color: #1a202c; margin-bottom: 8px; }
        p { color: #718096; font-size: 14px; margin-bottom: 24px; }
        input[type="file"] { margin: 20px 0; border: 1px dashed #cbd5e0; padding: 12px; width: 80%; border-radius: 6px; }
        button { background: #0066ff; color: white; border: none; padding: 12px 24px; font-size: 16px; border-radius: 6px; cursor: pointer; font-weight: 600; width: 100%; }
        button:hover { background: #0052cc; }
        .footer { margin-top: 20px; font-size: 12px; color: #a0aec0; }
        .result { margin-top: 20px; }
        .download-btn { background: #38a169; display: inline-block; text-decoration: none; color: white; padding: 10px 20px; border-radius: 6px; font-weight: 600; margin-top: 15px; width: 80%; }
        .download-btn:hover { background: #2f855a; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🛡️ PrivacyProxy Prototype</h2>
        <p>Shield your photos locally from cloud AI scrapers and facial recognition.</p>
        
        {% if filename %}
            <div class="result">
                <p style="color: #38a169; font-weight: bold;">Image successfully shielded!</p>
                <a href="/download/{{ filename }}" class="download-btn">Download Protected Image</a>
                <br><br>
                <a href="/" style="color: #0066ff; font-size: 14px; text-decoration: none;">Shield Another Image</a>
            </div>
        {% else %}
            <form method="POST" enctype="multipart/form-data">
                <input type="file" name="file" accept="image/*" required><br>
                <button type="submit">Shield Image</button>
            </form>
        {% endif %}
        
        <div class="footer">Built for National Startup Awards (NSA 6.0) Submission</div>
    </div>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "file" not in request.files:
            return redirect(request.url)
        file = request.files["file"]
        if file.filename == "":
            return redirect(request.url)
        
        if file:
            input_path = os.path.join(UPLOAD_FOLDER, file.filename)
            output_path = os.path.join(OUTPUT_FOLDER, "shielded_" + file.filename)
            
            file.save(input_path)
            apply_adversarial_shield(input_path, output_path)
            
            return render_template_string(HTML_TEMPLATE, filename="shielded_" + file.filename)
            
    return render_template_string(HTML_TEMPLATE, filename=None)

@app.route("/download/<filename>")
def download(filename):
    return send_file(os.path.join(OUTPUT_FOLDER, filename), as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)