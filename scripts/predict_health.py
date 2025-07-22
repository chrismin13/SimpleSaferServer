#!/usr/bin/env python3

import json
import sys
import os
import xgboost as xgb
import numpy as np
import joblib

# Paths for the XGBoost model and threshold (same as main app)
MODEL_PATH = "/usr/local/bin/harddrive_model/xgb_model.json"
THRESHOLD_PATH = "/usr/local/bin/harddrive_model/optimal_threshold_xgb.pkl"

# SMART attributes used for telemetry/model with their default values
SMART_FIELDS = {
    "smart_1_raw": 0.0,
    "smart_3_raw": 0.0,
    "smart_4_raw": 0.0,
    "smart_5_raw": 0.0,
    "smart_7_raw": 0.0,
    "smart_10_raw": 0.0,
    "smart_192_raw": 0.0,
    "smart_193_raw": 0.0,
    "smart_194_raw": 25.0,
    "smart_197_raw": 0.0,
    "smart_198_raw": 0.0
}

def predict_health(smart_attrs):
    """Make a health prediction based on SMART attributes"""
    try:
        # Load model and threshold
        if not os.path.exists(MODEL_PATH):
            raise Exception(f"Model file not found: {MODEL_PATH}")
        if not os.path.exists(THRESHOLD_PATH):
            raise Exception(f"Threshold file not found: {THRESHOLD_PATH}")
        
        model = xgb.XGBClassifier()
        model.load_model(MODEL_PATH)
        optimal_threshold = joblib.load(THRESHOLD_PATH)
        
        # Initialize dictionary with default values for all required SMART fields
        attrs = {field: info for field, info in SMART_FIELDS.items()}
        
        # Update with actual values from smartctl output
        for attr_id, value in smart_attrs.items():
            field_name = f"smart_{attr_id}_raw"
            if field_name in SMART_FIELDS:
                try:
                    # Temperature is a special case, it is a 16 bit value, but we only want the lowest byte
                    # Extract the lowest byte for smart_194_raw (Temperature)
                    if field_name == "smart_194_raw":
                        attrs[field_name] = float(int(value) & 0xFF)
                    else:
                        attrs[field_name] = float(value)
                except (ValueError, TypeError):
                    print(f"Warning: Could not parse value for {field_name}", file=sys.stderr)
                    continue
        
        # Create feature vector in the correct order
        features = [attrs.get(field, 0.0) for field in SMART_FIELDS.keys()]
        
        # Make prediction
        X = np.array([features])
        prob = float(model.predict_proba(X)[:, 1])
        prediction = int(prob >= optimal_threshold)
        
        return {
            'prediction': prediction,
            'probability': prob
        }
    except Exception as e:
        print(f"Error making prediction: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    try:
        # Read input JSON
        input_data = json.loads(sys.argv[1])
        smart_attrs = input_data.get('smart_attrs', {})
        
        # Make prediction
        result = predict_health(smart_attrs)
        
        # Output result as JSON
        print(json.dumps(result))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1) 