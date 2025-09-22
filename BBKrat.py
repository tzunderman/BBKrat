import time
import pygame
import serial
import serial.tools.list_ports as stlp

# ---------------- Constants ----------------

# Axes
AXIS_L_STICK_X = 0
AXIS_L_STICK_Y = 1
AXIS_R_STICK_X = 3
AXIS_R_STICK_Y = 4

# # Shoulder buttons
BTN_SHOULDER_UP = 5
BTN_SHOULDER_DOWN = 4
# # D-pad buttons
HAT_DPAD_Y = 1


#Demo mode to see which button index of the controller is what.
BTN_INDEX_DEMO_MODE = False
# Print mode to print data in the terminal instead of sending it to an Arduino
PRINT_MODE = False
# ---------------- Initial variable values ----------------

# Max power
max_power = 20  # 20% start

# # Prev button values
prev_shoulder_up = False
prev_shoulder_down = False
prev_dpad = 0

# ---------------- Init ----------------
pygame.init()
pygame.joystick.init()

if pygame.joystick.get_count() == 0:
    print("No controller detected.")
    exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()
print(f"Connected to: {joystick.get_name()}")


while BTN_INDEX_DEMO_MODE:
    pygame.event.pump()

    axes = [joystick.get_axis(i) for i in range(joystick.get_numaxes())]
    buttons = [joystick.get_button(i) for i in range(joystick.get_numbuttons())]
    hats = [joystick.get_hat(i) for i in range(joystick.get_numhats())]
    print(f"Axes: {axes}  Buttons: {buttons}  Hats: {hats}", end='\r') 

# ---------------- Serial connection ----------------
ser: serial.Serial | None = None
if not PRINT_MODE:
    connected_arduinos = [port.device for port in stlp.comports() if not port.manufacturer is None and "Arduino" in port.manufacturer]
    if len(connected_arduinos) == 0:
        print("No Arduino connected")
        exit()
        
    port = connected_arduinos[0]
    # print(port)
    ser = serial.Serial(port, 115200)
    # For some reason there needs to be a delay in order for the Arduino to be
    # ready to receive messages 
    time.sleep(1)

# ---------------- Main Loop ----------------
try:
    while True:
        pygame.event.pump()

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

        # ----- Communicate results to the Arduino 
        if PRINT_MODE:
            print(
                f"Drive: {drive:>4}%  Steer: {steer:>4}%  MaxPower: {int(max_power):>3}%  "
                f"PowerL: {powerLeft:>4}%  PowerR: {powerRight:>4}%  "
                f"PWML: {pwmLeft:>5.1f}  PWMR: {pwmRight:>5.1f}",
                end="\r"
            )
        elif ser is not None:
            buf = [pwmLeft, pwmRight, 0]
            ser.write(bytes(buf))
            b = ser.read_until()
            if b != b"":
                print(b, end='\r')

            # Small delay to prevent too much spamming on the serial connection
            time.sleep(0.02)
except Exception as e:
    print(e)

if not PRINT_MODE and ser is not None:
    # Make sure to properly close the connection
    ser.close()
