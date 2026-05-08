import subprocess
import time
import os
import re
import shutil
import syncedlyrics
import certifi
import sys
import argparse

os.environ['SSL_CERT_FILE'] = certifi.where()
CACHE_DIR = os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache/lyrics-sync"))
os.makedirs(CACHE_DIR, exist_ok=True)

from fonts import BLOCK_LETTERS

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
        data = subprocess.check_output(
            "playerctl metadata --format '{{title}}|||{{artist}}|||{{position}}'",
            shell=True, executable="/bin/sh", stderr=subprocess.STDOUT
        ).decode("utf-8").strip()
        if not data or "No player found" in data: return None, None, 0
        parts = data.split("|||")
        title = parts[0].strip()
        artist = parts[1].strip()
        try:
            raw_pos = float(parts[2])
            pos = raw_pos / 1000000 if raw_pos > 100000 else raw_pos
        except: pos = 0.0
        title = re.sub(r' - YouTube Music| - Spotify| - Topic| - YouTube| - Brave', '', title, flags=re.I)
        if (not artist or artist == "") and " - " in title:
            split_parts = title.split(" - ", 1)
            artist, title = split_parts[0].strip(), split_parts[1].strip()
        return artist, title, pos
    except: return None, None, 0

def get_lrc_path(artist, title):
    clean_a = " ".join(re.findall(r'\w+', re.sub(r'\(.*?\)|\[.*?\]', '', artist))[:2])
    clean_t = " ".join(re.findall(r'\w+', re.sub(r'\(.*?\)|\[.*?\]', '', title))[:2])
    filename = f"{clean_a}_{clean_t}.lrc".replace(" ", "_").lower()
    return os.path.join(CACHE_DIR, filename)

def fetch_lyrics(artist, title):
    if not title: return None
    filepath = get_lrc_path(artist, title)
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            content = f.read()
            return content if "theres no lyrics here" not in content else None
    try:
        search_query = f"{title} {artist}" if artist else title
        content = syncedlyrics.search(search_query)
        if content:
            with open(filepath, 'w') as f: f.write(content)
            return content
    except: pass
    return None

def fix_lyrics(manual_path=None):
    if manual_path:
        from tinytag import TinyTag
        try:
            tag = TinyTag.get(manual_path)
            artist, title = tag.artist or "", tag.title or ""
        except:
            print("Error: Could not read file tags."); return
    else:
        artist, title, _ = get_media_info()
    
    if not title:
        print("Error: No song detected."); return
        
    filepath = get_lrc_path(artist, title)
    print(f"\n--- Editing Lyrics for: {title} by {artist} ---")
    print(f"File Location: {filepath}\n")
    
    if os.path.exists(filepath):
        print("Current Content:")
        with open(filepath, 'r') as f:
            print(f.read())
    else:
        print("No local file found. Creating a new one...")
        with open(filepath, 'w') as f:
            f.write("[00:00.00] New lyric file...")
            
    input("\nPress Enter to open the editor and make changes...")
    editor = os.environ.get('EDITOR', 'nano')
    subprocess.call([editor, filepath])

def run_visualizer():
    last_song, synced_data, current_line = "", [], ""
    while True:
        raw_artist, raw_title, pos = get_media_info()
        if not raw_title:
            time.sleep(1); continue
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

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", nargs='?', const=True)
    args = parser.parse_args()
    if args.fix:
        path = args.fix if isinstance(args.fix, str) else None
        fix_lyrics(path)
    else:
        run_visualizer()
