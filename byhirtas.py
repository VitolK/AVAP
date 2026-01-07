#!/usr/bin/env python3
"""
Custom Image Viewer - Collage Mode
Displays images from a directory in a collage format, adding new images periodically
"""

import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from PIL import Image, ImageTk
import sys
import os
import argparse
import random
import time
from datetime import datetime


class CollageViewer:
    def __init__(self, root, directory, canvas_width=1920, canvas_height=1080, interval=5):
        self.root = root
        self.directory = Path(directory)
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.interval = interval  # seconds between new images
        
        # Supported image extensions
        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', 
                                 '.webp', '.tiff', '.tif', '.ico', '.svg'}
        
        # Store displayed images: list of (PhotoImage, x, y, image_path, img_object) tuples
        # img_object is the PIL Image object for saving
        self.displayed_images = []
        # Track which images we've already used
        self.used_images = set()
        # Store the background collage image (if loaded)
        self.background_collage = None
        self.background_collage_photo = None
        # Track total images added (including those in background collage)
        self.total_images_count = 0
        
        # Setup output directory for saved collages
        self.output_dir = Path("koliazai")
        self.output_dir.mkdir(exist_ok=True)
        
        # Set window size to canvas size
        self.root.title("")
        self.root.geometry(f"{canvas_width}x{canvas_height}")
        
        # Create UI
        self.create_widgets()
        
        # Bind keyboard shortcuts
        self.root.bind('<Escape>', lambda e: self.root.quit())
        
        # Load initial image list
        self.refresh_image_list()
        
        # Start the collage timer
        self.add_next_image()
    
    def create_widgets(self):
        # Canvas for displaying images (no scrollbars needed, fixed size)
        self.canvas = tk.Canvas(
            self.root, 
            bg="white", 
            highlightthickness=0,
            width=self.canvas_width,
            height=self.canvas_height
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Configure canvas scroll region
        self.canvas.configure(scrollregion=(0, 0, self.canvas_width, self.canvas_height))
    
    def refresh_image_list(self):
        """Refresh the list of available images from directory."""
        if not self.directory.exists() or not self.directory.is_dir():
            return []
        
        image_list = [
            p for p in self.directory.iterdir() 
            if p.is_file() and p.suffix.lower() in self.image_extensions
        ]
        return image_list
    
    def get_unused_image(self):
        """Get a random image that hasn't been used yet."""
        available_images = self.refresh_image_list()
        
        # Filter out already used images
        unused = [img for img in available_images if img not in self.used_images]
        
        # If all images have been used, reset the used set and use all images
        if not unused and available_images:
            self.used_images.clear()
            unused = available_images
        
        if not unused:
            return None
        
        selected = random.choice(unused)
        self.used_images.add(selected)
        return selected
    
    def load_and_place_image(self, image_path):
        """Load an image and place it at a random position."""
        try:
            # Open image
            img = Image.open(image_path)
            img_width, img_height = img.size
            original_img = img.copy()  # Keep original for saving
            
            # Convert to PhotoImage (keep original size or scale if too large)
            # Optionally scale down if image is extremely large
            max_size = max(self.canvas_width, self.canvas_height) * 2
            if img_width > max_size or img_height > max_size:
                scale = max_size / max(img_width, img_height)
                new_width = int(img_width * scale)
                new_height = int(img_height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                img_width, img_height = new_width, new_height
            
            photo = ImageTk.PhotoImage(img)
            
            # Random position (center is 0,0, so we place relative to center)
            # Position is the top-left corner of the image
            center_x = self.canvas_width // 2
            center_y = self.canvas_height // 2
            
            # Random offset from center (can go outside canvas)
            offset_x = random.randint(-self.canvas_width, self.canvas_width)
            offset_y = random.randint(-self.canvas_height, self.canvas_height)
            
            # Calculate position (anchor is center for create_image)
            x = center_x + offset_x
            y = center_y + offset_y
            
            # Store the image and its position (including original PIL image for saving)
            self.displayed_images.append((photo, x, y, image_path, img, img_width, img_height))
            
            # Draw the image on canvas (on top of background if exists)
            self.canvas.create_image(x, y, image=photo, anchor=tk.CENTER)
            
            # Keep reference to prevent garbage collection
            # (PhotoImage objects need to be kept alive)
            
        except Exception as e:
            print(f"Error loading image {image_path}: {e}")
    
    def save_collage(self):
        """Save the current collage as an image file and replace canvas with it."""
        try:
            # Delete all previous collage files
            if self.output_dir.exists():
                for old_file in self.output_dir.glob("collage_*.png"):
                    try:
                        old_file.unlink()
                        print(f"Deleted old collage: {old_file.name}")
                    except Exception as e:
                        print(f"Error deleting old collage {old_file.name}: {e}")
            
            # Create a new image with the canvas dimensions
            collage = Image.new('RGB', (self.canvas_width, self.canvas_height), 'white')
            
            # If there's a background collage, paste it first
            if self.background_collage:
                collage.paste(self.background_collage, (0, 0))
            
            # Paste each individual image at its position
            for photo, x, y, image_path, img, img_width, img_height in self.displayed_images:
                # Calculate top-left corner (since anchor is center)
                paste_x = x - img_width // 2
                paste_y = y - img_height // 2
                
                if img.mode == 'RGBA':
                    # Create a white background for transparent images
                    bg = Image.new('RGB', img.size, 'white')
                    bg.paste(img, mask=img.split()[3] if len(img.split()) == 4 else None)
                    img_to_paste = bg
                elif img.mode != 'RGB':
                    img_to_paste = img.convert('RGB')
                else:
                    img_to_paste = img
                
                collage.paste(img_to_paste, (paste_x, paste_y))
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"collage_{timestamp}_{self.total_images_count}images.png"
            output_path = self.output_dir / filename
            
            collage.save(output_path, 'PNG')
            print(f"Saved collage: {output_path} ({self.total_images_count} images)")
            
            # sneaky shit
            self.load_collage_background(output_path)
            
            return output_path
            
        except Exception as e:
            print(f"Error saving collage: {e}")
            return None
    
    def load_collage_background(self, collage_path):
        """Load a saved collage as the background, replacing current canvas content."""
        try:
            # Load the saved collage
            collage_img = Image.open(collage_path)
            
            # Convert to PhotoImage
            self.background_collage_photo = ImageTk.PhotoImage(collage_img)
            self.background_collage = collage_img.copy()
            
            # Clear the canvas
            self.canvas.delete("all")
            
            # Draw the collage as background (centered)
            center_x = self.canvas_width // 2
            center_y = self.canvas_height // 2
            self.canvas.create_image(
                center_x, 
                center_y, 
                image=self.background_collage_photo, 
                anchor=tk.CENTER
            )
            
            # Clear the displayed_images list (they're now in the background collage)
            # Keep the PhotoImage references alive by storing them
            self.displayed_images = []
            
            print(f"Loaded collage background: {collage_path.name}")
            
        except Exception as e:
            print(f"Error loading collage background: {e}")
    
    def add_next_image(self):
        """Add the next image to the collage."""
        image_path = self.get_unused_image()
        
        if image_path:
            self.load_and_place_image(image_path)
            # Update total count
            self.total_images_count += 1
            
            # Update window title with count
            #self.root.title(f"Užmojis - {self.total_images_count} nuotraukų")
            
            # Save collage every 30 images (based on total count)
            if self.total_images_count % 30 == 0:
                self.save_collage()
        
        # Schedule next image addition
        self.root.after(int(self.interval * 1000), self.add_next_image)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Collage Image Viewer - Displays images in a collage format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -d downloaded_images
  %(prog)s -d /path/to/images -w 1920 -h 1080 -i 3
  %(prog)s --directory images --width 2560 --height 1440 --interval 10
        """
    )
    
    parser.add_argument(
        '-d', '--directory',
        type=str,
        default='downloaded_images',
        help='Directory containing images (default: downloaded_images)'
    )
    
    parser.add_argument(
        '-w', '--width',
        type=int,
        default=1920,
        help='Canvas width in pixels (default: 1920)'
    )
    
    parser.add_argument(
        '--height',
        type=int,
        default=1080,
        help='Canvas height in pixels (default: 1080)'
    )
    
    parser.add_argument(
        '-i', '--interval',
        type=float,
        default=5.0,
        help='Interval in seconds between adding new images (default: 5.0)'
    )
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Validate directory
    directory = Path(args.directory)
    if not directory.exists():
        print(f"Error: Directory does not exist: {directory}")
        sys.exit(1)
    
    if not directory.is_dir():
        print(f"Error: Path is not a directory: {directory}")
        sys.exit(1)
    
    # Validate canvas dimensions
    if args.width <= 0 or args.height <= 0:
        print("Error: Canvas width and height must be positive")
        sys.exit(1)
    
    # Validate interval
    if args.interval <= 0:
        print("Error: Interval must be positive")
        sys.exit(1)
    
    root = tk.Tk()
    app = CollageViewer(
        root, 
        directory=args.directory,
        canvas_width=args.width,
        canvas_height=args.height,
        interval=args.interval
    )
    
    root.mainloop()


if __name__ == "__main__":
    main()
