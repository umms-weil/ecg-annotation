# ECG Waveform Annotation App

The ECG Waveform Annotation App is a desktop tool for reviewing and annotating physiological waveform data. It supports loading waveform records, marking sequential annotation intervals, saving/resuming work, and finalizing completed waveform reviews.

This repository contains the application source code, Sphinx documentation, test infrastructure, and build configuration.

---

## Repository Structure

```text
ecg-annotation/
├── docs/
│   ├── Makefile
│   ├── make.bat
│   └── source/
│       ├── conf.py
│       ├── index.rst
│       ├── user_manual/
│       └── developer_manual/
├── software/
│   ├── new_app.py
│   ├── new_callbacks.py
│   ├── processing.py
│   ├── requirements.txt
│   ├── assets/
│   └── tests/
└── README.md
```

---

## Documentation

The full user and developer documentation is maintained with Sphinx.

The documentation includes:

- User manual
- Annotation workflow
- Walkthrough videos
- Troubleshooting and FAQ
- Developer manual
- Data layout details
- Waveform loading behavior
- Annotation lifecycle
- Packaging and testing guidance

The documentation is the primary reference for users and developers.

---

## Getting Started

### 1. Clone the Repository

```bash
git clone <repository-url>
cd ecg-annotation
```

Replace `<repository-url>` with the actual GitHub or GitLab repository URL.

---

### 2. Create a Python Virtual Environment

From the repository root:

```bash
cd software
python -m venv .env
source .env/bin/activate
```

On Windows PowerShell:

```powershell
cd software
python -m venv .env
.\.env\Scripts\Activate.ps1
```

---

### 3. Install Dependencies

From the `software/` directory with your virtual environment activated:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If you plan to build the documentation (highly recommended), also install the documentation dependencies:

```bash
python -m pip install sphinx sphinx-rtd-theme sphinx-autodoc-typehints
```

---

## Running the Application from Source

From the base directory with your virtual environment activated:

```bash
python software/src/new_app.py
```

The user manual explains the application workflow in detail.

After building the documentation, open:

```text
docs/build/html/index.html
```

---

## Building the Documentation

The documentation source is located in:

```text
docs/source/
```

The Sphinx configuration file is:

```text
docs/source/conf.py
```

From the repository root:

```bash
cd docs
make html
```

On Windows:

```powershell
cd docs
.\make.bat html
```

Alternatively, run Sphinx directly:

```bash
python -m sphinx -b html source build/html
```

The generated documentation will be available at:

```text
docs/build/html/index.html
```

Open that file in a web browser.

---

## Walkthrough Videos

Walkthrough videos are expected to be available to Sphinx under:

```text
docs/source/_static/videos/
```

If the videos are stored in:

```text
software/assets/
```

copy them before building the docs:

```bash
mkdir -p docs/source/_static/videos
cp software/assets/*.mp4 docs/source/_static/videos/
```

Then rebuild:

```bash
cd docs
make html
```

On Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path docs\source\_static\videos
Copy-Item software\assets\*.mp4 docs\source\_static\videos\
cd docs
.\make.bat html
```

---

## Building a Windows Executable

The app can be packaged with PyInstaller.

From the `software/` directory:

```bash
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ECGWaveformAnnotationApp new_app.py
```

The executable will be created under:

```text
software/dist/
```

---


## Data and Privacy Notes

DO NOT COMMIT:

- Raw waveform data
- Annotation output files
- Patient identifiers
- PHI/ePHI
- Local user-specific data
- Large generated build artifacts

Use synthetic test data for development and testing.

Recommended ignored paths include:

```text
software/.env/
software/.venv/
software/build/
software/dist/
software/release/
software/__pycache__/
docs/build/
docs/source/_static/videos/*.mp4
.coverage
coverage.xml
.pytest_cache/
```

---

## Quick Documentation Build and Open

From the repository root:

```bash
cd docs
make html
open build/html/index.html
```

On Windows PowerShell:

```powershell
cd docs
.\make.bat html
start build\html\index.html
```

---

## Support

For project-specific support, refer to the Sphinx documentation after building it:

```text
docs/build/html/index.html
```

The documentation contains the user manual, developer manual, troubleshooting guide, FAQ, and support instructions.