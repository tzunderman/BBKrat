# BarbeKrat (BBKrat)

🍖🚗 **BBKrat** is the remote-controllable driving barbecue project — because food tastes better when it drives itself to you.  

## Overview
- **BBKrat.py**  
  Runs on a Raspberry Pi.  
  - Reads input from a Bluetooth controller  
  - Sends UART commands to an Arduino  
  - Arduino drives the motors via PWM  

- **run.bat**  
  Simple launcher script for quick testing on Windows.

## Getting Started
1. Clone the repo  
   git clone https://github.com/<your-user>/BBKrat.git  
   cd BBKrat  

2. On Raspberry Pi, run:  
   python3 BBKrat.py  

3. On Windows (for testing):  
   Double-click `run.bat`.

## To-Do
- [ ] Failsafe if controller connection is lost  
- [ ] Lots more 🚀  

---

Built for fun, food, and robotics!  
