#!/usr/bin/env python3
"""
Custom Image Viewer - Collage Mode
Displays images from a directory in a collage format, adding new images periodically
"""

import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk
import numpy as np
import sys
import argparse
import random
from datetime import datetime


MIDNIGHT = '#0A0A0A'
INK = '#E8E8E0'
DARK = '#0A0A0A'
PANEL_RIGHT = 240
PANEL_BOTTOM = 100
UI_FONT = ('Courier', 10)
UI_FONT_SM = ('Courier', 9)
BLEND_OPTIONS = ('normal', 'divide', 'subtract', 'exclusion')


class CollageViewer:
    def __init__(self, root, directory, canvas_width=1920, canvas_height=1080, interval=5, fullscreen=False,
                 rotate=False, mirror=False, crop=False, effects=None, opacity='1.0', blend=None,
                 auto_delete=False, save_collage=False, save_collage_interval=50):
        self.root = root
        self.directory = Path(directory)
        self.interval = interval
        self.fullscreen = fullscreen
        self.auto_delete = auto_delete
        self.save_collage_enabled = save_collage
        self.save_collage_interval = save_collage_interval
        self.last_displayed_image_path = None
        self.rotate = rotate
        self.mirror = mirror
        self.crop = crop
        self.effects = list(effects or [])
        self.blend = blend or ''
        self.opacity_str = opacity

        self.opacity_range = self._parse_opacity(opacity)
        self.blend_modes = self._parse_blend_modes(blend)

        self.image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp',
                                 '.webp', '.tiff', '.tif', '.ico', '.svg'}

        self.used_images = set()
        self.background_collage = None
        self.background_collage_photo = None
        self.live_collage = None
        self.total_images_count = 0
        self.paused = False
        self.launched = False
        self.ui_visible = True
        self._after_id = None

        self.output_dir = Path("koliazai")
        self.output_dir.mkdir(exist_ok=True)

        self.canvas_width = canvas_width
        self.canvas_height = canvas_height

        self.root.title("")
        self.root.configure(bg=DARK)
        self.root.update_idletasks()

        if fullscreen:
            self.root.attributes('-fullscreen', True)
            import platform
            if platform.system() == 'Windows':
                try:
                    self.root.overrideredirect(True)
                except Exception:
                    pass
        else:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            win_w = min(canvas_width + PANEL_RIGHT, sw)
            win_h = min(canvas_height + PANEL_BOTTOM, sh)
            self.root.geometry(f"{win_w}x{win_h}")

        self._build_vars()
        self.create_widgets()

        self.root.bind('<Escape>', lambda e: self.root.quit())
        self.root.bind('<Return>', self._on_return)
        self.root.bind_all('<KeyPress-space>', self._on_space)
        self.root.bind_all('<KeyPress-h>', self._on_hide_key)
        self.root.bind_all('<KeyPress-H>', self._on_hide_key)
        self.root.bind_all('<Button-1>', self._on_click_unfocus)
        self.root.focus_set()

    def _build_vars(self):
        self.var_directory = tk.StringVar(value=str(self.directory))
        self.var_interval = tk.StringVar(value=str(self.interval))
        self.var_opacity = tk.StringVar(value=self.opacity_str)
        self.var_width = tk.StringVar(value=str(self.canvas_width))
        self.var_height = tk.StringVar(value=str(self.canvas_height))
        self.var_fullscreen = tk.BooleanVar(value=self.fullscreen)
        self.var_auto_delete = tk.BooleanVar(value=self.auto_delete)
        self.var_save_collage = tk.BooleanVar(value=self.save_collage_enabled)
        self.var_rotate = tk.BooleanVar(value=self.rotate)
        self.var_mirror = tk.BooleanVar(value=self.mirror)
        self.var_crop = tk.BooleanVar(value=self.crop)
        self.var_grayscale = tk.BooleanVar(value='grayscale' in self.effects)
        initial_blends = set(self.blend_modes)
        self.var_blend_modes = {
            mode: tk.BooleanVar(value=(mode in initial_blends))
            for mode in BLEND_OPTIONS
        }

    def _panel_label(self, parent, text, **pack_kwargs):
        lbl = tk.Label(
            parent, text=text, bg=MIDNIGHT, fg=INK,
            font=UI_FONT_SM, anchor='w', padx=0, pady=0,
        )
        lbl.pack(**pack_kwargs)
        return lbl

    def _panel_entry(self, parent, var, width=22):
        entry = tk.Entry(
            parent, textvariable=var, bg=MIDNIGHT, fg=INK,
            insertbackground=INK, font=UI_FONT, relief='solid',
            bd=1, highlightthickness=1, highlightbackground=INK,
            highlightcolor=INK, width=width,
        )
        entry.pack(fill=tk.X, pady=(0, 8))
        entry.bind('<Return>', self._on_return)
        return entry

    def _panel_check(self, parent, text, var, command=None):
        cb = tk.Checkbutton(
            parent, text=text, variable=var, command=command,
            bg=MIDNIGHT, fg=INK, activebackground=MIDNIGHT, activeforeground=INK,
            selectcolor=MIDNIGHT, font=UI_FONT_SM, relief='flat',
            bd=0, highlightthickness=0, anchor='w', padx=0,
        )
        cb.pack(fill=tk.X, pady=1)
        return cb

    def _panel_button(self, parent, text, command, **pack_kwargs):
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=MIDNIGHT,
            fg=INK,
            activebackground=MIDNIGHT,
            activeforeground=INK,
            font=UI_FONT_SM,
            relief='solid',
            bd=1,
            highlightthickness=0,
            padx=10,
            pady=2,
        )
        btn.pack(**pack_kwargs)
        return btn

    def create_widgets(self):
        self.shell = tk.Frame(self.root, bg=DARK)
        self.shell.pack(fill=tk.BOTH, expand=True)
        self.shell.grid_rowconfigure(0, weight=1)
        self.shell.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self.shell,
            bg=DARK,
            highlightthickness=0,
            bd=0,
            takefocus=1,
        )
        self.canvas.grid(row=0, column=0, sticky='nsew')

        self.right_panel = tk.Frame(
            self.shell, bg=MIDNIGHT, width=PANEL_RIGHT, bd=0, highlightthickness=0,
        )
        self.right_panel.grid(row=0, column=1, sticky='nsew')
        self.right_panel.grid_propagate(False)
        right_inner = tk.Frame(self.right_panel, bg=MIDNIGHT)
        right_inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._panel_label(right_inner, 'DIRECTORY', fill=tk.X)
        self._panel_entry(right_inner, self.var_directory)

        self._panel_label(right_inner, 'INTERVAL', fill=tk.X)
        self._panel_entry(right_inner, self.var_interval)

        self._panel_label(right_inner, 'OPACITY', fill=tk.X)
        self._panel_entry(right_inner, self.var_opacity)

        self._panel_label(right_inner, 'BLEND', fill=tk.X, pady=(0, 2))
        for mode in BLEND_OPTIONS:
            self._panel_check(
                right_inner,
                mode.upper(),
                self.var_blend_modes[mode],
                self._sync_live_options,
            )

        self._panel_label(right_inner, 'WIDTH', fill=tk.X, pady=(8, 0))
        self._panel_entry(right_inner, self.var_width)

        self._panel_label(right_inner, 'HEIGHT', fill=tk.X)
        self._panel_entry(right_inner, self.var_height)

        self._panel_check(right_inner, 'FULLSCREEN', self.var_fullscreen, self._on_fullscreen_toggle)
        self._panel_check(right_inner, 'AUTO-DELETE', self.var_auto_delete, self._sync_live_options)
        self._panel_check(right_inner, 'SAVE COLLAGE', self.var_save_collage, self._sync_live_options)

        self.bottom_panel = tk.Frame(
            self.shell, bg=MIDNIGHT, height=PANEL_BOTTOM, bd=0, highlightthickness=0,
        )
        self.bottom_panel.grid(row=1, column=0, columnspan=2, sticky='ew')
        self.bottom_panel.grid_propagate(False)
        bottom_inner = tk.Frame(self.bottom_panel, bg=MIDNIGHT)
        bottom_inner.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        row = tk.Frame(bottom_inner, bg=MIDNIGHT)
        row.pack(fill=tk.X)

        for text, var in (
            ('ROTATE', self.var_rotate),
            ('MIRROR', self.var_mirror),
            ('CROP', self.var_crop),
            ('GRAYSCALE', self.var_grayscale),
        ):
            cb = tk.Checkbutton(
                row, text=text, variable=var, command=self._sync_live_options,
                bg=MIDNIGHT, fg=INK, activebackground=MIDNIGHT, activeforeground=INK,
                selectcolor=MIDNIGHT, font=UI_FONT_SM, relief='flat',
                bd=0, highlightthickness=0, padx=0,
            )
            cb.pack(side=tk.LEFT, padx=(0, 16))

        self.pause_btn = self._panel_button(
            row, 'PAUSE', self.toggle_pause, side=tk.RIGHT,
        )
        self.hide_btn = self._panel_button(
            row, 'HIDE', self.toggle_ui, side=tk.RIGHT, padx=(0, 8),
        )

        self.hint_label = tk.Label(
            bottom_inner,
            text='ENTER LAUNCH   SPACE/PAUSE   H HIDE UI   ESC QUIT',
            bg=MIDNIGHT, fg=INK, font=UI_FONT_SM, anchor='w',
        )
        self.hint_label.pack(fill=tk.X, pady=(10, 0))

    def _focus_is_entry(self):
        w = self.root.focus_get()
        return w is not None and w.winfo_class() == 'Entry'

    def _on_click_unfocus(self, event=None):
        """Deactivate text fields when clicking the collage or other UI."""
        if event is None:
            self.canvas.focus_set()
            return
        try:
            if event.widget.winfo_class() == 'Entry':
                return
        except tk.TclError:
            return
        self.canvas.focus_set()

    def _on_return(self, event=None):
        if not self.launched:
            self.launch()
        return 'break'

    def _on_space(self, event=None):
        if self._focus_is_entry():
            return
        if self.launched:
            self.toggle_pause()
        return 'break'

    def _on_hide_key(self, event=None):
        if self._focus_is_entry():
            return
        self.toggle_ui()
        return 'break'

    def toggle_ui(self, event=None):
        """Show or hide the side and bottom control panels."""
        self.ui_visible = not self.ui_visible
        if self.ui_visible:
            self.right_panel.grid(row=0, column=1, sticky='nsew')
            self.bottom_panel.grid(row=1, column=0, columnspan=2, sticky='ew')
            self.hide_btn.configure(text='HIDE')
        else:
            self.right_panel.grid_remove()
            self.bottom_panel.grid_remove()
            self.canvas.focus_set()

    def toggle_pause(self, event=None):
        """Toggle pause/resume of image generation."""
        if not self.launched:
            return

        self.paused = not self.paused

        if self.paused:
            if self._after_id is not None:
                try:
                    self.root.after_cancel(self._after_id)
                except Exception:
                    pass
                self._after_id = None
            self.pause_btn.configure(text='RESUME')
        else:
            self.pause_btn.configure(text='PAUSE')
            self._after_id = self.root.after(
                int(self.interval * 1000),
                self.add_next_image,
            )

    def _on_fullscreen_toggle(self):
        self.fullscreen = self.var_fullscreen.get()
        try:
            self.root.attributes('-fullscreen', self.fullscreen)
        except Exception:
            pass

    def _sync_live_options(self):
        self.auto_delete = self.var_auto_delete.get()
        self.save_collage_enabled = self.var_save_collage.get()
        self.rotate = self.var_rotate.get()
        self.mirror = self.var_mirror.get()
        self.crop = self.var_crop.get()
        self.effects = ['grayscale'] if self.var_grayscale.get() else []

        try:
            interval = float(self.var_interval.get().strip())
            if interval > 0:
                self.interval = interval
        except ValueError:
            pass

        opacity_raw = self.var_opacity.get().strip()
        try:
            self.opacity_range = self._parse_opacity(opacity_raw)
            self.opacity_str = opacity_raw
        except Exception:
            pass

        self.blend_modes = [
            mode for mode in BLEND_OPTIONS if self.var_blend_modes[mode].get()
        ]
        self.blend = ','.join(self.blend_modes)

    def _apply_size_from_ui(self):
        try:
            w = int(self.var_width.get().strip())
            h = int(self.var_height.get().strip())
            if w > 0 and h > 0:
                self.canvas_width = w
                self.canvas_height = h
        except ValueError:
            pass

    def launch(self):
        if self.launched:
            return

        directory = Path(self.var_directory.get().strip())
        if not directory.exists() or not directory.is_dir():
            print(f"Error: Directory does not exist: {directory}")
            return

        self.directory = directory
        self._apply_size_from_ui()
        self._sync_live_options()
        self._on_fullscreen_toggle()

        self.launched = True
        self.paused = False
        self.pause_btn.configure(text='PAUSE')
        self.used_images.clear()
        self.live_collage = None
        self.background_collage = None
        self.background_collage_photo = None
        self.total_images_count = 0
        self.last_displayed_image_path = None

        self.hint_label.configure(text='RUNNING   SPACE/PAUSE   H HIDE UI   ESC QUIT')
        self.canvas.focus_set()
        self.add_next_image()

    def _parse_opacity(self, opacity_str):
        """Parse opacity string. Returns (min, max) tuple."""
        opacity_str = opacity_str.strip()
        if opacity_str.startswith('[') and opacity_str.endswith(']'):
            inner = opacity_str[1:-1]
            parts = inner.split('-')
            if len(parts) == 2:
                return (float(parts[0]), float(parts[1]))
        val = float(opacity_str)
        return (val, val)

    def _parse_blend_modes(self, blend_str):
        """Parse blend string into a list of modes."""
        if not blend_str:
            return []
        s = blend_str.strip()
        if s.startswith('[') and s.endswith(']'):
            inner = s[1:-1]
        else:
            inner = s
        tokens = [t.strip() for t in inner.replace(',', ' ').split() if t.strip()]
        allowed = {'divide', 'subtract', 'exclusion', 'normal'}
        modes = [t for t in tokens if t in allowed]
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
        if base_img.size != blend_img.size:
            return blend_img

        base = np.array(base_img.convert('RGB')).astype(float)
        blend = np.array(blend_img.convert('RGB')).astype(float)

        if mode == 'normal':
            result = blend
        elif mode == 'divide':
            result = np.clip((base * 255) / (blend + 1), 0, 255)
        elif mode == 'subtract':
            result = np.clip(base - blend, 0, 255)
        elif mode == 'exclusion':
            result = np.clip(base + blend - (2 * base * blend / 255), 0, 255)
        else:
            result = blend

        if opacity < 1.0:
            result = base * (1 - opacity) + result * opacity
            result = np.clip(result, 0, 255)

        return Image.fromarray(result.astype(np.uint8), 'RGB')

    def refresh_image_list(self):
        """Refresh the list of available images from directory."""
        if not self.directory.exists() or not self.directory.is_dir():
            return []

        return [
            p for p in self.directory.iterdir()
            if p.is_file() and p.suffix.lower() in self.image_extensions
        ]

    def get_unused_image(self):
        """Get a random image that hasn't been used yet."""
        available_images = self.refresh_image_list()
        unused = [img for img in available_images if img not in self.used_images]

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
            img = Image.open(image_path)

            if self.crop:
                w, h = img.size
                crop_percent = random.uniform(0.1, 1.0)
                new_w = max(int(w * crop_percent), 1)
                new_h = max(int(h * crop_percent), 1)
                x = random.randint(0, w - new_w)
                y = random.randint(0, h - new_h)
                img = img.crop((x, y, x + new_w, y + new_h))

            if self.rotate:
                angle = random.choice([0, 90, 180, 270])
                if angle != 0:
                    img = img.rotate(angle, expand=True)

            if self.mirror:
                if random.random() < 0.5:
                    img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)

            for effect in self.effects:
                if effect == 'grayscale':
                    img = img.convert('L').convert('RGB')

            current_opacity = self._get_opacity()

            if current_opacity < 1.0 and not self.blend_modes:
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                r, g, b, a = img.split()
                a = a.point(lambda x: int(x * current_opacity))
                img = Image.merge('RGBA', (r, g, b, a))

            img_width, img_height = img.size

            max_size = max(self.canvas_width, self.canvas_height) * 2
            if img_width > max_size or img_height > max_size:
                scale = max_size / max(img_width, img_height)
                new_width = int(img_width * scale)
                new_height = int(img_height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                img_width, img_height = new_width, new_height

            if self.live_collage is None:
                if self.background_collage is not None:
                    self.live_collage = self.background_collage.copy()
                else:
                    self.live_collage = Image.new('RGB', (self.canvas_width, self.canvas_height), 'white')

            center_x = self.canvas_width // 2
            center_y = self.canvas_height // 2
            offset_x = random.randint(-self.canvas_width, self.canvas_width)
            offset_y = random.randint(-self.canvas_height, self.canvas_height)
            x = center_x + offset_x
            y = center_y + offset_y
            paste_x = x - img_width // 2
            paste_y = y - img_height // 2

            if self.blend_modes:
                mode = random.choice(self.blend_modes)
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
                if img.mode == 'RGBA':
                    base_rgba = self.live_collage.convert('RGBA')
                    layer = Image.new('RGBA', base_rgba.size, (0, 0, 0, 0))
                    layer.paste(img, (paste_x, paste_y))
                    self.live_collage = Image.alpha_composite(base_rgba, layer).convert('RGB')
                else:
                    self.live_collage.paste(img, (paste_x, paste_y))

            self.background_collage = self.live_collage
            self.background_collage_photo = ImageTk.PhotoImage(self.live_collage)
            self.canvas.delete("all")
            self.canvas.create_image(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                image=self.background_collage_photo,
                anchor=tk.CENTER,
            )

        except Exception as e:
            print(f"Error loading image {image_path}: {e}")

    def delete_last_displayed_image(self):
        """Delete the source file of the previously displayed image."""
        if not self.auto_delete or self.last_displayed_image_path is None:
            return
        path = self.last_displayed_image_path
        try:
            if path.exists() and path.is_file():
                path.unlink()
                print(f"Deleted image: {path.name}")
        except Exception as e:
            print(f"Error deleting image {path}: {e}")

    def save_collage(self):
        """Save the current collage as an image file and replace canvas with it."""
        try:
            if self.output_dir.exists():
                for old_file in self.output_dir.glob("collage_*.png"):
                    try:
                        old_file.unlink()
                        print(f"Deleted old collage: {old_file.name}")
                    except Exception as e:
                        print(f"Error deleting old collage {old_file.name}: {e}")

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

            self.load_collage_background(output_path)
            return output_path

        except Exception as e:
            print(f"Error saving collage: {e}")
            return None

    def load_collage_background(self, collage_path):
        """Load a saved collage as the background, replacing current canvas content."""
        try:
            collage_img = Image.open(collage_path)

            collage_img = collage_img.convert('RGB')
            collage_img.load()
            self.background_collage_photo = ImageTk.PhotoImage(collage_img)
            self.background_collage = collage_img
            self.live_collage = collage_img

            self.canvas.delete("all")
            self.canvas.create_image(
                self.canvas.winfo_width() // 2,
                self.canvas.winfo_height() // 2,
                image=self.background_collage_photo,
                anchor=tk.CENTER,
            )

            print(f"Loaded collage background: {collage_path.name}")

        except Exception as e:
            print(f"Error loading collage background: {e}")

    def add_next_image(self):
        """Add the next image to the collage."""
        if not self.launched or self.paused:
            return

        self._sync_live_options()

        image_path = self.get_unused_image()

        if image_path:
            self.delete_last_displayed_image()
            self.load_and_place_image(image_path)
            self.last_displayed_image_path = image_path
            self.total_images_count += 1

            if (
                self.save_collage_enabled
                and self.save_collage_interval > 0
                and self.total_images_count % self.save_collage_interval == 0
            ):
                self.save_collage()

        self._after_id = self.root.after(int(self.interval * 1000), self.add_next_image)


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
  %(prog)s -d images --auto-delete --save-collage
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
        '--auto-delete',
        action='store_true',
        help='Delete the source file of the previously displayed image when a new one is shown'
    )

    parser.add_argument(
        '--save-collage',
        action='store_true',
        help='Save the current collage to the koliazai folder every 50 images'
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

    if args.width <= 0 or args.height <= 0:
        print("Error: Canvas width and height must be positive")
        sys.exit(1)

    if args.interval <= 0:
        print("Error: Interval must be positive")
        sys.exit(1)

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
    CollageViewer(
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
        blend=args.blend,
        auto_delete=args.auto_delete,
        save_collage=args.save_collage,
    )

    root.mainloop()


if __name__ == "__main__":
    main()
