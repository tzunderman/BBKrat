import time
import pygame
import serial
import serial.tools.list_ports as stlp
from queue import Queue, Full
from threading import Thread

# ---------------- Constants ----------------=
# Axes
AXIS_L_STICK_X = 0
AXIS_L_STICK_Y = 1
AXIS_R_STICK_X = 3
AXIS_R_STICK_Y = 4

# Shoulder buttons
BTN_SHOULDER_UP = 5
BTN_SHOULDER_DOWN = 4
# D-pad buttons
HAT_DPAD_Y = 1

# Demo mode to see which button index of the controller is what.
BTN_INDEX_DEMO_MODE = False
# Print mode to print data in the terminal instead of sending it to an Arduino
PRINT_MODE = False

measurement_queue: Queue[dict[str, str | int | dict[str, float]]] = Queue(maxsize=256)

def connect_arduino() -> serial.Serial:
    print("Try to connect to an Arduino")
    while True:
        arduinos = [port.device for port in stlp.comports() if port.manufacturer and "Arduino" in port.manufacturer]
        if arduinos:
            ser = serial.Serial(arduinos[0], 115200)
            print("Connected to an Arduino")
            time.sleep(1) # Wait for Arduino reboot
            
            # Start reader thread here, ONLY ONCE per connection
            Thread(target=queue_serial_data, args=[ser], daemon=True).start()
            return ser
        time.sleep(0.5)

def control():
    # ---------------- Initial variable values ----------------
    # Max power
    max_power = 20  # 20% start

    # # Prev button values
    prev_shoulder_up = False
    prev_shoulder_down = False
    prev_dpad = 0

    # ---------------- Init ----------------
    ## ---------------- Serial connection ----------------
    ser = None
    if not PRINT_MODE:
        ser = connect_arduino()

    ## ---------------- Controller connection ----------------
    # pygame.init()
    pygame.display.init()
    pygame.joystick.init()

    while True:
        print("Waiting for controller...")
        while pygame.joystick.get_count() < 1:
            pygame.event.pump() # Must pump to detect new devices
            time.sleep(0.5)

        joystick = pygame.joystick.Joystick(0)
        joystick.init()
        print(f"Connected to: {joystick.get_name()}")

        max_power = 20
        prev_shoulder_up = False
        prev_shoulder_down = False
        prev_dpad = 0

        while BTN_INDEX_DEMO_MODE:
            pygame.event.pump()

            axes = [joystick.get_axis(i) for i in range(joystick.get_numaxes())]
            buttons = [joystick.get_button(i) for i in range(joystick.get_numbuttons())]
            hats = [joystick.get_hat(i) for i in range(joystick.get_numhats())]
            print(f"Axes: {axes}  Buttons: {buttons}  Hats: {hats}", end='\r')

        try:
            timestamp = 0
            while True:
                while time.time_ns() - timestamp < 20e6:
                    time.sleep(0.001)

                timestamp = time.time_ns()
                # Handle events
                for event in pygame.event.get():
                    if event.type == pygame.JOYDEVICEREMOVED:
                        raise RuntimeError("Controller disconnected")

                # ----- Read controller -----
                leftStickX = joystick.get_axis(AXIS_L_STICK_X)
                rightStickY = joystick.get_axis(AXIS_R_STICK_Y)
                current_shoulder_up = joystick.get_button(BTN_SHOULDER_UP)
                current_shoulder_down = joystick.get_button(BTN_SHOULDER_DOWN)
                current_dpad = joystick.get_hat(0)[HAT_DPAD_Y]


                # ----- Process controller inputs -----
                # Change max power with d-pad buttons (steps of 10%)
                if current_shoulder_up and not prev_shoulder_up or current_dpad == 1 and prev_dpad != 1:
                    max_power += 10
                if current_shoulder_down and not prev_shoulder_down or current_dpad == -1 and prev_dpad != -1:
                    max_power -= 10

                prev_shoulder_up = current_shoulder_up
                prev_shoulder_down = current_shoulder_down
                prev_dpad = current_dpad

                # Clamp max power between 10% and 100%
                max_power = max(10, min(100, max_power))

                # Drive and steer signals, with max power applied, in percent
                drive = round(-rightStickY * max_power)
                steer = round(leftStickX * max_power)
                
                # Power for left and right motor (-100 to 100)
                powerLeft = max(-100, min(100, drive + steer))
                powerRight = max(-100, min(100, drive - steer))
                
                # Map -100..100 → 0..255
                pwmLeft = max(1, round((powerLeft + 100) * 255 / 200))
                pwmRight = max(1, round((powerRight + 100) * 255 / 200))

                # ----- Communicate results to the Arduino -----
                if PRINT_MODE:
                    print(
                        f"Drive: {drive:>4}%  Steer: {steer:>4}%  MaxPower: {int(max_power):>3}%  "
                        f"PowerL: {powerLeft:>4}%  PowerR: {powerRight:>4}%  "
                        f"PWML: {pwmLeft:>5.1f}  PWMR: {pwmRight:>5.1f}",
                        end="\r"
                    )
                elif ser is not None:
                    try:
                        ser.write(bytes([pwmLeft, pwmRight, 0]))
                    except serial.SerialException:
                        print("Lost connection to Arduino!")
                        ser.close()
                        ser = connect_arduino()
                
                # ----- Queue data to be sent to Grafana -----
                measurement_controller: dict[str, str | int | dict[str, float]] = {
                    "measurement": "controller",
                    "time": time.time_ns(),
                    "fields": {
                        "maxPower": max_power,
                        "drive": drive,
                        "steer": steer,
                        "powerLeft": powerLeft,
                        "powerRight": powerRight,
                        "pwmLeft": pwmLeft,
                        "pwmRight": pwmRight,
                    }
                }
                try:
                    measurement_queue.put_nowait(measurement_controller)
                except:
                    pass

                # time.sleep(0.02)
        except RuntimeError as e:
            print(e)
            joystick.quit()

def queue_serial_data(ser: serial.Serial):
    while True:
        try:
            raw_bytes = ser.read_until()
            if not raw_bytes:
                continue
                
            line = raw_bytes.decode('utf-8', errors='ignore').strip()
            parts = line.split()
            
            if len(parts) >= 4:
                print(line, end='\r')
                measurement_arduino: dict[str, str | int | dict[str, float]] = {
                    "measurement": "arduino",
                    "time": time.time_ns(),
                    "fields": {
                        "pwmLeft": float(parts[0]),
                        "pwmRight": float(parts[1]),
                    }
                }
                measurement_battery: dict[str, str | int | dict[str, float]] = {
                    "measurement": "battery",
                    "time": time.time_ns(),
                    "fields": {
                        "voltage": float(parts[2]),
                        "motor_1_current": float(parts[3]),
                        "motor_2_current": float(parts[4]),
                    }
                }
                measurement_queue.put_nowait(measurement_arduino)
                measurement_queue.put_nowait(measurement_battery)
                
        except (ValueError, IndexError):
            # Ignore malformed serial lines
            pass
        except serial.SerialException:
            # Stop the thread if the serial port closes
            break 
        except Full:
            # Ignore the measurement if the queue is full
            print("Warning: Full Queue")
            pass


if __name__ == '__main__': 
    control()