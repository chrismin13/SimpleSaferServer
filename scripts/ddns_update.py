#!/usr/bin/env python3

import sys
import json
import logging
import os
import urllib.request
import urllib.error
from urllib.parse import quote
from datetime import datetime
from pathlib import Path

def _add_app_to_path():
    script_path = Path(__file__).resolve()
    candidates = [
        script_path.parents[1],
        Path('/opt/SimpleSaferServer'),
    ]
    for candidate in candidates:
        if (candidate / 'drive_health.py').exists():
            sys.path.insert(0, str(candidate))
            return

_add_app_to_path()

from config_manager import ConfigManager
from runtime import get_runtime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('DDNSUpdater')

def get_public_ip():
    services = [
        "https://api.ipify.org",
        "https://ipv4.icanhazip.com"
    ]
    for url in services:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                ip = response.read().decode('utf-8').strip()
                if ip:
                    return ip
        except Exception as e:
            logger.debug(f"Failed to fetch IP from {url}. Error: {e}")
            continue
    return None

def update_duckdns(domain, token, ipv4):
    logger.info(f"Updating DuckDNS domain '{domain}' with IP {ipv4 if ipv4 else 'auto'}...")
    encoded_domain = quote(domain)
    encoded_token = quote(token)
    url = f"https://www.duckdns.org/update?domains={encoded_domain}&token={encoded_token}"
    if ipv4:
        encoded_ipv4 = quote(ipv4)
        url += f"&ip={encoded_ipv4}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            result = response.read().decode('utf-8').strip()
            if result == "OK":
                return True, "OK"
            else:
                return False, f"API returned: {result}"
    except urllib.error.URLError as e:
        return False, f"Connection Error: {e.reason}"
    except Exception as e:
        return False, str(e)

def get_cloudflare_record(zone_id, token, record_name):
    encoded_record_name = quote(record_name)
    url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records?type=A&name={encoded_record_name}"
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('success'):
                records = data.get('result', [])
                if records:
                    return records[0]['id'], records[0].get('content')
    except urllib.error.HTTPError as e:
        logger.error(f"Cloudflare record fetch API error: {e.code}")
        raise
    except Exception as e:
        logger.error(f"Cloudflare record fetch error: {e}")
        raise
    return None, None

def update_cloudflare(zone_id, token, record_name, ip, proxy):
    logger.info(f"Updating Cloudflare record '{record_name}' in zone '{zone_id}' with IP {ip}...")
    try:
        record_id, existing_ip = get_cloudflare_record(zone_id, token, record_name)
        if not record_id:
            return False, "Record does not exist."
        if existing_ip == ip:
            return True, "IP hasn't changed."

        url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}"
        payload = json.dumps({
            "type": "A",
            "name": record_name,
            "content": ip,
            "proxied": proxy.lower() == 'true',
            "ttl": 3600 if proxy.lower() != 'true' else 1
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }, method='PUT')  # Cloudflare v4 API requires PUT (not PATCH) to update a DNS record
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('success'):
                return True, "Updated successfully"
            else:
                # Surface the API error messages for easier debugging
                errors = data.get('errors', [])
                error_messages = "; ".join(
                    error.get('message', str(error)) if isinstance(error, dict) else str(error)
                    for error in errors
                )
                return False, error_messages or "API returned failure"
    except urllib.error.HTTPError as e:
        return False, f"HTTP Error {e.code}: {e.read().decode('utf-8')}"
    except urllib.error.URLError as e:
        return False, f"Connection Error: {e.reason}"
    except Exception as e:
        return False, str(e)

def main():
    runtime = get_runtime()
    config = ConfigManager(runtime=runtime)

    duckdns_enabled = config.get_value('ddns', 'duckdns_enabled', 'false') == 'true'
    cf_enabled = config.get_value('ddns', 'cloudflare_enabled', 'false') == 'true'

    if not duckdns_enabled and not cf_enabled:
        logger.info("No DDNS services enabled.")
        sys.exit(0)

    status_file = runtime.data_dir / 'ddns_status.json'
    try:
        if status_file.exists():
            status_data = json.loads(status_file.read_text())
        else:
            status_data = {}
    except Exception:
        status_data = {}

    ipv4 = get_public_ip()
    if ipv4:
        status_data['ipv4'] = ipv4
    else:
        logger.warning("Could not fetch IPv4. Falling back to duckdns auto-detect for DuckDNS, but Cloudflare will fail.")

    status_data['last_check'] = datetime.now().isoformat()

    duckdns_new_status = status_data.get('duckdns', {})
    if duckdns_enabled:
        domain = config.get_value('ddns', 'duckdns_domain', '')
        token = config.get_secret('duckdns_token', '')
        if domain and token:
            success, msg = update_duckdns(domain, token, ipv4)
            duckdns_new_status['status'] = 'Success' if success else 'Error'
            duckdns_new_status['message'] = msg
            logger.info(f"DuckDNS Update result: {duckdns_new_status['status']} - {msg}")

            # Alert once per unique error message to avoid alert spam
            if not success and "Connection" not in msg:
                if status_data.get('duckdns', {}).get('message') != msg:
                    config.log_alert("DuckDNS DDNS Update Failed", f"Domain {domain}: {msg}", alert_type="error")
        else:
            duckdns_new_status['status'] = 'Configuration Missing'
            duckdns_new_status['message'] = 'Domain or Token is missing.'
    else:
        duckdns_new_status = {}

    cf_new_status = status_data.get('cloudflare', {})
    if cf_enabled:
        zone = config.get_value('ddns', 'cloudflare_zone', '')
        record = config.get_value('ddns', 'cloudflare_record', '')
        proxy = config.get_value('ddns', 'cloudflare_proxy', 'false')
        token = config.get_secret('cloudflare_token', '')
        if zone and record and token:
            if ipv4:
                success, msg = update_cloudflare(zone, token, record, ipv4, proxy)
                cf_new_status['status'] = 'Success' if success else 'Error'
                cf_new_status['message'] = msg
                logger.info(f"Cloudflare Update result: {cf_new_status['status']} - {msg}")
                # Alert once per unique error message to avoid alert spam
                if not success and "Connection" not in msg:
                    if status_data.get('cloudflare', {}).get('message') != msg:
                        config.log_alert("Cloudflare DDNS Update Failed", f"Record {record}: {msg}", alert_type="error")
            else:
                cf_new_status['status'] = 'Error'
                cf_new_status['message'] = 'Failed to fetch public IP required for Cloudflare.'
        else:
            cf_new_status['status'] = 'Configuration Missing'
            cf_new_status['message'] = 'Zone, Record, or Token is missing.'
    else:
        cf_new_status = {}

    status_data['duckdns'] = duckdns_new_status
    status_data['cloudflare'] = cf_new_status

    status_file.parent.mkdir(parents=True, exist_ok=True)
    # Write atomically: write to a temp file in the same directory then rename, so
    # concurrent reads by the web API never see a partial/empty file.
    tmp_file = status_file.with_suffix('.tmp')
    tmp_file.write_text(json.dumps(status_data, indent=2))
    tmp_file.chmod(0o644)
    os.replace(tmp_file, status_file)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logger.error(f"Unexpected error in DDNS Update script: {e}")
        sys.exit(1)
