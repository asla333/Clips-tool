import os
import streamlit as st
from pytube import YouTube
from moviepy.editor import VideoFileClip
import numpy as np
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import googleapiclient.http

# -------------------------------
# Function: Auto Detect Viral Segment
# -------------------------------
def detect_viral_segment(video_path, clip_duration):
    """
    Analyzes the audio track of the video to detect a segment with high energy.
    Returns the best start time (in seconds) for a clip of length clip_duration.
    """
    with VideoFileClip(video_path) as video:
        audio = video.audio
        sample_rate = audio.fps  # frames per second for audio
        # Get the audio as a numpy array (sampled at sample_rate)
        audio_array = audio.to_soundarray(fps=sample_rate)
        # Convert to mono by averaging channels if necessary
        if audio_array.ndim > 1:
            audio_array = audio_array.mean(axis=1)
        window_size = int(clip_duration * sample_rate)
        max_rms = 0
        best_start = 0
        # Slide a window over the audio signal in 1-second steps
        for start in range(0, len(audio_array) - window_size, sample_rate):
            window = audio_array[start:start+window_size]
            rms = np.sqrt(np.mean(window**2))
            if rms > max_rms:
                max_rms = rms
                best_start = start / sample_rate
        return best_start

# -------------------------------
# Function: Upload Video to YouTube
# -------------------------------
def upload_video(video_file, title, description, tags, category_id, privacy_status):
    """
    Uploads the video clip to YouTube using the YouTube Data API.
    Make sure you have your client_secrets.json file in the project folder.
    """
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        "client_secrets.json", scopes)
    credentials = flow.run_console()
    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id
        },
        "status": {
            "privacyStatus": privacy_status
        }
    }

    media = googleapiclient.http.MediaFileUpload(video_file, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            st.write("Uploaded {0:.2f}%".format(status.progress() * 100))
    st.success("Upload complete!")
    return response

# -------------------------------
# Main Streamlit Application
# -------------------------------
st.title("YouTube Automation Tool: Long-to-Short Viral Clip")

# Create a folder to store downloads if it doesn't exist
if not os.path.exists("downloads"):
    os.makedirs("downloads")

# Choose extraction method: Manual vs. Auto Detect Viral Segment
method = st.radio("Select Extraction Method:", ("Manual Input", "Auto Detect Viral Segment"))

# Input: YouTube video URL
video_url = st.text_input("Enter the YouTube video URL:")

# Manual method: enter a start time; otherwise, the system auto-detects the best segment.
if method == "Manual Input":
    start_time = st.number_input("Start Time (in seconds):", min_value=0, value=60)
else:
    st.info("The system will automatically detect a viral segment based on audio energy.")

# Input: Clip duration using a dropdown menu
# Options: 30 sec, 45 sec, 60 sec, 90 sec, and 3 min (180 sec)
clip_duration = st.selectbox("Select Clip Duration (in seconds):", options=[30, 45, 60, 90, 180], index=2)

# Button to process the video
if st.button("Process Video"):
    if not video_url:
        st.error("Please enter a valid YouTube URL.")
    else:
        try:
            # --- Step 1: Download the Video ---
            st.info("Downloading video...")
            yt = YouTube(video_url)
            # Select the highest resolution progressive stream (includes both video and audio)
            stream = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
            download_path = stream.download(output_path="downloads")
            st.success("Video downloaded successfully!")

            # --- Step 2: Determine the Clip Start Time ---
            if method == "Auto Detect Viral Segment":
                st.info("Analyzing video for a viral segment based on audio energy...")
                start_time = detect_viral_segment(download_path, clip_duration)
                st.info(f"Detected viral segment starting at {start_time:.2f} seconds.")

            # --- Step 3: Extract the Clip ---
            st.info("Extracting clip...")
            clip_output_path = os.path.join("downloads", "clip.mp4")
            with VideoFileClip(download_path) as video:
                end_time = start_time + clip_duration
                if end_time > video.duration:
                    st.warning("Clip duration exceeds video length. Adjusting to end of video.")
                    end_time = video.duration
                clip = video.subclip(start_time, end_time)
                clip.write_videofile(clip_output_path, codec="libx264", audio_codec="aac")
            st.success("Clip extracted successfully!")
            st.video(clip_output_path)

            # --- Step 4: Optional Upload to YouTube ---
            if st.button("Upload Clip to YouTube"):
                st.info("Fill in the upload details below:")
                upload_title = st.text_input("Video Title for Upload:", value="Short Viral Clip")
                upload_description = st.text_area("Video Description:", value="This is a short viral clip extracted automatically.")
                upload_tags = st.text_input("Video Tags (comma separated):", value="viral,clip,short")
                upload_category = st.text_input("Video Category ID (e.g., 22 for People & Blogs):", value="22")
                privacy_status = st.selectbox("Privacy Status:", ("public", "private", "unlisted"))

                if st.button("Confirm Upload"):
                    response = upload_video(
                        clip_output_path,
                        upload_title,
                        upload_description,
                        upload_tags.split(','),
                        upload_category,
                        privacy_status
                    )
                    st.write("Upload Response:", response)

        except Exception as e:
            st.error(f"An error occurred: {e}")
