# 🎥 Face2Face

A Python video-conferencing application built from scratch with end-to-end encryption and real-time streaming.

## ✨ Features

- 🔐 **Encrypted Communication** – Diffie-Hellman key exchange with AES-CBC encryption
- 🎬 **Live Video & Audio** – Real-time streaming using OpenCV and sounddevice
- 📡 **UDP Streaming** – Optimized for low-latency video and audio
- 🎙️ **Synchronized Controls** – Mic and camera state synced across all participants
- 👥 **Database Authentication** – SQLite user sign-up and login
- 👑 **Host & Guest Roles** – Simple meeting hosting model
- 🔑 **Easy Meeting Codes** – Join meetings with 5-letter codes
- 🖥️ **Native GUI** – Built with wxPython for cross-platform desktop support

## 🚀 Quick Start

### Requirements
- Python 3.10 or higher

### Installation

Install dependencies:
```bash
pip install -r requirements.txt
```

Configure your server in `Common/settings.txt`:
```ini
server_ip=127.0.0.1
server_port=2000
video_port=5000
audio_port=3000
dh_p=797
dh_g=100
```

### Running

Start the server:
```bash
python -m Server.serverLogic
```

Launch the client on each machine:
```bash
python -m Client.GUI.main_app
```

## 📖 Usage

1. **Sign up** or **log in** to your account
2. **Create a meeting** to become the host
3. **Share the meeting code** (5 letters) with participants
4. **Guests join** using the meeting code
5. **Control your media** – mute/unmute, toggle camera on/off, or leave the call

> **Note:** Participants start with microphone muted and camera off. If the host leaves, the meeting ends for all participants.

## 🔧 Architecture

The application uses a distributed architecture with centralized server coordination:

```
┌─────────────────┐
│ Central Server  │
│   (TCP)         │
└────────┬────────┘
         │
    ┌────┴────┐
    │          │
┌───▼──┐   ┌──▼────┐
│ Host │   │ Guest │
│Client│◄─►│Client │
└──────┘   └───────┘
 (TCP/UDP)  (TCP/UDP)
```

### Network Channels

| Channel     | Transport    | Purpose                                    |
|-------------|--------------|--------------------------------------------|
| **Signalling** | TCP → Server | Login, meeting creation, and management  |
| **Control**    | TCP → Host   | Mute/camera state, join, leave events    |
| **Video**      | UDP          | JPEG frames at 15 FPS                    |
| **Audio**      | TCP          | 16-bit PCM audio at 16 kHz               |
