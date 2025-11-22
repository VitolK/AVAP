#!/bin/bash

# Picture Viewer TUI Script
# Select and open pictures in a separate window

# Colors for better UI
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to convert WSL path to Windows path
wsl_to_win_path() {
    local wsl_path="$1"
    # Convert /mnt/c/... to C:\...
    if [[ "$wsl_path" =~ ^/mnt/([a-zA-Z])/(.*) ]]; then
        local drive="${BASH_REMATCH[1]}"
        local path="${BASH_REMATCH[2]}"
        # Convert to uppercase drive letter (works in bash 4+)
        drive=$(echo "$drive" | tr '[:lower:]' '[:upper:]')
        # Replace forward slashes with backslashes
        path=$(echo "$path" | tr '/' '\\')
        echo "${drive}:\\$path"
    else
        echo "$wsl_path"
    fi
}

# Function to detect if we're in WSL
is_wsl() {
    if [[ -f /proc/version ]] && grep -qi microsoft /proc/version; then
        return 0
    fi
    return 1
}

# Function to detect OS and open image accordingly
# Uses Windows default image viewer which opens in the same window if already open
open_image() {
    local image_path="$1"
    local replace_window="${2:-false}"  # For future use if needed
    
    # Check if we're in WSL first
    if is_wsl; then
        # WSL detected - convert path and use Windows commands
        local win_path=$(wsl_to_win_path "$(realpath "$image_path")")
        if command -v cmd.exe &> /dev/null; then
            # Use start with /wait to potentially reuse the same window
            # Windows Photos app will open in the same window if already open
            cmd.exe /c start "" "$win_path" 2>/dev/null
        elif command -v explorer.exe &> /dev/null; then
            explorer.exe "$win_path" 2>/dev/null
        else
            # Fallback: try wslview if available
            if command -v wslview &> /dev/null; then
                wslview "$image_path"
            else
                echo -e "${RED}Error: Could not find a way to open images in WSL${NC}"
                echo -e "${YELLOW}Trying to use xdg-open as fallback...${NC}"
                if command -v xdg-open &> /dev/null; then
                    xdg-open "$image_path"
                else
                    exit 1
                fi
            fi
        fi
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || -n "$WINDIR" ]]; then
        # Windows (Git Bash or native)
        # Windows default image viewer opens in same window if already open
        if command -v start &> /dev/null; then
            start "$image_path"
        elif command -v explorer.exe &> /dev/null; then
            explorer.exe "$image_path"
        else
            echo -e "${RED}Error: Could not find a way to open images on Windows${NC}"
            exit 1
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS - Preview opens in same window if already open
        open "$image_path"
    else
        # Linux (native, not WSL)
        if command -v xdg-open &> /dev/null; then
            xdg-open "$image_path"
        elif command -v gnome-open &> /dev/null; then
            gnome-open "$image_path"
        else
            echo -e "${RED}Error: Could not find a way to open images on Linux${NC}"
            exit 1
        fi
    fi
}

# Function to get a random image from directory
get_random_image() {
    local dir="${1:-.}"
    local images=($(get_image_files "$dir"))
    
    if [ ${#images[@]} -eq 0 ]; then
        return 1
    fi
    
    # Get random index
    local random_index=$((RANDOM % ${#images[@]}))
    echo "${images[$random_index]}"
}

# Function to get image files from directory
get_image_files() {
    local dir="${1:-.}"
    find "$dir" -maxdepth 1 -type f \( \
        -iname "*.jpg" -o -iname "*.jpeg" -o \
        -iname "*.png" -o -iname "*.gif" -o \
        -iname "*.bmp" -o -iname "*.webp" -o \
        -iname "*.tiff" -o -iname "*.tif" -o \
        -iname "*.svg" -o -iname "*.ico" \
    \) | sort
}

# Main function with fzf (fuzzy finder)
select_with_fzf() {
    local dir="${1:-.}"
    local images=$(get_image_files "$dir")
    
    if [ -z "$images" ]; then
        echo -e "${YELLOW}No image files found in directory: $dir${NC}"
        exit 1
    fi
    
    while true; do
        # Add random option to the list
        local images_with_random=$(echo -e "🎲 RANDOM IMAGE\n$images")
        
        echo -e "${BLUE}Select an image (use arrow keys, type to filter, Enter to open, Esc to exit):${NC}"
        selected=$(echo "$images_with_random" | fzf --height=40% --border --prompt="📷 Select image > " --header="Picture Viewer - Navigate with arrow keys, filter by typing | 'RANDOM IMAGE' for random selection | Esc to quit")
        
        if [ -z "$selected" ]; then
            echo -e "${YELLOW}Exiting...${NC}"
            exit 0
        fi
        
        if [[ "$selected" == "🎲 RANDOM IMAGE" ]]; then
            local random_img=$(get_random_image "$dir")
            if [ -n "$random_img" ]; then
                echo -e "${GREEN}Opening random image: $(basename "$random_img")${NC}"
                open_image "$random_img"
                echo -e "${YELLOW}Press Enter to continue...${NC}"
                read -r
            else
                echo -e "${RED}Error: Could not get random image${NC}"
                echo -e "${YELLOW}Press Enter to continue...${NC}"
                read -r
            fi
        else
            echo -e "${GREEN}Opening: $(basename "$selected")${NC}"
            open_image "$selected"
            echo -e "${YELLOW}Press Enter to continue...${NC}"
            read -r
        fi
    done
}

# Fallback function with simple menu (if fzf not available)
select_with_menu() {
    local dir="${1:-.}"
    local images=($(get_image_files "$dir"))
    
    if [ ${#images[@]} -eq 0 ]; then
        echo -e "${YELLOW}No image files found in directory: $dir${NC}"
        exit 1
    fi
    
    while true; do
        echo ""
        echo -e "${BLUE}=== Picture Viewer ===${NC}"
        echo -e "${BLUE}Select an image to open:${NC}"
        echo ""
        
        # Create menu with random option at the top
        local menu_items=("🎲 RANDOM IMAGE" "${images[@]}")
        
        PS3="Enter number to select (or 'q' to quit, 'r' for random): "
        select img in "${menu_items[@]}"; do
            if [ "$REPLY" = "q" ] || [ "$REPLY" = "Q" ]; then
                echo -e "${YELLOW}Exiting...${NC}"
                exit 0
            elif [ "$REPLY" = "r" ] || [ "$REPLY" = "R" ] || [[ "$img" == "🎲 RANDOM IMAGE" ]]; then
                local random_img=$(get_random_image "$dir")
                if [ -n "$random_img" ]; then
                    echo -e "${GREEN}Opening random image: $(basename "$random_img")${NC}"
                    open_image "$random_img"
                    echo -e "${YELLOW}Press Enter to continue, or 'q' to quit...${NC}"
                    read -r
                    break  # Break out of select, continue while loop
                else
                    echo -e "${RED}Error: Could not get random image${NC}"
                    break
                fi
            elif [ -n "$img" ] && [[ "$img" != "🎲 RANDOM IMAGE" ]]; then
                echo -e "${GREEN}Opening: $(basename "$img")${NC}"
                open_image "$img"
                echo -e "${YELLOW}Press Enter to continue, or 'q' to quit...${NC}"
                read -r
                break  # Break out of select, continue while loop
            else
                echo -e "${RED}Invalid selection. Please try again.${NC}"
                break
            fi
        done
    done
}

# Main script
main() {
    local target_dir="${1:-.}"
    
    # Check if directory exists
    if [ ! -d "$target_dir" ]; then
        echo -e "${RED}Error: Directory '$target_dir' does not exist${NC}"
        exit 1
    fi
    
    # Try to use fzf if available, otherwise fall back to simple menu
    if command -v fzf &> /dev/null; then
        select_with_fzf "$target_dir"
    else
        echo -e "${YELLOW}Note: 'fzf' not found. Using simple menu.${NC}"
        echo -e "${YELLOW}Install 'fzf' for a better experience: https://github.com/junegunn/fzf${NC}"
        echo ""
        select_with_menu "$target_dir"
    fi
}

# Run main function
main "$@"

