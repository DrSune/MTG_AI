
import os
import subprocess
import yt_dlp

# --- Constants ---
SEARCH_KEYWORDS = ["opening booster pack box mtg", "mtg card opening", "pack opening magic", "new magic set card opening", "unboxing new mtg cards"] #, "mtg gameplay", "magic the gathering shorts"
MAX_VIDEOS_PER_KEYWORD = 10
FRAME_INTERVAL_SECONDS = 1
OUTPUT_DIR = "scraped_frames"

# --- Video Type Settings ---
INCLUDE_SHORTS = True
MIN_VIDEO_DURATION = 10 if INCLUDE_SHORTS else 60

# Settings for long videos
LONG_VIDEO_IGNORE_START_SECONDS = 60
LONG_VIDEO_IGNORE_END_SECONDS = 30

# Settings for shorts (usually no intro/outro)
SHORTS_IGNORE_START_SECONDS = 1
SHORTS_IGNORE_END_SECONDS = 1

# --- yt-dlp options ---
YDL_OPTS = {
    'format': 'bestvideo/best',
    'quiet': True,
}

def extract_frames(video_url, output_folder, duration, ignore_start, ignore_end):
    """
    Extracts frames from a video using ffmpeg, skipping the beginning and end.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    processing_duration = duration - ignore_start - ignore_end
    if processing_duration <= 0:
        print("Video is too short to process after skipping intro/outro.")
        return

    command = [
        'ffmpeg',
        '-ss', str(ignore_start),
        '-i', video_url,
        '-t', str(processing_duration),
        '-vf', f'fps=1/{FRAME_INTERVAL_SECONDS}',
        '-q:v', '2',
        os.path.join(output_folder, 'frame_%04d.png')
    ]

    print(f"Executing ffmpeg command: {' '.join(command)}")
    subprocess.run(command, check=True)

def main():
    """
    Main function to search for videos and extract frames.
    """
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
        for keyword in SEARCH_KEYWORDS:
            print(f"\nSearching for videos with keyword: {keyword}")
            try:
                search_results = ydl.extract_info(f"ytsearch{MAX_VIDEOS_PER_KEYWORD}:{keyword}", download=False)['entries']
                
                for video_info in search_results:
                    duration = video_info.get('duration', 0)
                    if duration < MIN_VIDEO_DURATION:
                        print(f"Skipping video (too short): {video_info.get('title')}")
                        continue

                    video_id = video_info.get('id')
                    video_title = video_info.get('title', 'unknown_title').replace(" ", "_").replace("/", "-")
                    
                    print(f"\nProcessing video: {video_title} ({video_id})")

                    # Determine if the video is a short and set ignore times accordingly
                    is_short = duration < 60
                    if is_short:
                        ignore_start = SHORTS_IGNORE_START_SECONDS
                        ignore_end = SHORTS_IGNORE_END_SECONDS
                    else:
                        ignore_start = LONG_VIDEO_IGNORE_START_SECONDS
                        ignore_end = LONG_VIDEO_IGNORE_END_SECONDS

                    try:
                        info_dict = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
                        video_url = info_dict.get('url')

                        if video_url:
                            video_output_folder = os.path.join(OUTPUT_DIR, f"{video_id}_{video_title[:50]}")
                            extract_frames(video_url, video_output_folder, duration, ignore_start, ignore_end)
                            print(f"Finished extracting frames for {video_title}")
                        else:
                            print(f"Could not get stream URL for {video_title}")

                    except Exception as e:
                        print(f"Error processing video {video_title}: {e}")

            except Exception as e:
                print(f"An error occurred during search for keyword '{keyword}': {e}")

if __name__ == "__main__":
    main()
