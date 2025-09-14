import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader
from sklearn.model_selection import ParameterGrid, train_test_split
import wandb
from tqdm import tqdm
import json
import time
from pathlib import Path
import pandas as pd
from PIL import Image
import numpy as np
import albumentations as A
from albumentations.pytorch import ToTensorV2
import os
import cv2
import glob

# Set your W&B API key directly
os.environ["WANDB_API_KEY"] = "170694f36aeba75ee06ea0efea1e2d12a584d276"  # Replace with your actual key
# Optional: Set other W&B environment variables
os.environ["WANDB_MODE"] = "online"  # or "offline" if you want to run without internet
#os.environ["WANDB_MODE"] = "disabled"
wandb.init(project="Projekt Projektor")
print("W&B setup successful!")
wandb.finish()

def load_all_labels_json(root_dir):
    """
    Load labels from JSON files and find corresponding image files
    """
    all_labels = []
    
    for labels_path in glob.glob(f"{root_dir}/**/labels.json", recursive=True):
        with open(labels_path, "r") as f:
            data = json.load(f)
            set_name = Path(labels_path).parent.name
            images_dir = Path(labels_path).parent / "images"
            
            print(f"Processing set: {set_name}")
            print(f"Looking for images in: {images_dir}")
            
            # Extract cards from the JSON structure
            if "cards" in data and isinstance(data["cards"], list):
                cards = data["cards"]
                print(f"Found {len(cards)} cards in labels.json")
                
                for card in cards:
                    if isinstance(card, dict) and "filename" in card and "name" in card:
                        filename = card["filename"]
                        card_name = card["name"]
                        image_path = images_dir / filename
                        
                        # Check if image file exists
                        if image_path.exists():
                            entry = {
                                "name": card_name,
                                "filename": filename,
                                "set": set_name,
                                "unique_id": f"{set_name}_{card_name}",
                                "image_path": str(image_path)
                            }
                            all_labels.append(entry)
                            print(f"Added: {entry['unique_id']}")
                        else:
                            print(f"Warning: Image not found: {image_path}")
            else:
                print(f"Warning: No 'cards' array found in {labels_path}")
    
    df = pd.DataFrame(all_labels)
    print(f"Total entries created: {len(df)}")
    
    if len(df) == 0:
        print("ERROR: No valid image files found!")
        print("Please check your directory structure and image files.")
        return df
    
    return df

def create_source_aware_splits(df, source_col='unique_id', train_size=0.7, val_size=0.2, test_size=0.1):
    """
    Split data ensuring no source image appears in multiple splits
    """
    if len(df) == 0:
        print("ERROR: Empty dataframe provided to create_source_aware_splits")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
    # Get unique source images
    unique_sources = df[source_col].unique()
    
    print(f"Total unique sources: {len(unique_sources)}")
    
    if len(unique_sources) < 3:
        print("WARNING: Very few unique sources. Consider collecting more data.")
        # For very small datasets, just do train/val split
        if len(unique_sources) == 1:
            print("Only 1 unique source - using all data for training")
            return df, pd.DataFrame(), pd.DataFrame()
        elif len(unique_sources) == 2:
            print("Only 2 unique sources - splitting into train/val only")
            train_sources = [unique_sources[0]]
            val_sources = [unique_sources[1]]
            test_sources = []
        else:
            # Normal split for 3+ sources
            temp_size = val_size + test_size
            train_sources, temp_sources = train_test_split(
                unique_sources, test_size=temp_size, random_state=42
            )
            val_ratio = val_size / temp_size
            val_sources, test_sources = train_test_split(
                temp_sources, test_size=(1-val_ratio), random_state=42
            )
    else:
        # Normal split for sufficient data
        temp_size = val_size + test_size
        train_sources, temp_sources = train_test_split(
            unique_sources, test_size=temp_size, random_state=42
        )
        val_ratio = val_size / temp_size
        val_sources, test_sources = train_test_split(
            temp_sources, test_size=(1-val_ratio), random_state=42
        )
    
    # Create splits based on source images
    train_df = df[df[source_col].isin(train_sources)]
    val_df = df[df[source_col].isin(val_sources)]
    test_df = df[df[source_col].isin(test_sources)] if len(test_sources) > 0 else pd.DataFrame()
    
    print(f"Training sources: {len(train_sources)}")
    print(f"Validation sources: {len(val_sources)}")
    if len(test_sources) > 0:
        print(f"Test sources: {len(test_sources)}")
    
    return train_df, val_df, test_df

# --- Augmented Dataset ---
class AugmentedMTGCardDataset(torch.utils.data.Dataset):
    def __init__(self, dataframe, class_to_idx, transform=None, augmentations_per_sample=50):
        """
        Dataset that creates multiple augmented versions of each original image
        """
        self.original_df = dataframe.reset_index(drop=True)
        self.transform = transform
        self.class_to_idx = class_to_idx
        self.augmentations_per_sample = augmentations_per_sample
        
        # Create expanded dataset indices
        self.expanded_indices = []
        for idx in range(len(self.original_df)):
            for aug_idx in range(augmentations_per_sample):
                self.expanded_indices.append((idx, aug_idx))
    
    def __len__(self):
        return len(self.expanded_indices)
    
    def __getitem__(self, idx):
        original_idx, aug_idx = self.expanded_indices[idx]
        row = self.original_df.iloc[original_idx]
        
        if not os.path.exists(row['image_path']):
            raise FileNotFoundError(f"Image not found: {row['image_path']}")
        
        # Load original image
        image = Image.open(row['image_path']).convert('RGB')
        image = np.array(image)
        
        # Apply augmentations (different each time due to randomness)
        if self.transform:
            image = self.transform(image=image)['image']
        
        label = self.class_to_idx[row['unique_id']]
        return image, label

# --- Original Dataset (for validation) ---
class MTGCardDataset(torch.utils.data.Dataset):
    def __init__(self, dataframe, class_to_idx, transform=None):
        self.df = dataframe.reset_index(drop=True)
        self.transform = transform
        self.class_to_idx = class_to_idx

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        row = self.df.iloc[idx]
        if not os.path.exists(row['image_path']):
            raise FileNotFoundError(f"Image not found: {row['image_path']}")
        
        image = Image.open(row['image_path']).convert('RGB')
        label = self.class_to_idx[row['unique_id']]
        image = np.array(image)
        if self.transform:
            image = self.transform(image=image)['image']
        return image, label

IMG_SIZE = 224

# Fixed augmentation pipeline - ensures consistent output size
strong_card_aug = A.Compose([
    # First, ensure we have a consistent size
    A.Resize(height=IMG_SIZE, width=IMG_SIZE, p=1.0),
    # Then apply augmentations
    A.OneOf([
        A.RandomResizedCrop(size=(IMG_SIZE, IMG_SIZE), scale=(0.35, 1.0), ratio=(0.75, 1.3)),
        A.Affine(scale=(0.8, 1.2), rotate=(-35, 35), shear=(-12, 12), p=1.0)
    ], p=0.8),
    A.Perspective(scale=(0.04, 0.12), keep_size=True, p=0.4),
    A.OneOf([
        A.GaussianBlur(blur_limit=5),
        A.MotionBlur(blur_limit=7),
        A.MedianBlur(blur_limit=5)
    ], p=0.5),
    A.ColorJitter(brightness=0.5, contrast=0.5, saturation=0.5, hue=0.1, p=0.7),
    A.ISONoise(color_shift=(0.01, 0.15), intensity=(0.1, 0.5), p=0.4),
    A.RandomGamma(gamma_limit=(70, 130), p=0.3),
    A.OneOf([
        A.CoarseDropout(
            num_holes_range=(1, 4),
            hole_height_range=(0.1, 0.25),
            hole_width_range=(0.1, 0.25),
            fill=0, p=0.7
        ),
        A.CoarseDropout(
            num_holes_range=(1, 4),
            hole_height_range=(0.2, 0.35),
            hole_width_range=(0.2, 0.35),
            fill=0, p=0.7
        )
    ], p=0.5),
    A.GridDistortion(num_steps=5, distort_limit=0.3, p=0.3),
    A.ToGray(p=0.08),
    # Final resize to ensure consistent output (safety net)
    A.Resize(height=IMG_SIZE, width=IMG_SIZE, p=1.0),
    A.Normalize(),
    ToTensorV2()
])

val_aug = A.Compose([
    A.Resize(height=IMG_SIZE, width=IMG_SIZE),
    A.Normalize(),
    ToTensorV2()
])

# --- Model ---
class MagicCardNet(nn.Module):
    def __init__(self, num_classes, channels=[64, 128, 256, 512], pool_size=(4, 4), dropout=0.5):
        super().__init__()
        self.features = nn.ModuleList()
        in_ch = 3
        for out_ch in channels:
            block = nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 3, padding=1),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True),
                nn.Conv2d(out_ch, out_ch, 3, padding=1),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True),
                nn.MaxPool2d(2, 2)
            )
            self.features.append(block)
            in_ch = out_ch
        self.adaptive_pool = nn.AdaptiveAvgPool2d(pool_size)
        pool_features = channels[-1] * pool_size[0] * pool_size[1]
        self.classifier = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(pool_features, pool_features // 2),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(pool_features // 2, pool_features // 4),
            nn.ReLU(inplace=True),
            nn.Linear(pool_features // 4, num_classes)
        )
    
    def forward(self, x):
        for block in self.features:
            x = block(x)
        x = self.adaptive_pool(x)
        x = x.view(x.size(0), -1)
        return self.classifier(x)

def train_epoch(model, loader, optimizer, criterion, device):
    model.train()
    total_loss = 0
    correct = 0
    total = 0
    pbar = tqdm(loader, desc="Training", leave=False)
    for batch_idx, (data, target) in enumerate(pbar):
        data, target = data.to(device), target.to(device)
        if batch_idx % 3 == 0:
            size = torch.randint(160, 320, (1,)).item()
            data = F.interpolate(data, size=(size, size), mode='bilinear', align_corners=False)
        optimizer.zero_grad()
        output = model(data)
        loss = criterion(output, target)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        pred = output.argmax(dim=1)
        correct += pred.eq(target).sum().item()
        total += target.size(0)
        pbar.set_postfix({'Loss': f'{loss.item():.4f}', 'Acc': f'{100.*correct/total:.2f}%'})
    return total_loss / len(loader), 100. * correct / total

def validate(model, loader, criterion, device):
    model.eval()
    total_loss = 0
    correct = 0
    total = 0
    with torch.no_grad():
        pbar = tqdm(loader, desc="Validation", leave=False)
        for data, target in pbar:
            data, target = data.to(device), target.to(device)
            output = model(data)
            loss = criterion(output, target)
            total_loss += loss.item()
            pred = output.argmax(dim=1)
            correct += pred.eq(target).sum().item()
            total += target.size(0)
            pbar.set_postfix({'Loss': f'{loss.item():.4f}', 'Acc': f'{100.*correct/total:.2f}%'})
    return total_loss / len(loader), 100. * correct / total

def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)

def save_model(model, config, metrics, save_dir, is_best=False):
    save_dir = Path(save_dir)
    save_dir.mkdir(exist_ok=True)
    channels_str = "_".join(map(str, config['channels']))
    pool_str = f"{config['pool_size'][0]}x{config['pool_size'][1]}"
    filename = f"model_ch{channels_str}_pool{pool_str}_acc{metrics['val_acc']:.2f}"
    if is_best:
        filename += "_BEST"
    local_path = save_dir / f"{filename}.pth"
    torch.save({
        'model_state_dict': model.state_dict(),
        'config': config,
        'metrics': metrics,
        'model_params': count_parameters(model)
    }, local_path)
    if wandb.run is not None:
        wandb.save(str(local_path))
        if is_best:
            wandb.run.summary["best_model_path"] = str(local_path)
    return local_path

def grid_search_training(train_df, val_df, class_to_idx, param_grid, num_epochs=20, batch_size=32, 
                        save_dir="./models", project_name="magic-card-grid-search", augmentations_per_sample=50):
    
    if len(train_df) == 0 or len(val_df) == 0:
        print("ERROR: Empty training or validation set. Cannot proceed with training.")
        return [], None
    
    save_dir = Path(save_dir)
    save_dir.mkdir(exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    
    print(f"Training sources: {train_df['unique_id'].nunique()}")
    print(f"Validation sources: {val_df['unique_id'].nunique()}")
    print(f"With {augmentations_per_sample}x augmentation: {len(train_df) * augmentations_per_sample} training samples")
    print(f"Number of classes: {len(class_to_idx)}")
    
    grid = list(ParameterGrid(param_grid))
    results = []
    best_val_acc = 0
    best_model_path = None
    print(f"Starting grid search with {len(grid)} configurations...")
    
    for config_idx, config in enumerate(grid):
        print(f"\n{'='*60}")
        print(f"Configuration {config_idx + 1}/{len(grid)}")
        print(f"Config: {config}")
        print(f"{'='*60}")
        
        run = wandb.init(
            project=project_name,
            config=config,
            name=f"config_{config_idx+1}",
            reinit=True
        )
        
        try:
            # Use augmented dataset for training
            train_dataset = AugmentedMTGCardDataset(
                train_df, class_to_idx, transform=strong_card_aug, 
                augmentations_per_sample=augmentations_per_sample
            )
            # Use original dataset for validation
            val_dataset = MTGCardDataset(val_df, class_to_idx, transform=val_aug)
            
            train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0)
            val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=0)
            
            model = MagicCardNet(
                num_classes=len(class_to_idx),
                channels=config['channels'],
                pool_size=config['pool_size'],
                dropout=config['dropout']
            ).to(device)
            
            param_count = count_parameters(model)
            print(f"Model parameters: {param_count:,}")
            wandb.log({"model_parameters": param_count})
            
            optimizer = optim.Adam(model.parameters(), lr=config['lr'])
            criterion = nn.CrossEntropyLoss()
            scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=3, factor=0.5)
            
            best_val_acc_this_config = 0
            best_model_state = None
            
            epoch_pbar = tqdm(range(num_epochs), desc=f"Config {config_idx+1}")
            for epoch in epoch_pbar:
                start_time = time.time()
                train_loss, train_acc = train_epoch(model, train_loader, optimizer, criterion, device)
                val_loss, val_acc = validate(model, val_loader, criterion, device)
                scheduler.step(val_loss)
                
                if val_acc > best_val_acc_this_config:
                    best_val_acc_this_config = val_acc
                    best_model_state = model.state_dict().copy()
                
                epoch_time = time.time() - start_time
                metrics = {
                    'epoch': epoch,
                    'train_loss': train_loss,
                    'train_acc': train_acc,
                    'val_loss': val_loss,
                    'val_acc': val_acc,
                    'lr': optimizer.param_groups[0]['lr'],
                    'epoch_time': epoch_time
                }
                wandb.log(metrics)
                
                epoch_pbar.set_postfix({
                    'Train Acc': f'{train_acc:.2f}%',
                    'Val Acc': f'{val_acc:.2f}%',
                    'Best': f'{best_val_acc_this_config:.2f}%'
                })
            
            model.load_state_dict(best_model_state)
            final_metrics = {
                'val_acc': best_val_acc_this_config,
                'val_loss': val_loss,
                'train_acc': train_acc,
                'model_params': param_count
            }
            
            is_best = best_val_acc_this_config > best_val_acc
            model_path = save_model(model, config, final_metrics, save_dir, is_best)
            
            if is_best:
                best_val_acc = best_val_acc_this_config
                best_model_path = model_path
                print(f"🎉 New best model! Validation accuracy: {best_val_acc:.2f}%")
            
            result = {
                'config': config,
                'val_acc': best_val_acc_this_config,
                'val_loss': val_loss,
                'train_acc': train_acc,
                'model_params': param_count,
                'model_path': str(model_path)
            }
            results.append(result)
            
            wandb.run.summary.update({
                'final_val_acc': best_val_acc_this_config,
                'final_train_acc': train_acc,
                'is_best': is_best
            })
            
        except Exception as e:
            print(f"Error in configuration {config_idx + 1}: {e}")
            results.append({
                'config': config,
                'error': str(e),
                'val_acc': 0,
                'model_params': 0
            })
        
        finally:
            wandb.finish()
    
    results_path = save_dir / "grid_search_results.json"
    with open(results_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*60}")
    print("GRID SEARCH COMPLETE")
    print(f"{'='*60}")
    print(f"Best validation accuracy: {best_val_acc:.2f}%")
    print(f"Best model saved at: {best_model_path}")
    print(f"Results saved at: {results_path}")
    
    valid_results = [r for r in results if 'error' not in r]
    valid_results.sort(key=lambda x: x['val_acc'], reverse=True)
    
    print(f"\nTop 3 configurations:")
    for i, result in enumerate(valid_results[:3]):
        print(f"{i+1}. Val Acc: {result['val_acc']:.2f}% | Params: {result['model_params']:,} | Config: {result['config']}")
    
    return results, best_model_path

# --- Main ---
if __name__ == "__main__":
    # Load original data
    data_source = load_all_labels_json("mtg_datasets")
    
    if len(data_source) == 0:
        print("No data found. Exiting.")
        exit(1)
    
    print("Creating source-aware data splits...")
    train_df, val_df, test_df = create_source_aware_splits(
        data_source, 
        source_col='unique_id',
        train_size=0.7, 
        val_size=0.2, 
        test_size=0.1
    )
    
    if len(train_df) == 0 or len(val_df) == 0:
        print("ERROR: Cannot create proper train/val splits. Need more data.")
        exit(1)
    
    # Build class mapping from unique_id
    all_ids = pd.concat([train_df, val_df])['unique_id'].unique()
    class_to_idx = {uid: i for i, uid in enumerate(sorted(all_ids))}
    
    print(f"Training sources: {train_df['unique_id'].nunique()}")
    print(f"Validation sources: {val_df['unique_id'].nunique()}")
    print(f"Total classes: {len(class_to_idx)}")
    
    # ===== CONFIGURE YOUR GRID SEARCH PARAMETERS =====
    param_grid = {
        'channels': [[64, 128, 256], [64, 128, 256, 512]],
        'pool_size': [(2, 2), (4, 4)],
        'dropout': [0.3, 0.5],
        'lr': [0.001, 0.0005]
    }
    
    # ===== CONFIGURE TRAINING PARAMETERS =====
    NUM_EPOCHS = 20
    BATCH_SIZE = 16
    PROJECT_NAME = "magic-card-grid-search"
    AUGMENTATIONS_PER_SAMPLE = 50  # Each original image creates 50 augmented versions
    
    # Start training
    results, best_model = grid_search_training(
        train_df=train_df,
        val_df=val_df,
        class_to_idx=class_to_idx,
        param_grid=param_grid,
        num_epochs=NUM_EPOCHS,
        batch_size=BATCH_SIZE,
        save_dir="./magic_card_models",
        project_name=PROJECT_NAME,
        augmentations_per_sample=AUGMENTATIONS_PER_SAMPLE
    )