from __future__ import annotations

import time
import pygame
import serial
import serial.tools.list_ports as stlp
from queue import Full
from threading import Thread
from multiprocessing import Queue
from typing import TypeVar, Literal
from RPi import GPIO

T = TypeVar('T')
def clamp(x: T, lo: T, hi: T) -> T:
    return max(lo, min(x, hi))

# ---------------- Constants -----------------

# Relay pins
RELAY_1_PIN = 37
RELAY_2_PIN = 35
RELAY_3_PIN = 33
RELAY_4_PIN = 31

# Axes
AXIS_L_STICK_X = 0
AXIS_L_STICK_Y = 1
AXIS_R_STICK_X = 3
AXIS_R_STICK_Y = 4

# Shoulder buttons
BTN_SHOULDER_UP = 5
BTN_SHOULDER_DOWN = 4

# D-pad buttons
HAT_DPAD_X = 0
HAT_DPAD_Y = 1
BTN_RIGHT = 1

# Demo mode to see which button index of the controller is what.
BTN_INDEX_DEMO_MODE = False

# Print mode to print data in the terminal instead of sending it to an Arduino
PRINT_MODE = False


# Controller interval (s)
DT = 0.02

# Time (s) to ramp power from 0 to 100 (full forward)
POWER_RAMP_TIME = 1.0

# Maximum slew rate of power command (%/s), derived from ramp time
POWER_SLEWRATE = 100.0 / POWER_RAMP_TIME

# Power (0 to 100) defined as deadzone, in which motor does not move.
DEADZONE_POWER_LEFT = 5
DEADZONE_POWER_RIGHT = 5

# Power (0 to 100) defined as off, values below this will be set to 0 output
OFF_POWER_LEFT = 1
OFF_POWER_RIGHT = 1



R_WINDING   = 0.2   #ohm, winding resistance


# Stall current clamping settings
I_PEAK      = 20.0  #A, limit where clamping starts immediately
I_MAX_LIM   = 12.0  #A, limit where clamping starts after I_MAX_TIME
I_MAX_TIME  = 0.50  #s, amount of time to allow exceeding I_MAX_LIM before clamping
I_CLAMP     = 10.0  #A, current to clamp to
I_UNCLAMP   = 6.0   #A, current to stop clamping at


# Data from arduino
data_received = False #Indicates if at least one data point has been received
Vbat = 0.0 #V
Ileft = 0.0 #A
Iright = 0.0 #A

# Stall clamping state variables
last_valid_I_t_left = -1.0 #s, timestamp when left motor had valid current last time
last_valid_I_t_right = -1.0 #s, timestamp when left motor had valid current last time

clamping_left = False
clamping_right = False
clamp_dir_left = 0
clamp_dir_right = 0

# Controller rumble state
rumbling = False



def connect_arduino(measurement_queue: Queue[dict[str, str | int | dict[str, float]]]) -> serial.Serial:
    print("Try to connect to an Arduino")
    while True:
        arduinos = [port.device for port in stlp.comports() if port.manufacturer and "Arduino" in port.manufacturer]
        if arduinos:
            ser = serial.Serial(arduinos[0], 115200)
            print("Connected to an Arduino")
            time.sleep(1) # Wait for Arduino reboot
            
            # Start reader thread here, ONLY ONCE per connection
            Thread(target=queue_serial_data, args=[ser, measurement_queue], daemon=True).start()

            print("Waiting for data...")
            while not data_received:
                time.sleep(0.5)

            print("Data reception confirmed.")
            return ser

        time.sleep(0.5)


def applyStallCurrentClamping(powerLeft: int, powerRight: int) -> tuple[int, int]:

    global last_valid_I_t_left, last_valid_I_t_right, clamping_left, clamping_right, clamp_dir_left, clamp_dir_right


    U_CLAMP = R_WINDING * I_CLAMP
    powerClamp = (U_CLAMP / Vbat)*100
    powerClamp = clamp(powerClamp, 0, 100)


    t_now = time.monotonic()


    if last_valid_I_t_left < 0 or abs(Ileft) <= I_MAX_LIM:
        last_valid_I_t_left = t_now

    if last_valid_I_t_right < 0 or abs(Iright) <= I_MAX_LIM:
        last_valid_I_t_right = t_now


    t_exceed_left = t_now - last_valid_I_t_left
    t_exceed_right = t_now - last_valid_I_t_right


    if abs(Ileft) > I_PEAK or t_exceed_left > I_MAX_TIME:
        clamping_left = True
        clamp_dir_left = int(powerLeft / abs(powerLeft))

    if abs(Iright) > I_PEAK or t_exceed_right > I_MAX_TIME:
        clamping_right = True
        clamp_dir_right = int(powerRight / abs(powerRight))



    # Clamp exit conditions: commanded power lower than clamp power,
    # or measured current lower than I_UNCLAMP

    if abs(powerLeft) <= powerClamp or abs(Ileft) < I_UNCLAMP:
        clamping_left = False

    if abs(powerRight) <= powerClamp or abs(Iright) < I_UNCLAMP:
        clamping_right = False


    powerLeftOut = powerLeft
    if clamping_left:
        powerLeftOut = powerClamp * clamp_dir_left

    powerRightOut = powerRight
    if clamping_right:
        powerRightOut = powerClamp * clamp_dir_right


    return int(powerLeftOut), int(powerRightOut)


def set_rumble(joystick: pygame.joystick.JoystickType, shouldRumble: bool) -> None:

    global rumbling

    if shouldRumble and not rumbling:
        rumbling = joystick.rumble(1.0, 1.0, 300000)
        if not rumbling:
            print("Rumbling failed")

    if rumbling and not shouldRumble:
        joystick.stop_rumble()
        rumbling = False


def control(measurement_queue: Queue[dict[str, str | int | dict[str, float]]]):

    ## Init controller libs
    # pygame.init()
    pygame.display.init()
    pygame.joystick.init()

    while True:

        ## Init GPIO
        # This needs to be called before pins can be set. Also after GPIO.cleanup()
        GPIO.setmode(GPIO.BOARD)

        relay_pins: list[tuple[int, Literal[0, 1]]] = [(RELAY_1_PIN, GPIO.HIGH), (RELAY_2_PIN, GPIO.HIGH), (RELAY_3_PIN, GPIO.HIGH), (RELAY_4_PIN, GPIO.HIGH)]
        for pin, level in relay_pins:
            GPIO.setup(pin, GPIO.OUT, initial=level)

        motor_on = False


        ## Init serial
        ser = None
        if not PRINT_MODE:
            ser = connect_arduino(measurement_queue)

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
        prev_dpad_left = 0
        prev_button_right = False
        dpad_left_rising = False
        button_right_rising = False

        # Commanded, slew-rated power per motor (from -100 to +100)
        powerLeft = 0
        powerRight = 0

        while BTN_INDEX_DEMO_MODE:
            pygame.event.pump()

            axes = [joystick.get_axis(i) for i in range(joystick.get_numaxes())]
            buttons = [joystick.get_button(i) for i in range(joystick.get_numbuttons())]
            hats = [joystick.get_hat(i) for i in range(joystick.get_numhats())]
            print(f"Axes: {axes}  Buttons: {buttons}  Hats: {hats}", end='\r')


        # Startup rumble
        set_rumble(joystick, True)
        time.sleep(0.2)
        set_rumble(joystick, False)

        # Start main loop (in catchall block)
        next_control_time = time.monotonic()
        try:
            while True:
                next_control_time += DT
                now = time.monotonic()
                if next_control_time > now:
                    time.sleep(next_control_time - now)
                else:
                    # Loop fell behind schedule; catch up
                    next_control_time = now

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
                current_dpad_left = joystick.get_hat(0)[HAT_DPAD_X]
                current_button_right = joystick.get_button(BTN_RIGHT)


                # ----- Process controller inputs -----
                # Change max power with d-pad buttons (steps of 10%)
                if current_shoulder_up and not prev_shoulder_up or current_dpad == 1 and prev_dpad != 1:
                    max_power += 10
                if current_shoulder_down and not prev_shoulder_down or current_dpad == -1 and prev_dpad != -1:
                    max_power -= 10
                if current_dpad_left == -1 and prev_dpad_left != -1:
                    dpad_left_rising = True
                elif current_dpad_left != -1:
                    dpad_left_rising = False
                if current_button_right and not prev_button_right:
                    button_right_rising = True
                elif not current_button_right:
                    button_right_rising = False

                if dpad_left_rising and button_right_rising:
                    dpad_left_rising = False
                    button_right_rising = False
                    motor_on = not motor_on
                    
                    motor_relay_pin = relay_pins[3]
                    if motor_on:
                        GPIO.output(motor_relay_pin[0], not bool(motor_relay_pin[1]))
                    else:
                        GPIO.output(motor_relay_pin[0], bool(motor_relay_pin[1]))

                prev_shoulder_up = current_shoulder_up
                prev_shoulder_down = current_shoulder_down
                prev_dpad = current_dpad
                prev_dpad_left = current_dpad_left
                prev_button_right = current_button_right

                # Clamp max power between 10% and 100%
                max_power = clamp(max_power, 10, 100)
                max_steer_power = clamp(0.5*max_power, 10, 100)

                # Drive and steer signals, with max power applied, in percent
                drive = round(-rightStickY * max_power)
                steer = round(leftStickX * max_steer_power)
                
                # Power for left and right motor (-100 to 100)
                powerLeftReq = round(clamp(drive + steer, -100, 100))
                powerRightReq = round(clamp(drive - steer, -100, 100))

                # Apply a power slew rate, to gently ramp up when accelerating
                # (Prevents broken wheel parts when quickly accelerating)
                maxPowerInc = round(POWER_SLEWRATE * DT)
                powerLeft += round(clamp(powerLeftReq - powerLeft, -maxPowerInc, maxPowerInc))
                powerRight += round(clamp(powerRightReq - powerRight, -maxPowerInc, maxPowerInc))


                # Deadzone removal logic. If we are in the range of +-5% power, the motor does not start moving.
                # If we are in the deadzone, set value to +5%, 0%, or -5% based on the powerReq value.

                if abs(powerLeft) < DEADZONE_POWER_LEFT:
                    if abs(powerLeftReq) < OFF_POWER_LEFT:
                        powerLeft = 0
                    elif powerLeftReq >= OFF_POWER_LEFT:
                        powerLeft = +DEADZONE_POWER_LEFT
                    elif powerLeftReq <= -OFF_POWER_LEFT:
                        powerLeft = -DEADZONE_POWER_LEFT

                if abs(powerRight) < DEADZONE_POWER_RIGHT:
                    if abs(powerRightReq) < OFF_POWER_RIGHT:
                        powerRight = 0
                    elif powerRightReq >= OFF_POWER_RIGHT:
                        powerRight = +DEADZONE_POWER_RIGHT
                    elif powerRightReq <= -OFF_POWER_RIGHT:
                        powerRight = -DEADZONE_POWER_RIGHT


                # Apply overcurrent clamping logic
                powerLeft, powerRight = applyStallCurrentClamping(powerLeft, powerRight)

                # Map -100..100 → 1..255
                pwmLeft = max(1, round((powerLeft + 100) * 255 / 200))
                pwmRight = max(1, round((powerRight + 100) * 255 / 200))

                # Final clamp to be safe
                pwmLeft = clamp(pwmLeft, 1, 255)
                pwmRight = clamp(pwmRight, 1, 255)

                # ----- Communicate results to the Arduino -----
                if PRINT_MODE:
                    print(
                        f"Drive: {drive:>4}%  Steer: {steer:>4}%  MaxPower: {int(max_power):>3}%  "
                        f"PowerReqL: {powerLeftReq:>4}%  PowerReqR: {powerRightReq:>4}%  "
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
                        break

                # Rumble controller if clamping
                rumble = clamping_left or clamping_right
                set_rumble(joystick, rumble)

                
                # ----- Queue data to be sent to Grafana -----
                measurement_controller: dict[str, str | int | dict[str, float]] = {
                    "measurement": "controller",
                    "time": time.time_ns(),
                    "fields": {
                        "maxPower": max_power,
                        "drive": drive,
                        "steer": steer,
                        "powerLeftRequest": powerLeftReq,
                        "powerRightRequest": powerRightReq,
                        "powerLeft": powerLeft,
                        "powerRight": powerRight,
                        "pwmLeft": pwmLeft,
                        "pwmRight": pwmRight,
                        "clampingLeft": clamping_left,
                        "clampingRight": clamping_right,
                        "motorRelayOn": motor_on,
                    }
                }
                try:
                    measurement_queue.put_nowait(measurement_controller)
                except Full:
                    # TODO log message?
                    pass

        except RuntimeError as e:
            print(e)
            joystick.quit()
            if ser is not None:
                ser.close()

        for pin, level in relay_pins:
            GPIO.output(pin, level)
        GPIO.cleanup()

def queue_serial_data(ser: serial.Serial, measurement_queue: Queue[dict[str, str | int | dict[str, float]]]):
    last_error_queue = None

    global Vbat, Ileft, Iright, data_received

    while True:
        try:
            raw_bytes = ser.read_until()
            if not raw_bytes:
                continue
                
            line = raw_bytes.decode('utf-8', errors='ignore').strip()
            parts = line.split()
            
            if len(parts) >= 6:
                # print(line, end='\r')
                Vbat = float(parts[2])
                Ileft = float(parts[3]) # Left = motor 1 in arduino code
                Iright = float(parts[4])  # Right  motor 2 in arduino code
                data_received = True
                
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
                        "voltage": Vbat,
                        "motor_1_current": Ileft,
                        "motor_2_current": Iright,
                        "vref": float(parts[5])
                    }
                }
                measurement_queue.put_nowait(measurement_arduino)
                measurement_queue.put_nowait(measurement_battery)
                last_error_queue = None
                
        except (ValueError, IndexError):
            # Ignore malformed serial lines
            pass
        except serial.SerialException:
            # Stop the thread if the serial port closes
            break 
        except Full:
            # Ignore the measurement if the queue is full
            now = time.monotonic()
            if last_error_queue is None or (now - last_error_queue) > 2:
                print("Warning: Full Queue")
                last_error_queue = now


if __name__ == '__main__':
    control(Queue(maxsize=2048))
