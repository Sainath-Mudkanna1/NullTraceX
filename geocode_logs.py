import csv
import requests
import os

LOG_FILE = "logs/usage_logs.csv"
UPDATED_LOG_FILE = "logs/usage_logs_with_location.csv"

def is_private_ip(ip):
    """Checks if an IP is a local loopback or private network address."""
    if not ip or ip in ["127.0.0.1", "localhost", "::1"]:
        return True
    
    # Check standard private IP ranges (10.x, 192.168.x, 172.16-31.x)
    parts = ip.split('.')
    if len(parts) == 4:
        try:
            p1, p2 = int(parts[0]), int(parts[1])
            if p1 == 10:
                return True
            if p1 == 192 and p2 == 168:
                return True
            if p1 == 172 and (16 <= p2 <= 31):
                return True
        except ValueError:
            pass
            
    return False

def get_location_from_ip(ip_address):
    if is_private_ip(ip_address):
        return "Internal / Local Network"
    
    try:
        # Querying ipapi.co free tier (rate limit ~45 requests/minute)
        response = requests.get(f"https://ipapi.co/{ip_address}/json/", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if "error" in data:
                return f"Lookup Failed: {data.get('reason', 'Unknown')}"
            
            city = data.get("city", "Unknown")
            region = data.get("region", "Unknown")
            country = data.get("country_name", "Unknown")
            org = data.get("org", "Unknown ISP")
            return f"{city}, {region}, {country} ({org})"
    except Exception as e:
        print(f"Error fetching IP {ip_address}: {e}")
    
    return "Geolocation Unavailable"

def process_logs():
    if not os.path.exists(LOG_FILE):
        print(f"Error: {LOG_FILE} not found!")
        return

    updated_rows = []
    with open(LOG_FILE, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            return
        
        # Add 'Location' column to header if not already present
        if 'Location' not in header:
            header.append('Location')
        
        for row in reader:
            if len(row) > 1:
                ip = row[1]  # IP_Address is the 2nd column
                print(f"Processing IP: {ip}...")
                location = get_location_from_ip(ip)
                row.append(location)
                updated_rows.append(row)

    # Save to a new enriched CSV file
    with open(UPDATED_LOG_FILE, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(updated_rows)
    
    print(f"\nSuccessfully generated location-enriched logs at: {UPDATED_LOG_FILE}")

if __name__ == "__main__":
    process_logs()