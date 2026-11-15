# DeskBot

DeskBot is a local pan/tilt companion for an assembled RoboBuddy. It centers a visible face and uses person detections as a fallback. Rock-on triggers three nods, thumbs-down triggers a happy nod/wiggle, thumbs-up triggers a moderate head circle, and a raised middle finger triggers a look to the calibrated downward tilt limit.

The build uses a **Raspberry Pi 5 with 2 GB RAM**, **one Raspberry Pi AI Camera (IMX500)** in the head, an **Adafruit CRICKIT HAT #3957**, and two positional MG90S servos. CRICKIT port 1 is pan; port 2 is tilt.
