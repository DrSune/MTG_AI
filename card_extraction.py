import requests
import os
import json
from typing import List, Dict, Any
import time

class MTGDatasetBuilder:
    def __init__(self, output_base_dir: str = "mtg_datasets"):
        self.output_base_dir = output_base_dir
        self.base_url = "https://api.scryfall.com"
        self.session = requests.Session()
        
    def create_directories(self, set_code: str):
        """Create directory structure for a set"""
        set_dir = os.path.join(self.output_base_dir, set_code)
        images_dir = os.path.join(set_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        return set_dir, images_dir
    
    def fetch_set_cards(self, set_code: str) -> List[Dict[Any, Any]]:
        """Fetch all cards from a specific set"""
        url = f"{self.base_url}/cards/search"
        params = {
            'q': f'set:{set_code}',
            'order': 'cmc'
        }
        
        all_cards = []
        
        while url:
            print(f"Fetching cards from: {url}")
            response = self.session.get(url, params=params if url == f"{self.base_url}/cards/search" else None)
            
            if response.status_code != 200:
                print(f"Error fetching cards: {response.status_code}")
                break
                
            data = response.json()
            all_cards.extend(data.get('data', []))
            
            # Check for next page
            url = data.get('next_page')
            params = None  # Only use params for first request
            
            # Be nice to Scryfall API
            time.sleep(0.1)
        
        return all_cards
    
    def download_card_image(self, card: Dict[Any, Any], images_dir: str) -> str:
        """Download a single card image"""
        if 'image_uris' not in card:
            return None
            
        image_url = card['image_uris']['normal']
        
        # Create safe filename
        card_name = card['name'].replace('/', '_').replace('\\', '_')
        collector_number = card.get('collector_number', 'unknown')
        filename = f"{collector_number}_{card_name}.jpg"
        filepath = os.path.join(images_dir, filename)
        
        try:
            img_response = self.session.get(image_url)
            if img_response.status_code == 200:
                with open(filepath, 'wb') as f:
                    f.write(img_response.content)
                return filename
            else:
                print(f"Failed to download image for {card['name']}: {img_response.status_code}")
                return None
        except Exception as e:
            print(f"Error downloading {card['name']}: {e}")
            return None
    
    def create_labels_file(self, cards: List[Dict[Any, Any]], set_dir: str, set_code: str):
        """Create comprehensive labels file for training"""
        labels_data = {
            'set_info': {
                'set_code': set_code,
                'set_name': cards[0].get('set_name', '') if cards else '',
                'total_cards': len(cards)
            },
            'cards': []
        }
        
        for card in cards:
            if 'image_uris' not in card:
                continue
                
            card_name = card['name'].replace('/', '_').replace('\\', '_')
            collector_number = card.get('collector_number', 'unknown')
            filename = f"{collector_number}_{card_name}.jpg"
            
            card_info = {
                'filename': filename,
                'name': card['name'],
                'collector_number': card.get('collector_number'),
                'type_line': card.get('type_line', ''),
                'mana_cost': card.get('mana_cost', ''),
                'cmc': card.get('cmc', 0),
                'colors': card.get('colors', []),
                'color_identity': card.get('color_identity', []),
                'rarity': card.get('rarity', ''),
                'oracle_text': card.get('oracle_text', ''),
                'power': card.get('power'),
                'toughness': card.get('toughness'),
                'loyalty': card.get('loyalty'),
                'keywords': card.get('keywords', []),
                'image_url': card['image_uris']['normal'],
                'scryfall_id': card.get('id'),
                'set_code': card.get('set'),
                'set_name': card.get('set_name'),
                # Classification labels for ML
                'is_land': 'Land' in card.get('type_line', ''),
                'is_creature': 'Creature' in card.get('type_line', ''),
                'is_instant': 'Instant' in card.get('type_line', ''),
                'is_sorcery': 'Sorcery' in card.get('type_line', ''),
                'is_artifact': 'Artifact' in card.get('type_line', ''),
                'is_enchantment': 'Enchantment' in card.get('type_line', ''),
                'is_planeswalker': 'Planeswalker' in card.get('type_line', ''),
                'is_basic_land': card.get('type_line', '').startswith('Basic Land'),
            }
            
            labels_data['cards'].append(card_info)
        
        # Save labels file
        labels_file = os.path.join(set_dir, 'labels.json')
        with open(labels_file, 'w', encoding='utf-8') as f:
            json.dump(labels_data, f, indent=2, ensure_ascii=False)
        
        return labels_file
    
    def create_training_splits(self, labels_data: Dict[Any, Any], set_dir: str):
        """Create train/validation/test splits"""
        import random
        
        cards = labels_data['cards']
        random.shuffle(cards)
        
        total = len(cards)
        train_end = int(0.7 * total)
        val_end = int(0.85 * total)
        
        splits = {
            'train': cards[:train_end],
            'validation': cards[train_end:val_end],
            'test': cards[val_end:]
        }
        
        for split_name, split_cards in splits.items():
            split_file = os.path.join(set_dir, f'{split_name}_split.json')
            with open(split_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'split': split_name,
                    'count': len(split_cards),
                    'cards': split_cards
                }, f, indent=2, ensure_ascii=False)
        
        return splits
    
    def build_dataset_for_set(self, set_code: str, download_images: bool = True):
        """Build complete dataset for a single set"""
        print(f"\n=== Building dataset for set: {set_code} ===")
        
        # Create directories
        set_dir, images_dir = self.create_directories(set_code)
        
        # Fetch all cards from the set
        print("Fetching card data...")
        cards = self.fetch_set_cards(set_code)
        print(f"Found {len(cards)} cards in set {set_code}")
        
        if not cards:
            print(f"No cards found for set {set_code}")
            return
        
        # Download images
        if download_images:
            print("Downloading card images...")
            downloaded_count = 0
            for i, card in enumerate(cards):
                if 'image_uris' in card:
                    filename = self.download_card_image(card, images_dir)
                    if filename:
                        downloaded_count += 1
                    
                    # Progress indicator
                    if (i + 1) % 10 == 0:
                        print(f"Downloaded {downloaded_count}/{i+1} images...")
                    
                    # Be nice to Scryfall
                    time.sleep(0.05)
            
            print(f"Downloaded {downloaded_count} images")
        
        # Create labels file
        print("Creating labels file...")
        labels_file = self.create_labels_file(cards, set_dir, set_code)
        
        # Load labels for splits
        with open(labels_file, 'r', encoding='utf-8') as f:
            labels_data = json.load(f)
        
        # Create training splits
        print("Creating train/validation/test splits...")
        splits = self.create_training_splits(labels_data, set_dir)
        
        # Create summary
        summary = {
            'set_code': set_code,
            'set_name': cards[0].get('set_name', ''),
            'total_cards': len(cards),
            'cards_with_images': len([c for c in cards if 'image_uris' in c]),
            'train_count': len(splits['train']),
            'validation_count': len(splits['validation']),
            'test_count': len(splits['test']),
            'card_types': {},
            'rarities': {}
        }
        
        # Count card types and rarities
        for card in cards:
            type_line = card.get('type_line', '')
            rarity = card.get('rarity', 'unknown')
            
            # Count main card types
            for card_type in ['Land', 'Creature', 'Instant', 'Sorcery', 'Artifact', 'Enchantment', 'Planeswalker']:
                if card_type in type_line:
                    summary['card_types'][card_type] = summary['card_types'].get(card_type, 0) + 1
            
            summary['rarities'][rarity] = summary['rarities'].get(rarity, 0) + 1
        
        # Save summary
        summary_file = os.path.join(set_dir, 'dataset_summary.json')
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        print(f"Dataset complete! Files saved in: {set_dir}")
        print(f"Summary: {summary['total_cards']} cards, {summary['cards_with_images']} with images")
        print(f"Card types: {summary['card_types']}")
        
        return set_dir

# Create the dataset builder
builder = MTGDatasetBuilder()

# Define the sets we want to download
target_sets = [
    'm21',  # Core Set 2021
    'm20',  # Core Set 2020
    'dom',  # Dominaria (popular recent set)
]

print("MTG Dataset Builder")
print("==================")
print(f"Target sets: {target_sets}")
print(f"Output directory: {builder.output_base_dir}")

# Build datasets for each set
for set_code in target_sets:
    try:
        builder.build_dataset_for_set(set_code, download_images=True)
    except Exception as e:
        print(f"Error processing set {set_code}: {e}")
        continue

# Create master index
print("\n=== Creating master dataset index ===")
master_index = {
    'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    'sets': [],
    'total_cards': 0,
    'total_images': 0
}

for set_code in target_sets:
    summary_file = os.path.join(builder.output_base_dir, set_code, 'dataset_summary.json')
    if os.path.exists(summary_file):
        with open(summary_file, 'r') as f:
            summary = json.load(f)
            master_index['sets'].append(summary)
            master_index['total_cards'] += summary['total_cards']
            master_index['total_images'] += summary['cards_with_images']

master_index_file = os.path.join(builder.output_base_dir, 'master_index.json')
with open(master_index_file, 'w') as f:
    json.dump(master_index, f, indent=2)

print(f"Master index created: {master_index_file}")
print(f"Total cards across all sets: {master_index['total_cards']}")
print(f"Total images downloaded: {master_index['total_images']}")
print("\nDataset building complete!")