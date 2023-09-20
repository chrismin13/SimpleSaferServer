#!/bin/bash

# Source the config file
source /etc/SimpleSaferServer/config.conf

# Function to send email
function send_email {
    echo "$1 - $2" # Log the status
    echo -e "Subject: $1 - $SERVER_NAME\n\n$2" | msmtp $EMAIL_ADDRESS
}

# Define the directories for the hdsentinel files
PREVIOUS_OUTPUT_FILE="/var/tmp/hdsentinel_previous_output"
COMMAND="/usr/local/bin/hdsentinel-armv8 -solid"

# Check if the previous output file exists, if not, create an empty one
if [ ! -f "$PREVIOUS_OUTPUT_FILE" ]; then
    touch $PREVIOUS_OUTPUT_FILE
fi

# Execute the command and save output to variable
CURRENT_OUTPUT=$($COMMAND)
printf "HDSentinel reported:\n\n$CURRENT_OUTPUT\n\n"

# Parse the output line by line
echo "$CURRENT_OUTPUT" | while read -r line
do
    # Get the drive name, model, and serial number
    DRIVE=$(echo $line | cut -d ' ' -f1)
    MODEL=$(echo $line | cut -d ' ' -f5)
    SERIAL=$(echo $line | cut -d ' ' -f6)
    # Get the temperature
    TEMPERATURE=$(echo $line | cut -d ' ' -f2)
    # Get the health
    HEALTH=$(echo $line | cut -d ' ' -f3)
    # Skip if health or temperature are not available
    if [ "$TEMPERATURE" == "?" ] || [ "$HEALTH" == "?" ]; then
        continue
    fi

    # Search for the previous data for this model and serial number
    PREVIOUS_LINE=$(grep "$MODEL $SERIAL" $PREVIOUS_OUTPUT_FILE)

    # If the drive was not found in the previous output, treat it as a new drive
    if [ "$PREVIOUS_LINE" == "" ]; then
        echo "New drive detected: $MODEL ($SERIAL). Health: $HEALTH%, Temperature: $TEMPERATURE."
    else
        PREVIOUS_HEALTH=$(echo $PREVIOUS_LINE | cut -d ' ' -f3)

        # If the health has changed, send an email
        if [ "$HEALTH" != "$PREVIOUS_HEALTH" ]; then
            send_email "Hard Drive Health Changed" "The health of the drive $MODEL ($SERIAL) has changed. New health is $HEALTH%. The output of the command is: $($COMMAND -dump)"
        fi
    fi

    if [ "$HEALTH" -lt 50 ]; then
        send_email "Hard Drive Health Low" "The health of the drive $MODEL ($SERIAL) is below 50%. Current health is $HEALTH%. The output of the command is: $($COMMAND -dump)"
    fi

    if [ "$TEMPERATURE" -gt 50 ]; then
        send_email "Hard Drive Temperature High" "The temperature of the drive $MODEL ($SERIAL) is above 50C. Current temperature is $TEMPERATURE. The output of the command is: $($COMMAND -dump)"
    fi

    # If everything is fine, log the drive status
    if [ "$HEALTH" -ge 50 ] && [ "$TEMPERATURE" -le 50 ]; then
        echo "Drive $MODEL ($SERIAL) is OK. Health: $HEALTH%. Temperature: $TEMPERATURE."
    fi
done

# Store current output for next run
echo "$CURRENT_OUTPUT" > $PREVIOUS_OUTPUT_FILE