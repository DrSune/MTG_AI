import json
import csv
import sys
import os

def extract_lei_data(file_path, output_csv, limit=1000):
    """
    Reads a large LEI JSON file line by line (or chunk by chunk if it's a huge array)
    and extracts the first N records into a CSV file.
    """
    count = 0
    # Common LEI fields to extract
    fields = [
        'LEI', 'Entity.LegalName', 'Entity.LegalAddress.City', 
        'Entity.LegalAddress.Country', 'Registration.RegistrationStatus'
    ]
    
    # We'll use a simple streaming approach if possible, but Golden Copy JSON 
    # is usually a massive array of objects.
    # Because it's a structured JSON file [{}, {}, ...], we might need an incremental parser
    # like ijson if it's not line-delimited.
    
    try:
        import ijson
    except ImportError:
        print("ijson not found. Trying manual primitive parsing...")
        # Fallback: simple line reading or small buffer search if it's formatted well.
        # But for 12GB, we really want ijson or similar.
        # Let's check if we can install it or if we can manage with basic file reading.
        pass

    print(f"Opening {file_path} for streaming...")
    
    with open(file_path, 'rb') as f:
        # The JSON structure is {"records": [ {...}, {...} ]}
        # ijson.items(f, 'records.item') yields each object in the records list
        import ijson
        records = ijson.items(f, 'records.item')
        
        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fields)
            writer.writeheader()
            
            for record in records:
                # Map complex JSON to flat CSV structure
                # Note: Many fields like LEI and LegalName are objects with a '$' key
                def get_val(obj):
                    if isinstance(obj, dict):
                        return obj.get('$')
                    return obj

                row = {
                    'LEI': get_val(record.get('LEI')),
                    'Entity.LegalName': get_val(record.get('Entity', {}).get('LegalName')),
                    'Entity.LegalAddress.City': get_val(record.get('Entity', {}).get('LegalAddress', {}).get('City')),
                    'Entity.LegalAddress.Country': get_val(record.get('Entity', {}).get('LegalAddress', {}).get('Country')),
                    'Registration.RegistrationStatus': get_val(record.get('Registration', {}).get('RegistrationStatus'))
                }
                writer.writerow(row)
                count += 1
                if count % 100 == 0:
                    print(f"Processed {count} records...")
                if count >= limit:
                    break
    
    print(f"Successfully extracted {count} records to {output_csv}")

if __name__ == "__main__":
    # Use the workspace path if copied, or direct path
    source = r'C:\Users\FrederikSunesen\Downloads\20260410-0800-gleif-goldencopy-lei2-golden-copy.json\20260410-0800-gleif-goldencopy-lei2-golden-copy.json'
    target = 'lei_extract_1000.csv'
    
    # Try to install ijson if not present
    try:
        import ijson
    except ImportError:
        print("Installing ijson...")
        os.system(f"{sys.executable} -m pip install ijson")
        import ijson

    extract_lei_data(source, target)
