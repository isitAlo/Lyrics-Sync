import subprocess
import time
import os
import re
import shutil
import syncedlyrics
import certifi
import argparse
import sys
from tinytag import TinyTag
from fonts import BLOCK_LETTERS

# Ensure SSL certificates are found on various Linux distros
os.environ['SSL_CERT_FILE'] = certifi.where()

# Use standard Linux cache directory instead of hardcoding home dir
CACHE_DIR = os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache/lyrics-sync"))
os.makedirs(CACHE_DIR, exist_ok=True)

# --- RENDERING & WRAPPING ---
def get_str_width(text):
    width = 0
    for char in text.upper():
        char_lines = BLOCK_LETTERS.get(char, BLOCK_LETTERS[' '])
        width += len(char_lines[0]) + 1
    return width

def wrap_text(text, max_cols):
    words = text.split()
    lines, current_line = [], []
    for word in words:
        test_line = " ".join(current_line + [word])
        if get_str_width(test_line) <= max_cols:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    if current_line: lines.append(" ".join(current_line))
    return lines

def render_block_segment(text):
    text = text.upper()
    height = 5
    lines = ['' for _ in range(height)]
    for char in text:
        char_lines = BLOCK_LETTERS.get(char, BLOCK_LETTERS[' '])
        for i in range(height):
            lines[i] += char_lines[i] + ' '
    return lines

def draw_centered(text):
    cols, rows = shutil.get_terminal_size()
    wrapped_segments = wrap_text(text, cols - 8)
    all_rendered_lines = []
    for segment in wrapped_segments:
        all_rendered_lines.extend(render_block_segment(segment))
        all_rendered_lines.append("")
    centered = [line.center(cols) for line in all_rendered_lines]
    top_pad = (rows - len(centered)) // 2
    
    # ANSI escape code to clear screen without flickering
    sys.stdout.write("\033[H\033[J")
    print("\n" * max(0, top_pad) + "\n".join(centered))

# --- CORE LOGIC ---
def get_media_info():
    try:
        artist = subprocess.check_output(["playerctl", "metadata", "artist"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
        title = subprocess.check_output(["playerctl", "metadata", "title"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
        pos = float(subprocess.check_output(["playerctl", "position"], stderr=subprocess.DEVNULL).decode("utf-8").strip())
        return artist, title, pos
    except:
        return None, None, 0

def get_filename(artist, title):
    clean_a = " ".join(re.findall(r'\w+', re.sub(r'\(.*?\)|\[.*?\]', '', artist))[:2])
    clean_t = " ".join(re.findall(r'\w+', re.sub(r'\(.*?\)|\[.*?\]', '', title))[:2])
    return f"{clean_a}_{clean_t}.lrc".replace(" ", "_").lower()

def fetch_lyrics(artist, title):
    filename = get_filename(artist, title)
    filepath = os.path.join(CACHE_DIR, filename)

    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            content = f.read()
            # Ignore the placeholder text so it doesn't crash the parser
            if content.strip() and "theres no lyrics here" not in content:
                return content
            elif "theres no lyrics here" in content:
                return None

    try:
        content = syncedlyrics.search(f"{title} {artist}")
        if content:
            with open(filepath, 'w') as f:
                f.write(content)
            return content
    except:
        pass
    return None

def fix_lyrics():
    artist, title, _ = get_media_info()
    if not artist or not title:
        print("Error: No music is currently playing. Play a song first to fix its lyrics.")
        sys.exit(1)

    filename = get_filename(artist, title)
    filepath = os.path.join(CACHE_DIR, filename)

    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        with open(filepath, 'w') as f:
            f.write("theres no lyrics here, you can add them by yourself if ou want\n")
        print(f"Created new lyric file for: {artist} - {title}")
    
    # Opens nano (or your default terminal editor)
    editor = os.environ.get('EDITOR', 'nano')
    os.system(f"{editor} '{filepath}'")

def scan_folder(folder_path):
    if not os.path.isdir(folder_path):
        print(f"Error: Directory '{folder_path}' does not exist.")
        sys.exit(1)

    print(f"Scanning folder: {folder_path}\n")
    valid_exts = ('.mp3', '.flac', '.wav', '.m4a', '.ogg')
    
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(valid_exts):
                file_path = os.path.join(root, file)
                try:
                    tag = TinyTag.get(file_path)
                    if tag.artist and tag.title:
                        print(f"Searching: {tag.artist} - {tag.title}...", end=" ")
                        content = fetch_lyrics(tag.artist, tag.title)
                        if content:
                            print("Success!")
                        else:
                            print("Not Found.")
                except Exception:
                    print(f"Could not read metadata for {file}")

def run_visualizer():
    last_song, synced_data, current_line = "", [], ""
    while True:
        raw_artist, raw_title, pos = get_media_info()
        if not raw_artist:
            time.sleep(1)
            continue

        song_id = f"{raw_artist}-{raw_title}"
        if song_id != last_song:
            last_song = song_id
            content = fetch_lyrics(raw_artist, raw_title)
            synced_data = []
            if content:
                for line in content.splitlines():
                    match = re.search(r'\[(\d+):(\d+\.\d+)\](.*)', line)
                    if match:
                        synced_data.append((int(match.group(1)) * 60 + float(match.group(2)), match.group(3).strip()))
            synced_data.sort()
            sys.stdout.write("\033[H\033[J") # Clear screen on song change

        if synced_data:
            line_to_show = ""
            for t, lyric_text in synced_data:
                if pos >= t: line_to_show = lyric_text
                else: break
            if line_to_show != current_line and line_to_show:
                current_line = line_to_show
                draw_centered(current_line)
        time.sleep(0.05)

def main():
    parser = argparse.ArgumentParser(description="Lyrics-Sync: Universal Lyrics Visualizer")
    parser.add_argument("--search", type=str, help="Search and download lyrics for a song (Artist - Title)")
    parser.add_argument("--fix", action="store_true", help="Open the lyric file for the currently playing song")
    parser.add_argument("--get", type=str, help="Scan a folder and download lyrics for all audio files")
    args = parser.parse_args()

    if args.fix:
        fix_lyrics()
        sys.exit(0)

    if args.get:
        scan_folder(args.get)
        sys.exit(0)

    if args.search:
        if " - " in args.search:
            a, t = args.search.split(" - ", 1)
            print(f"Searching for: {t} by {a}...")
            res = fetch_lyrics(a, t)
            if res:
                print(f"Success! Saved to {CACHE_DIR}")
            else:
                print("Lyrics not found.")
        else:
            print("Usage: --search 'Artist - Title'")
        sys.exit(0)

    run_visualizer()

if __name__ == "__main__":
    main()
