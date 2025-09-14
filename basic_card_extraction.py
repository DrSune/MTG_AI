import requests
import os
print('hello')
basic_lands = ["Plains", "Island", "Swamp", "Mountain", "Forest"]
output_dir = "basic_land_images"
os.makedirs(output_dir, exist_ok=True)

card_data = []

for land in basic_lands:
    url = f"https://api.scryfall.com/cards/named?exact={land}"
    resp = requests.get(url)
    data = resp.json()
    # Get the best available image (PNG, normal size)
    image_url = data['image_uris']['normal']
    # Download the image
    img_data = requests.get(image_url).content
    img_path = os.path.join(output_dir, f"{land}.jpg")
    with open(img_path, 'wb') as f:
        f.write(img_data)
    # Collect card info
    card_info = {
        "name": data['name'],
        "type_line": data['type_line'],
        "oracle_text": data['oracle_text'],
        "image_url": image_url
    }
    card_data.append(card_info)
    print(f"Downloaded {land}: {image_url}")

# Optionally, save card info to a JSON file
import json
with open("basic_lands_info.json", "w") as f:
    json.dump(card_data, f, indent=2)