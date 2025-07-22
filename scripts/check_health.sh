#!/bin/bash

CONFIG_FILE="/etc/SimpleSaferServer/config.conf"

get_config_value() {
    section=$1
    key=$2
    awk -F '=' -v section="[$section]" -v key="$key" '
        $0 == section { in_section=1; next }
        /^\[.*\]/     { in_section=0 }
        in_section && $1 ~ "^[ \t]*"key"[ \t]*$" { gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit }
    ' "$CONFIG_FILE" | tr -d '"'
}

MOUNT_POINT=$(get_config_value backup mount_point)
UUID=$(get_config_value backup uuid)
EMAIL_ADDRESS=$(get_config_value backup email_address)
SERVER_NAME=$(get_config_value system server_name)

# Function to send email and log alert
function send_email {
    echo "$1 - $2" # Log the status
    echo -e "Subject: $1 - $SERVER_NAME\n$2" | msmtp $EMAIL_ADDRESS
    
    # Log alert using the standalone script
    python3 /usr/local/bin/log_alert.py "$1" "$2" "error" "check_health"
}

echo "Starting drive health check using XGBoost model..."

# Check if drive is mounted
if ! grep -qs "$MOUNT_POINT" /proc/mounts; then
    send_email "Drive Health Check Failed - Drive Not Mounted" "The backup drive is not mounted at $MOUNT_POINT"
    exit 1
fi

# Get the device path from UUID
if [ -z "$UUID" ]; then
    send_email "Drive Health Check Failed - No UUID Configured" "Cannot determine drive device without UUID"
    exit 1
fi

partition_device=$(blkid -t UUID=$UUID -o device)
if [ -z "$partition_device" ]; then
    send_email "Drive Health Check Failed - Drive Not Found" "Cannot find drive with UUID $UUID"
    exit 1
fi

# Get the parent device (e.g., /dev/sda from /dev/sda1)
parent_device=$(lsblk -no PKNAME "$partition_device")
if [ -z "$parent_device" ]; then
    # Fallback: strip trailing digits
    parent_device=$(echo "$partition_device" | sed 's/[0-9]*$//')
fi

# Ensure parent_device is a full device path
if [[ "$parent_device" != /dev/* ]]; then
    parent_device="/dev/$parent_device"
fi

if [ -z "$parent_device" ]; then
    send_email "Drive Health Check Failed - Cannot Determine Parent Device" "Cannot determine parent device for $partition_device"
    exit 1
fi

echo "Checking health of device: $parent_device"

# Get SMART attributes using smartctl
echo "Getting SMART attributes..."
smart_attrs=$(smartctl -A "$parent_device" | grep -E "^(  [0-9]+| [0-9]+)" | grep -E "^(  5|  9| 12|177|194|197|198|199|200|201|202|203|204|205|206|207|208|209|211|212|220|221|222|223|224|225|226|227|228|230|231|232|233|234|235|240|241|242|250|251|252|254|255)" | awk '{print $2 " " $10}')

if [ -z "$smart_attrs" ]; then
    send_email "Drive Health Check Failed - No SMART Data" "Could not retrieve SMART data from $parent_device"
    exit 1
fi

# Convert to JSON format for Python script
json_data="{\"smart_attrs\":{"
while read -r line; do
    if [ ! -z "$line" ]; then
        attr_id=$(echo $line | awk '{print $1}')
        value=$(echo $line | awk '{print $2}')
        json_data="${json_data}\"$attr_id\":$value,"
    fi
done <<< "$smart_attrs"
json_data="${json_data%,}}}"

echo "SMART data collected, making health prediction..."

# Call Python script to make prediction
prediction=$(python3 /usr/local/bin/predict_health.py "$json_data")

if [ $? -ne 0 ]; then
    send_email "Drive Health Check Failed - Prediction Error" "Error running health prediction script"
    exit 1
fi

# Parse prediction result
probability=$(echo $prediction | jq -r '.probability')
prediction_result=$(echo $prediction | jq -r '.prediction')

if [ "$prediction_result" = "1" ]; then
    send_email "Drive Health Warning" "Drive health check failed with probability $probability. Drive: $parent_device"
    exit 1
else
    echo "Drive health check passed with probability $probability"
    exit 0
fi 