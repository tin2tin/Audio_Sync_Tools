# Audio Sync Tools for Blender

![Blender Version](https://img.shields.io/badge/Blender-4.5+-orange.svg)![License](https://img.shields.io/badge/License-GPL-blue.svg)

This add-on provides a suite of powerful, professional-grade tools for synchronizing audio directly within Blender's Video Sequence Editor (VSE). It is designed for filmmakers and editors who work with dual-system audio (e.g., sound recorded separately on a dedicated audio recorder and on the camera) and need a fast, accurate way to sync their rushes.

The add-on's flagship feature, **"Match and Sync Audio,"** uses a sophisticated, multi-stage algorithm to automatically identify which dedicated audio clips belong to which video clips and then performs a sample-accurate sync based on a clapperboard or other sharp, loud sound.

https://github.com/user-attachments/assets/68d94c9d-5c7b-4cfa-81ae-b61e2daf753b

## Features

-   **Automatic "Match and Sync Audio":**
    -   Intelligently analyzes all selected sound strips (from video and audio files).
    -   Uses a definitive **"Sync-and-Verify"** algorithm to find the correct 1-to-1 pairings, preventing mismatches.
    -   Performs a precise, sample-accurate sync based on the loudest peak (clapperboard).
    -   Asynchronous, non-blocking process with live feedback in the Blender status bar, so the UI never freezes.
-   **Manual "Sync to Active Strip":**
    -   For tricky shots or manual overrides, allows you to force-sync one or more selected audio strips to the active (last-selected) strip.
    -   Fast, simple, and direct.
-   **Automatic Dependency Installation:**
    -   On the first run, automatically installs the required Python libraries (`numpy`, `scipy`, `moviepy`) using `pip`.
-   **Robust File Handling:**
    -   Uses `moviepy` to reliably extract audio from a wide range of video containers (`.mp4`, `.mov`, `.mkv`, etc.) that Blender can import.

## Installation

1.  Download the latest version of the add-on (`professional_audio_sync.py`).
2.  In Blender, go to `Edit` > `Preferences` > `Add-ons`.
3.  Click the `Install...` button and navigate to the downloaded `.py` file.
4.  Enable the add-on by checking the box next to its name ("Audio Sync Tools").


## Location:

Sequencer > Strip > Transform > Sync Sound to Sound

## Usage

The tools will appear in the Video Sequencer's `Strip` > `Transform` menu.

![sync_sound](https://github.com/tin2tin/sync_sound/assets/1322593/973b94ae-d89c-49f5-8a4c-3e77b259c1be)

### Automatic Sync (`Match and Sync Audio`)

This is the main, powerful feature for syncing all your daily rushes in one go.

1.  Import all your video clips and their corresponding dedicated audio files into the Sequencer.
2.  Select **all** the sound strips you want to process (both from the video files and the `.wav` files).
3.  Go to `Strip` > `Transform` > **Match and Sync Audio**.
4.  The process will start in the background. You can monitor its progress in the Blender status bar at the bottom of the window. The UI will remain responsive.


**IMPORTANT: First-Time Use**
The very first time you run the operator, it will pause to install the necessary Python libraries. This requires an internet connection. The console will show the installation progress. After it reports success, you must **run the "Match and Sync Audio" operator a second time** to perform the sync. This is a one-time setup.

### Manual Sync (`Sync to Active Strip`)

Use this when you know exactly which strips need to be synced together.

1.  Select the audio strip(s) you want to move.
2.  **Last**, select the audio strip you want to use as the stationary reference target. This strip will now have a bright white outline, making it the **active strip**.
3.  Go to `Strip` > `Transform` > **Sync Audio to Active Strip**.
4.  The selected strips will be instantly moved to align with the active one.

## How It Works (The "Magic")

The "Match and Sync" operator uses a definitive, multi-stage algorithm that mimics an assistant editor's workflow to ensure maximum accuracy:

1.  **Fast Candidate Generation:** First, the script performs a very fast analysis on the loudest sound (the "peak profile") of every audio clip. It uses this to create a ranked list of the most likely video candidates for each dedicated audio file. This is a quick "best guess."
2.  **Definitive Verification:** The script then takes the top candidates for each audio file and puts them through a much more rigorous test. It temporarily aligns the clips and calculates the **Energy Contour Correlation**—a statistical analysis of the audio's volume and cadence over time. If the rhythm and energy of the two clips are a strong match, the pairing is verified.
3.  **Competitive Assignment:** After verifying all the top candidates, the script looks at the complete matrix of verification scores. It finds the pair with the absolute highest score, locks it in as a definitive match, and removes them from the pool. It then repeats this process, ensuring that only the most confident pairs are made. This "best-first" approach prevents a single video clip from being incorrectly claimed by multiple audio clips.

## Troubleshooting

-   **The first time I run it, nothing happens!**
    -   This is the expected behavior. The first run is for installing dependencies. Simply run the operator again, and it will work.
-   **The operator seems to hang or Blender freezes.**
    -   This should not happen with the latest version. The "Match and Sync" process is asynchronous. If you experience a freeze, please check the Blender System Console (`Window` > `Toggle System Console`) for error messages.
-   **Some of my clips were not matched.**
    -   The algorithm is designed to be conservative to avoid bad matches. A match will be skipped if:
        1.  The duration of the audio and video clips differs by more than 15 seconds.
        2.  The final "Energy Contour Correlation" score is too low, meaning the algorithm could not confidently verify that the takes were the same.
-   **The sync is slightly off.**
    -   The script relies on the loudest sound being the sync point. If there is a much louder sound than the clapperboard (e.g., a door slam) at the start of a take, it may use that as the reference. In these rare cases, a small manual adjustment may be needed.

## License

This add-on is licensed under the GPL.

## Acknowledgments

-   Based on an original script by **tintwotin**.
-   This project relies on the incredible work of the following open-source libraries:
    -   [Librosa](https://librosa.org/) for audio analysis.
    -   [MoviePy](https://zulko.github.io/moviepy/) for robust audio extraction.
    -   [NumPy](https://numpy.org/) & [SciPy](https://scipy.org/) for numerical processing.
