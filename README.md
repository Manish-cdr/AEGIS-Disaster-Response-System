# 🚨 AEGIS – AI Emergency Grid Intelligence System

An AI-powered Disaster Response and Smart Surveillance System that analyzes disaster videos, monitors live CCTV feeds using a mobile phone, visualizes incidents on an interactive map, and simulates emergency response through a virtual drone command center.

> **Note:** The drone functionality in this project is a **virtual simulation** designed to demonstrate emergency response workflows. No physical drone hardware is used.

---

## 📖 Overview

AEGIS is a centralized emergency management platform that combines Artificial Intelligence, Computer Vision, Live Video Streaming, Location Services, and Interactive Mapping to help visualize and simulate disaster response operations.

The application consists of three main modules:

- 🚨 Disaster Response
- 📹 CCTV Surveillance
- 🗺️ Live Map & Tracking

---

# ✨ Features

## 🚨 Disaster Response

- Upload disaster videos
- AI-powered video analysis using YOLO
- Detect emergency situations from uploaded videos
- Calculate danger/threat level
- Display detected objects
- Show emergency recommendations
- Timeline of incident analysis
- Enter incident location
- Simulate emergency response

---

## 📹 CCTV Surveillance

Turn any smartphone into a live CCTV camera.

Features include:

- Live mobile camera streaming
- Secure HTTPS camera access
- Real-time surveillance dashboard
- Live AI monitoring
- Active surveillance sessions
- Event and alert logging
- Object detection
- Person detection

Cloudflare Tunnel is used to securely expose the local server over HTTPS, allowing browser camera access on mobile devices.

---

## 🗺️ Live Map & Tracking

- Interactive map powered by Geoapify
- Display incident locations
- GPS coordinate visualization
- Command center monitoring
- Address to coordinate conversion using Geoapify Geocoding API

---

## 🚁 Virtual Drone Simulation

The project includes a **Virtual Drone Simulation Module** to demonstrate emergency response coordination.

When an incident is detected, the system:

- Selects an appropriate virtual drone
- Simulates drone dispatch
- Displays mission status
- Calculates estimated arrival time (ETA)
- Simulates battery level
- Displays mission progress

> **No physical drone is connected or controlled.**  
> This module is purely software-based and created for educational and demonstration purposes.

---

# 🛠️ Technology Stack

## Backend

- Python
- FastAPI
- Uvicorn
- OpenCV
- WebSockets

## Frontend

- HTML
- CSS
- JavaScript

## Artificial Intelligence

- YOLO Object Detection
- OpenCV

## Maps & Location

- Geoapify Maps API
- Geoapify Geocoding API

## Networking

- Cloudflare Tunnel
- WebSocket Streaming

---

# 🔌 APIs & Services Used

| Service | Purpose |
|----------|---------|
| Geoapify Maps API | Interactive map visualization |
| Geoapify Geocoding API | Convert addresses into latitude and longitude |
| Cloudflare Tunnel | Secure HTTPS access for mobile camera streaming |

---

# 📂 Project Structure

```
AEGIS/
│
├── backend/
│   ├── api/
│   ├── routers/
│   ├── services/
│   ├── static/
│   ├── templates/
│   ├── uploads/
│   ├── main.py
│   └── requirements.txt
│
├── simulation/
│   └── drone_sim.py
│
├── README.md
├── .gitignore
└── .env.example
```

---

# ⚙️ Installation

## Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/AEGIS-Disaster-Response-System.git
```

Navigate into the project directory

```bash
cd AEGIS-Disaster-Response-System
```

---

## Create a Virtual Environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## Install Dependencies

```bash
pip install -r backend/requirements.txt
```

---

# 🔑 Environment Variables

Create a `.env` file inside the **backend** directory.

```env
GEOAPIFY_API_KEY=your_geoapify_api_key
```

You can obtain a free API key from Geoapify.

---

# ▶ Running the Project

## Step 1

Navigate to the backend directory.

```bash
cd backend
```

---

## Step 2

Start the FastAPI server.

```bash
uvicorn main:app --reload
```

---

## Step 3

Open your browser.

```
http://127.0.0.1:8000
```

The AEGIS dashboard will load.

---

# 📹 Mobile CCTV Setup

Browsers only allow camera access through **HTTPS**.

Cloudflare Tunnel is used to expose the local FastAPI server securely.

## Step 1

Start the backend server.

```bash
uvicorn main:app --reload
```

---

## Step 2

Start Cloudflare Tunnel.

```bash
cloudflared tunnel --url http://localhost:8000
```

Cloudflare will generate a secure HTTPS URL similar to:

```
https://xxxxxxxx.trycloudflare.com
```

---

## Step 3

Open the following URL on your mobile phone.

```
https://YOUR-CLOUDFLARE-URL/api/cctv/mobile
```

---

## Step 4

Tap **Connect Camera** and allow camera permission.

Your mobile phone will now act as a live CCTV camera.

---

## Step 5

Return to the dashboard and open the **CCTV Surveillance** tab.

The live video stream will appear in the application.

---

# 🚨 Disaster Response Workflow

```
Upload Video
        │
        ▼
AI Video Analysis
        │
        ▼
Threat Detection
        │
        ▼
Danger Level Calculation
        │
        ▼
Emergency Recommendations
        │
        ▼
Virtual Drone Simulation
```

---

# 📹 CCTV Surveillance Workflow

```
Mobile Camera
        │
        ▼
Cloudflare HTTPS Tunnel
        │
        ▼
FastAPI Backend
        │
        ▼
WebSocket Streaming
        │
        ▼
AI Object Detection
        │
        ▼
Live Dashboard
```

---

# 🗺️ Live Map Workflow

```
Incident Location
        │
        ▼
Geoapify Geocoding
        │
        ▼
Interactive Map
        │
        ▼
Command Center Visualization
```

---

# 🚁 Virtual Drone Simulation Workflow

```
Incident Detected
        │
        ▼
Threat Analysis
        │
        ▼
Virtual Drone Assigned
        │
        ▼
Mission Simulation
        │
        ▼
Mission Status Updates
        │
        ▼
Mission Complete
```

---

# 📸 Dashboard Modules

The dashboard includes:

- 🚨 Disaster Response
- 📹 CCTV Surveillance
- 🗺️ Live Map
- 📊 Threat Analysis
- 📍 Incident Tracking
- 🚁 Virtual Drone Fleet
- ⚠️ AI Recommendations
- 📈 System Status

---

# 🔮 Future Enhancements

- Integration with real UAV hardware
- Multiple CCTV camera support
- Fire and smoke classification improvements
- Face recognition
- Automatic emergency notifications
- Incident history database
- Weather API integration
- Emergency services integration
- AI-generated incident reports
- User authentication and role management

---

## 📹 Demo

This project demonstrates:

- AI-based disaster video analysis
- Mobile phone as a live CCTV camera using Cloudflare Tunnel
- Interactive incident mapping with Geoapify
- Virtual drone mission simulation


# 👨‍💻 Author

**Manish Sharma**

Computer Science (Data Science) Engineering Student

---

# 📄 License

This project is developed for educational and academic purposes.
