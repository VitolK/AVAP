#!/usr/bin/env python3
"""
Custom Image Viewer - Collage Mode
Displays images from a directory in a collage format, adding new images periodically
"""

import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from PIL import Image, ImageTk
import numpy as np
import sys
import os
import argparse
import random
import time
from datetime import datetime


class CollageViewer:
    def __init__(self, root, directory, canvas_width=1920, canvas_height=1080, interval=5, fullscreen=False,
                 rotate=False, mirror=False, crop=False, effects=None, opacity='1.0', blend=None):
        self.root = root
        self.directory = Path(directory)
        self.interval = interval  # seconds between new images
        self.fullscreen = fullscreen
        self.rotate = rotate
        self.mirror = mirror
        self.crop = crop
        self.effects = effects or []
        # Raw blend string from CLI; parsed into modes list below
        self.blend = blend
        
        # Parse opacity (can be single value or range like "[0.25-0.7]")
        self.opacity_range = self._parse_opacity(opacity)
        # Parse blend modes (can be single value or list like "[exclusion,subtract]")
        self.blend_modes = self._parse_blend_modes(blend)
        
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
        # Live collage used for on-the-fly compositing (shown in Tk)
        self.live_collage = None
        # Track total images added (including those in background collage)
        self.total_images_count = 0
        
        # Setup output directory for saved collages
        self.output_dir = Path("koliazai")
        self.output_dir.mkdir(exist_ok=True)
        
        # Set window size and fullscreen mode
        self.root.title("")
        if fullscreen:
            # Get screen dimensions first
            self.root.update_idletasks()
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            self.canvas_width = screen_width
            self.canvas_height = screen_height
            
            # Set fullscreen - this works on both Linux and Windows
            # On Linux, fullscreen typically removes borders automatically
            # On Windows, we may need overrideredirect, but try fullscreen first
            self.root.attributes('-fullscreen', True)
            self.root.update_idletasks()
            
            # On Windows, also remove decorations for true borderless
            # On Linux, this can cause X11 errors, so we skip it
            import platform
            if platform.system() == 'Windows':
                try:
                    self.root.overrideredirect(True)
                except:
                    pass
        else:
            self.canvas_width = canvas_width
            self.canvas_height = canvas_height
            self.root.geometry(f"{canvas_width}x{canvas_height}")
        
        # Create UI
        self.create_widgets()
        
        # Bind keyboard shortcuts
        self.root.bind('<Escape>', lambda e: self.root.quit())
        
        # Load initial image list
        self.refresh_image_list()
        
        # Start the collage timer
        self.add_next_image()
    
    def _parse_opacity(self, opacity_str):
        """Parse opacity string. Returns (min, max) tuple."""
        opacity_str = opacity_str.strip()
        if opacity_str.startswith('[') and opacity_str.endswith(']'):
            # Range format: [min-max]
            inner = opacity_str[1:-1]
            parts = inner.split('-')
            if len(parts) == 2:
                return (float(parts[0]), float(parts[1]))
        # Single value
        val = float(opacity_str)
        return (val, val)

    def _parse_blend_modes(self, blend_str):
        """Parse blend string into a list of modes."""
        if not blend_str:
            return []
        s = blend_str.strip()
        # Accept formats like "[exclusion,subtract]" or "[ exclusion subtract divide ]"
        if s.startswith('[') and s.endswith(']'):
            inner = s[1:-1]
        else:
            inner = s
        # Normalize separators (spaces and commas)
        tokens = [t.strip() for t in inner.replace(',', ' ').split() if t.strip()]
        # Supported blend modes, including 'normal' (no special math)
        allowed = {'divide', 'subtract', 'exclusion', 'normal'}
        modes = [t for t in tokens if t in allowed]
        # Fallback for simple single mode string
        if not modes and s in allowed:
            return [s]
        return modes
    
    def _get_opacity(self):
        """Get opacity value (random if range was specified)."""
        min_op, max_op = self.opacity_range
        if min_op == max_op:
            return min_op
        return random.uniform(min_op, max_op)
    
    def _apply_blend_mode(self, base_img, blend_img, mode, opacity=1.0):
        """Apply Photoshop-style blend mode between two images with opacity."""
        # Ensure both images are the same size and mode
        if base_img.size != blend_img.size:
            return blend_img
        
        base = np.array(base_img.convert('RGB')).astype(float)
        blend = np.array(blend_img.convert('RGB')).astype(float)
        
        if mode == 'normal':
            # Normal: no special blend math, just use the blend image
            result = blend
        elif mode == 'divide':
            # Divide: (base / blend) * 255, avoiding division by zero
            # Lightens the base where blend is dark
            result = np.clip((base * 255) / (blend + 1), 0, 255)
        
        elif mode == 'subtract':
            # Subtract: base - blend
            result = np.clip(base - blend, 0, 255)
        
        elif mode == 'exclusion':
            # Exclusion: base + blend - 2 * base * blend / 255
            result = np.clip(base + blend - (2 * base * blend / 255), 0, 255)
        
        else:
            result = blend
        
        # Apply opacity: interpolate between base and blended result
        if opacity < 1.0:
            result = base * (1 - opacity) + result * opacity
            result = np.clip(result, 0, 255)
        
        return Image.fromarray(result.astype(np.uint8), 'RGB')
    
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
            # Debug: print(f"Loading: {image_path.name}, effects={self.effects}, blend={self.blend}, opacity_range={self.opacity_range}")
            
            # Apply random crop (before other transformations)
            if self.crop:
                w, h = img.size
                crop_percent = random.uniform(0.1, 1.0)
                new_w = max(int(w * crop_percent), 1)
                new_h = max(int(h * crop_percent), 1)
                x = random.randint(0, w - new_w)
                y = random.randint(0, h - new_h)
                img = img.crop((x, y, x + new_w, y + new_h))
            
            # Apply random rotation at 90 degree intervals
            if self.rotate:
                angle = random.choice([0, 90, 180, 270])
                if angle != 0:
                    img = img.rotate(angle, expand=True)
            
            # Apply random mirror (50% chance)
            if self.mirror:
                if random.random() < 0.5:
                    img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            
            # Apply effects
            for effect in self.effects:
                # Debug: print(f"  Applying effect: {effect}")
                if effect == 'grayscale':
                    img = img.convert('L').convert('RGB')
            
            # Get opacity for this image
            current_opacity = self._get_opacity()
            # Debug: print(f"  Opacity: {current_opacity}, blend modes: {self.blend_modes}")
            
            # Apply opacity to alpha channel (for non-blend-mode transparency)
            if current_opacity < 1.0 and not self.blend_modes:
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                # Modify the alpha channel based on opacity
                r, g, b, a = img.split()
                a = a.point(lambda x: int(x * current_opacity))
                img = Image.merge('RGBA', (r, g, b, a))
            
            img_width, img_height = img.size
            original_img = img.copy()  # Keep transformed version for saving
            
            # Optionally scale down if image is extremely large
            max_size = max(self.canvas_width, self.canvas_height) * 2
            if img_width > max_size or img_height > max_size:
                scale = max_size / max(img_width, img_height)
                new_width = int(img_width * scale)
                new_height = int(img_height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                img_width, img_height = new_width, new_height
                original_img = img.copy()
            
            # Initialize live_collage if needed
            if self.live_collage is None:
                if self.background_collage is not None:
                    self.live_collage = self.background_collage.copy()
                else:
                    self.live_collage = Image.new('RGB', (self.canvas_width, self.canvas_height), 'white')
            
            # Random position (center is 0,0, so we place relative to center)
            center_x = self.canvas_width // 2
            center_y = self.canvas_height // 2
            offset_x = random.randint(-self.canvas_width, self.canvas_width)
            offset_y = random.randint(-self.canvas_height, self.canvas_height)
            x = center_x + offset_x
            y = center_y + offset_y
            paste_x = x - img_width // 2
            paste_y = y - img_height // 2

            # Composite onto live_collage
            if self.blend_modes:
                mode = random.choice(self.blend_modes)
                # Two-layer model: current background vs current image region
                src_x1 = max(0, paste_x)
                src_y1 = max(0, paste_y)
                src_x2 = min(self.canvas_width, paste_x + img_width)
                src_y2 = min(self.canvas_height, paste_y + img_height)

                if src_x2 > src_x1 and src_y2 > src_y1:
                    base_region = self.live_collage.crop((src_x1, src_y1, src_x2, src_y2))

                    img_x1 = src_x1 - paste_x
                    img_y1 = src_y1 - paste_y
                    img_x2 = img_x1 + (src_x2 - src_x1)
                    img_y2 = img_y1 + (src_y2 - src_y1)

                    blend_img = img.convert('RGB') if img.mode != 'RGB' else img
                    blend_region = blend_img.crop((img_x1, img_y1, img_x2, img_y2))

                    blended = self._apply_blend_mode(base_region, blend_region, mode, current_opacity)
                    self.live_collage.paste(blended, (src_x1, src_y1))
            else:
                # Normal compositing with alpha/opacity
                if img.mode == 'RGBA':
                    base_rgba = self.live_collage.convert('RGBA')
                    layer = Image.new('RGBA', base_rgba.size, (0, 0, 0, 0))
                    layer.paste(img, (paste_x, paste_y))
                    self.live_collage = Image.alpha_composite(base_rgba, layer).convert('RGB')
                else:
                    self.live_collage.paste(img, (paste_x, paste_y))

            # Update background_collage and Tk canvas from live_collage
            self.background_collage = self.live_collage.copy()
            self.background_collage_photo = ImageTk.PhotoImage(self.live_collage)
            self.canvas.delete("all")
            self.canvas.create_image(
                self.canvas_width // 2,
                self.canvas_height // 2,
                image=self.background_collage_photo,
                anchor=tk.CENTER,
            )

            # Optionally track metadata (not used for compositing anymore)
            self.displayed_images.append((None, x, y, image_path, original_img, img_width, img_height, current_opacity))
            
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
            
            # Use the current live_collage (what you see in Tk) as the saved collage
            if self.live_collage is not None:
                collage = self.live_collage.copy()
            elif self.background_collage is not None:
                collage = self.background_collage.copy()
            else:
                collage = Image.new('RGB', (self.canvas_width, self.canvas_height), 'white')
            
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
            self.live_collage = collage_img.copy()
            
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
  %(prog)s -d images --fullscreen
  %(prog)s -d images --rotate --mirror --crop
  %(prog)s -d images --effect grayscale --opacity 0.5
  %(prog)s -d images --opacity "[0.25-0.7]" --blend exclusion
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
    
    parser.add_argument(
        '--fullscreen',
        action='store_true',
        help='Run in fullscreen mode (no borders, no title bar, takes over entire screen)'
    )
    
    parser.add_argument(
        '--rotate',
        action='store_true',
        help='Rotate images at random 90 degree intervals (0, 90, 180, 270 degrees)'
    )
    
    parser.add_argument(
        '--mirror',
        action='store_true',
        help='Mirror images horizontally with 50%% chance'
    )
    
    parser.add_argument(
        '--crop',
        action='store_true',
        help='Randomly crop images (between 10%% and 100%% of original size)'
    )
    
    parser.add_argument(
        '--effect',
        type=str,
        action='append',
        choices=['grayscale'],
        help='Apply effect to images (can be specified multiple times). Available: grayscale'
    )
    
    parser.add_argument(
        '--opacity',
        type=str,
        default='1.0',
        help='Set opacity for each image. Single value (0.0-1.0) or range like "[0.25-0.7]" for random'
    )
    
    parser.add_argument(
        '--blend',
        type=str,
        help='Blend mode(s) for compositing images (like Photoshop). Single value (exclusion) or list like "[exclusion,subtract,divide,normal]". "normal" leaves the image unaltered by blend math.'
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
    
    # Validate opacity
    try:
        opacity_str = args.opacity.strip()
        if opacity_str.startswith('[') and opacity_str.endswith(']'):
            inner = opacity_str[1:-1]
            parts = inner.split('-')
            if len(parts) != 2:
                raise ValueError("Range format should be [min-max]")
            min_op, max_op = float(parts[0]), float(parts[1])
            if min_op < 0.0 or max_op > 1.0 or min_op > max_op:
                raise ValueError("Opacity range must be between 0.0 and 1.0")
        else:
            val = float(opacity_str)
            if val < 0.0 or val > 1.0:
                raise ValueError("Opacity must be between 0.0 and 1.0")
    except ValueError as e:
        print(f"Error: Invalid opacity value - {e}")
        sys.exit(1)
    
    root = tk.Tk()
    app = CollageViewer(
        root, 
        directory=args.directory,
        canvas_width=args.width,
        canvas_height=args.height,
        interval=args.interval,
        fullscreen=args.fullscreen,
        rotate=args.rotate,
        mirror=args.mirror,
        crop=args.crop,
        effects=args.effect,
        opacity=args.opacity,
        blend=args.blend
    )
    
    root.mainloop()


if __name__ == "__main__":
    main()
