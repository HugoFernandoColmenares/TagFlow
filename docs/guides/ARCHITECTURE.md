# Architecture Guidelines — TagFlow: Local Image Organization & Metadata Engine

This document outlines the architectural standards, directory layout, use cases, and technical implementation blueprint for **TagFlow**, a desktop-grade Python application designed for local image sorting, tagging, duplicate detection, and batch manipulation.

---

## 1. Architectural Vision & Core Principles

TagFlow operates as a local-first, standalone desktop application combining a Python backend (handling filesystem operations, image parsing, and SQLite persistence) with a clean, responsive graphical interface.

* **Local-First & Privacy-Focused:** All file parsing, SQLite transactions, and image processing happen entirely on the user's machine. No assets or metadata ever leave the local environment.
* **Separation of Concerns:** Strict adherence to clean architecture principles—decoupling the filesystem reader/writers and the SQLite storage layer from the UI presentation layer.
* **Non-Blocking Execution:** Heavy tasks (such as recursive folder traversal, hashing for duplicate detection, and bulk zipping) must run asynchronously using background threads or worker queues to prevent freezing the GUI.

---

## 2. Technology Stack

| Layer | Technology | Purpose |
| --- | --- | --- |
| **Backend & Core Logic** | Python 3.11+ | File system operations, image manipulation, and data transformation scripts. |
| **Image Processing** | Pillow (`PIL`) & OpenCV (`cv2`) | Extracts dimensions, computes quality metrics, and handles image compression. |
| **Local Persistence** | SQLite3 + SQLAlchemy (or native `sqlite3`) | Stores custom tags, cached file metadata, and grouping configurations. |
| **User Interface (GUI)** | PyQt6 / PySide6 (or CustomTkinter / Flet) | Cross-platform desktop interface providing a modern, friendly user experience. |
| **Packaging & Distribution** | PyInstaller | Bundles the Python application and assets into a standalone executable. |

---

## 3. Modular Directory Structure

```text
tagflow/
├── core/                        # Core backend controllers & business logic
│   ├── scanner.py               # Directory traversal and metadata extraction
│   ├── duplicates.py            # Duplicate detection engine (naming patterns + hashing)
│   ├── analytics.py             # Statistical analysis calculations
│   └── database.py              # SQLite connection pool and schema migrations
├── ui/                          # Graphical user interface layer
│   ├── main_window.py           # Master application window layout
│   ├── components/              # Reusable UI widgets (gallery grid, filter bar, tag manager)
│   └── workers.py               # Background worker threads for async file processing
├── utils/                       # Shared utility helpers (file compressors, path sanitizers)
├── assets/                      # Icons, styling sheets, and local UI resources
└── main.py                      # Application entry point

```

---

## 4. Use Case Specifications & Technical Implementation

### A. Folder Scanning & Content Profiling

* **Trigger:** User selects a root directory via a native folder dialog.
* **Execution:** A background worker recursively scans the directory, parsing total image count, cumulative file weight (size), format distributions (JPEG, PNG, WebP, etc.), and subfolder depth.
* **Data Model (Image Metadata):** Each discovered image extracts dimensions (`width` x `height`), exact file size in bytes, format extension, and a localized custom `tags` array stored as a comma-separated string or JSON blob in SQLite.

### B. Dynamic Filtering & Statistical Analysis

* **Filters:** Real-time query parameters evaluated against the SQLite database or cached view states:
* *Quality:* Based on resolution tiers (HD, 4K, Low-res) or compression density.
* *File Weight:* Size thresholds (e.g., < 500KB, > 5MB).
* *Tags:* Multi-select filtering matching user-defined custom arrays.


* **Statistical Analysis:** Computes and displays dynamic metrics: average file size, most common image formats, total disk footprint consumed by the folder, and tag distribution charts.

### C. Duplicate Detection Engine

* **Level 1 (Nesting & Naming Heuristic):** Analyzes Windows-style naming patterns (e.g., matching `image.jpg` against `image(1).jpg`, `image (copy).jpg`).
* **Level 2 (Advanced Algorithmic Matching):** Optional toggle allowing byte-to-byte hash checks (MD5/SHA-256) or perceptual hashing (`phash`) to identify visually identical assets regardless of file names or minor resolution differences.

### D. Asset Manipulation (CRUD & File Operations)

* **Metadata Editing:** Updates custom tags and file names instantly in the SQLite cache and applies physical file renames on disk securely.
* **File Operations:** Move or delete images with automatic path resolution updates in the database.
* **Grouping & Compressing:**
* *Grouping:* Creates a new subfolder inside the target directory and moves selected asset batches into it.
* *Compression:* Utilizes native Python zip libraries or image optimization loops to bundle selected folders into compressed `.zip` archives.



---

## 5. Coding Standards & Engineering Rules

* **KISS & DRY:** Keep database queries clean and reusable. Avoid redundant file system scans by relying on the SQLite metadata cache once initial folder indexing completes.
* **Error Handling:** Gracefully catch permission errors (e.g., restricted folders) or corrupted image files, logging them to a local error ledger without crashing the application loop.
* **Type Hinting:** All core Python functions must use explicit type hints (`typing` module) to maintain robust code readability and prevent runtime type mismatches.