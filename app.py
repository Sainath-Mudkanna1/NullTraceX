import os
import uuid
import csv
from datetime import datetime
from flask import (
    Flask, request, render_template, 
    send_from_directory, flash, redirect, url_for, abort, make_response
)
from werkzeug.exceptions import RequestEntityTooLarge
from shield_engine import apply_nulltracex_shield

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
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max limit

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
    log_user_activity(user_ip, "UNKNOWN", 0, "N/A", 0, "FAILED_TOO_LARGE")
    flash('❌ File size exceeds the 16MB limit. Please upload a smaller compressed image.')
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

    if 'file' not in request.files:
        flash('No file selected')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('index'))

    shield_mode = request.form.get('shield_mode', 'global')
    try:
        noise_scale = float(request.form.get('noise_scale', 1.0))
    except ValueError:
        noise_scale = 1.0

    if file:
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in ['.jpg', '.jpeg', '.png', '.webp']:
            log_user_activity(user_ip, file.filename, 0, shield_mode, 0, "FAILED_INVALID_FORMAT")
            flash('Unsupported format. Please upload JPG, PNG, or WEBP.')
            return redirect(url_for('index'))
            
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
            psnr_score, metrics_summary = apply_nulltracex_shield(
                input_path, output_path, mode=shield_mode, noise_scale_factor=noise_scale
            )
            log_user_activity(user_ip, file.filename, file_size_kb, shield_mode, psnr_score, "SUCCESS")
            
            return render_template(
                'index.html',
                original_img=input_filename,
                shielded_img=output_filename,
                psnr_score=psnr_score,
                metrics_summary=metrics_summary,
                shield_mode=shield_mode
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            log_user_activity(user_ip, file.filename, file_size_kb, shield_mode, 0, "FAILED_PROCESSING_ERROR")
            flash(f'Detailed Error: {str(e)}')
            return redirect(url_for('index'))

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
Framework: NullTraceX Edge-AI Security Pipeline
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