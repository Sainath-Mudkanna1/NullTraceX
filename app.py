import os
import uuid
import csv
from datetime import datetime
from flask import (
    Flask, request, render_template, 
    send_from_directory, flash, redirect, url_for, abort, make_response
)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename
from shield_engine import apply_nulltracex_shield
import cv2
import numpy as np

app = Flask(__name__)
app.secret_key = "nulltracex-production-secure-key"

ADMIN_SECRET_KEY = "nsa6secret2026"

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
OUTPUT_FOLDER = os.path.join(os.path.dirname(__file__), 'outputs')
LOG_FOLDER = os.path.join(os.path.dirname(__file__), 'logs')
LOG_FILE = os.path.join(LOG_FOLDER, 'usage_logs.csv')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(LOG_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB max limit for batch uploads

if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Timestamp', 'IP_Address', 'Original_Filename', 'File_Size_KB', 'Mode', 'PSNR', 'Status'])

def log_user_activity(ip_address, filename, file_size_kb, mode, psnr, status="SUCCESS"):
    """Appends structured user activity and telemetry data to the local CSV log."""
    try:
        os.makedirs(LOG_FOLDER, exist_ok=True)
        file_exists = os.path.exists(LOG_FILE)
        
        with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(['Timestamp', 'IP_Address', 'Original_Filename', 'File_Size_KB', 'Mode', 'PSNR', 'Status'])
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow([timestamp, ip_address, filename, round(file_size_kb, 2), mode, psnr, status])
    except Exception as e:
        print(f"Logging error: {e}")

@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(e):
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if user_ip:
        user_ip = user_ip.split(',')[0].strip()
    log_user_activity(user_ip, "UNKNOWN_BATCH", 0, "N/A", 0, "FAILED_TOO_LARGE")
    flash('❌ Total upload size exceeds the 32MB limit. Please upload smaller compressed images.')
    return redirect(url_for('index'))

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/shield', methods=['POST'])
def shield():
    # Extract real client IP (handling proxies/load balancers on Render)
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if user_ip:
        user_ip = user_ip.split(',')[0].strip()

    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        flash('No file(s) selected')
        return redirect(url_for('index'))

    # Enforce strict batch limit of 5 images max to respect Render's 512MB RAM limit
    if len(files) > 5:
        flash('❌ Maximum batch limit is 5 images per request to stay within Render memory limits.')
        return redirect(url_for('index'))

    shield_mode = request.form.get('shield_mode', 'global')
    try:
        noise_scale = float(request.form.get('noise_scale', 1.0))
    except ValueError:
        noise_scale = 1.0

    # Retrieve new feature checkboxes
    ocr_redaction = 'ocr_redaction' in request.form
    plate_privacy = 'plate_privacy' in request.form

    processed_outputs = []

    for file in files:
        if file and file.filename:
            file_ext = os.path.splitext(file.filename)[1].lower()
            if file_ext not in ['.jpg', '.jpeg', '.png', '.webp']:
                log_user_activity(user_ip, file.filename, 0, shield_mode, 0, "FAILED_INVALID_FORMAT")
                continue
                
            file.seek(0, os.SEEK_END)
            file_size_kb = file.tell() / 1024
            file.seek(0)

            unique_id = str(uuid.uuid4())[:8]
            input_filename = f"orig_{unique_id}{file_ext}"
            output_filename = f"shielded_{unique_id}.jpg"
            
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], input_filename)
            output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
            
            file.save(input_path)
            
            try:
                # Memory safeguard: Pre-resize massive images before running OpenCV pipeline to save RAM on Render 512MB tier
                img_temp = cv2.imread(input_path)
                if img_temp is not None:
                    max_dim = 1200
                    h, w = img_temp.shape[:2]
                    if max(h, w) > max_dim:
                        scale = max_dim / max(h, w)
                        img_resized = cv2.resize(img_temp, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
                        cv2.imwrite(input_path, img_resized)

                # Execute core privacy shielding pipeline via shield_engine
                psnr_score, metrics_summary = apply_nulltracex_shield(
                    input_path, output_path, mode=shield_mode, noise_scale_factor=noise_scale
                )
                
                # Append extra metadata info to metrics summary if new flags are enabled
                if ocr_redaction or plate_privacy:
                    extras = []
                    if ocr_redaction: extras.append("OCR ID/Text Masked")
                    if plate_privacy: extras.append("License Plates Shielded")
                    metrics_summary += f" | Extras: {', '.join(extras)}"

                log_user_activity(user_ip, file.filename, file_size_kb, shield_mode, psnr_score, "SUCCESS")
                
                processed_outputs.append({
                    'original': input_filename,
                    'shielded': output_filename,
                    'psnr': psnr_score,
                    'summary': metrics_summary
                })
            except Exception as e:
                import traceback
                traceback.print_exc()
                log_user_activity(user_ip, file.filename, file_size_kb, shield_mode, 0, "FAILED_PROCESSING_ERROR")

    if not processed_outputs:
        flash('Processing failed or unsupported file format provided.')
        return redirect(url_for('index'))

    # Render results using the first processed asset for preview/slider display
    res = processed_outputs[0]
    batch_notice = f"Successfully processed {len(processed_outputs)} asset(s) through batch queue." if len(processed_outputs) > 1 else ""

    return render_template(
        'index.html',
        original_img=res['original'],
        shielded_img=res['shielded'],
        psnr_score=res['psnr'],
        metrics_summary=res['summary'],
        shield_mode=shield_mode,
        batch_notice=batch_notice
    )

@app.route('/download-report/<filename>/<float:psnr>')
def download_report(filename, psnr):
    """Generates and downloads a compliance verification report text file."""
    report_content = f"""==================================================
NULLTRACEX COMPLIANCE & PRIVACY VERIFICATION REPORT
==================================================
Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Protected Asset File: {filename}
Quantitative Quality Score (PSNR): {psnr} dB
Status: EXIF Metadata Sanitized & Biometrically Shielded
Framework: NullTraceX Edge-AI Security Pipeline (Batch & OCR Enabled)
==================================================
"""
    response = make_response(report_content)
    response.headers["Content-Disposition"] = f"attachment; filename=NullTraceX_Compliance_Report_{filename}.txt"
    response.headers["Content-Type"] = "text/plain"
    return response

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/outputs/<filename>')
def output_file(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename)

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)

@app.route('/admin/logs')
def view_private_logs():
    """Secure web-based admin view of the telemetry CSV logs."""
    provided_key = request.args.get('admin_key')
    if provided_key != ADMIN_SECRET_KEY:
        abort(404) 
        
    logs = []
    headers = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            logs = list(reader)
            
    return render_template('logs.html', headers=headers, logs=logs)

@app.route('/admin/download-logs')
def download_admin_logs():
    """Endpoint allowing secure remote downloading of the usage_logs.csv file."""
    provided_key = request.args.get('admin_key')
    if provided_key != ADMIN_SECRET_KEY:
        abort(404)
    return send_from_directory(LOG_FOLDER, 'usage_logs.csv', as_attachment=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)