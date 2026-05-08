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

os.environ['SSL_CERT_FILE'] = certifi.where()
CACHE_DIR = os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache/lyrics-sync"))
os.makedirs(CACHE_DIR, exist_ok=True)

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
    sys.stdout.write("\033[H\033[J")
    print("\n" * max(0, top_pad) + "\n".join(centered))

def get_media_info():
    try:
        players = subprocess.check_output(["playerctl", "-l"], stderr=subprocess.DEVNULL).decode("utf-8").strip().splitlines()
        if not players: return None, None, 0
        
        active_player = None
        for p in players:
            status = subprocess.check_output(["playerctl", "-p", p, "status"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
            if status == "Playing":
                active_player = p
                break
                
        if not active_player:
            active_player = "playerctld"

        artist = subprocess.check_output(["playerctl", "-p", active_player, "metadata", "artist"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
        title = subprocess.check_output(["playerctl", "-p", active_player, "metadata", "title"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
        pos = float(subprocess.check_output(["playerctl", "-p", active_player, "position"], stderr=subprocess.DEVNULL).decode("utf-8").strip())

        title = re.sub(r' - YouTube Music| - Spotify| - Topic| - YouTube', '', title, flags=re.I)
        if not artist and " - " in title:
            parts = title.split(" - ", 1)
            artist, title = parts[0], parts[1]
        
        return artist, title, pos
    except:
        return None, None, 0

def get_filename(artist, title):
    clean_a = " ".join(re.findall(r'\w+', re.sub(r'\(.*?\)|\[.*?\]', '', artist))[:2])
    clean_t = " ".join(re.findall(r'\w+', re.sub(r'\(.*?\)|\[.*?\]', '', title))[:2])
    return f"{clean_a}_{clean_t}.lrc".replace(" ", "_").lower()

def fetch_lyrics(artist, title):
    if not artist or not title: return None
    filename = get_filename(artist, title)
    filepath = os.path.join(CACHE_DIR, filename)

    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            content = f.read()
            return content if "theres no lyrics here" not in content else None

    try:
        content = syncedlyrics.search(f"{title} {artist}")
        if content:
            with open(filepath, 'w') as f: f.write(content)
            return content
    except:
        pass
    return None

def fix_lyrics():
    artist, title, _ = get_media_info()
    if not artist or not title:
        print("No active song found."); sys.exit(1)
    filename = get_filename(artist, title)
    filepath = os.path.join(CACHE_DIR, filename)
    if not os.path.exists(filepath):
        with open(filepath, 'w') as f: f.write("theres no lyrics here, you can add them by yourself if ou want\n")
    os.system(f"{os.environ.get('EDITOR', 'nano')} '{filepath}'")

def scan_folder(folder_path):
    folder_path = os.path.expanduser(folder_path)
    valid_exts = ('.mp3', '.flac', '.wav', '.m4a', '.ogg')
    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.lower().endswith(valid_exts):
                try:
                    tag = TinyTag.get(os.path.join(root, file))
                    if tag.artist and tag.title: fetch_lyrics(tag.artist, tag.title)
                except: continue

def run_visualizer():
    last_song, synced_data, current_line = "", [], ""
    while True:
        raw_artist, raw_title, pos = get_media_info()
        if not raw_artist or not raw_title:
            time.sleep(1); continue
        
        song_id = f"{raw_artist}-{raw_title}"
        if song_id != last_song:
            last_song = song_id
            content = fetch_lyrics(raw_artist, raw_title)
            synced_data = []
            if content:
                for line in content.splitlines():
                    match = re.search(r'\[(\d+):(\d+\.\d+)\](.*)', line)
                    if match: synced_data.append((int(match.group(1)) * 60 + float(match.group(2)), match.group(3).strip()))
            synced_data.sort()
            sys.stdout.write("\033[H\033[J")

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", type=str)
    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--get", type=str)
    args = parser.parse_args()
    if args.fix: fix_lyrics()
    elif args.get: scan_folder(args.get)
    elif args.search:
        if " - " in args.search:
            a, t = args.search.split(" - ", 1)
            fetch_lyrics(a, t)
    else: run_visualizer()

if __name__ == "__main__":
    main()
