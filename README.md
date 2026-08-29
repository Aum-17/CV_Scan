# CV_scan — Object Recognition

A lightweight computer-vision based object (shape) recognition application. It uses **OpenCV** to detect shapes (Triangle, Square, Rectangle, Pentagon, Hexagon, Circle, Oval) from an image or a live webcam feed, and serves everything through a browser-based web interface.

The app runs a small Python HTTP server that:

- Recognizes shapes in uploaded images (`/api/analyze`)
- Detects objects in a live camera feed (`/api/frame`)
- Accepts user feedback/corrections to improve future detections (`/api/feedback`)

## How it works

- **Shape detection** (`shape_recognition.py`): extracts contours from the frame, computes polygon approximations and geometry-based metrics, and classifies each contour into one of the supported shapes.
- **Feedback learning** (`feedback_store.py`): stores user corrections in `data/` and uses them to refine future predictions via nearest-feature matching.
- **Server** (`server.py`): a `ThreadingHTTPServer` that serves the `static/` front-end and exposes the JSON API endpoints.

## Tech stack

- Python 3
- OpenCV
- NumPy
- Plain HTML / CSS / JavaScript (no front-end framework)

## Project structure

```
.
├── server.py              # HTTP server + API endpoints
├── shape_recognition.py   # Shape/object detection logic
├── feedback_store.py      # Stores & applies user feedback
├── static/                # Front-end (index.html, app.js, style.css)
├── data/                  # Created at runtime (user feedback/corrections)
├── requirements.txt       # Python dependencies
└── README.md
```

## Prerequisites

- [Python 3.8+](https://www.python.org/downloads/)
- [pip](https://pip.pypa.io/en/stable/installation/)
- [Git](https://git-scm.com/) (to clone the repo)

## Steps to run on another device

1. **Clone the repository**

   ```bash
   git clone <your-github-repo-url>
   cd Object_Recognition_CV
   ```

2. **Create a virtual environment** (recommended)

   ```bash
   python3 -m venv .venv
   ```

3. **Activate the virtual environment**

   - On macOS / Linux:
     ```bash
     source .venv/bin/activate
     ```
   - On Windows:
     ```powershell
     .venv\Scripts\activate
     ```

4. **Install the dependencies**

   ```bash
   pip install -r requirements.txt
   ```

5. **Run the server**

   ```bash
   python server.py
   ```

   To use a different port (default is `8000`):

   ```bash
   python server.py --port 9000
   ```

6. **Open the app**

   Open your browser and go to:

   ```
   http://127.0.0.1:8000
   ```

> **Note:** The app needs access to your webcam for the live-detection mode, so make sure to allow camera permissions in your browser.

## Usage

- **Image mode** — upload an image; detected shapes are highlighted with labels and confidence scores.
- **Live mode** — point your camera at objects; shapes are recognized in real time.
- **Feedback** — correct a misclassified shape; the model remembers your correction and improves over time.

## Deployment to GitHub

Before pushing, make sure you are **not** committing private/generated files. Add a `.gitignore` if it doesn't exist, containing at least:

```
.venv/
__pycache__/
data/
```

The `data/` folder is generated at runtime, so it should not be committed.

Then push your code as usual:

```bash
git add .
git commit -m "Add CV_scan object recognition app"
git push origin main
```

## License

This project is licensed under the [MIT License](LICENSE).
