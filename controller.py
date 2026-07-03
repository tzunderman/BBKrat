import time
import pygame
import serial
import serial.tools.list_ports as stlp
from queue import Queue, Full
from threading import Thread

def clamp(x, lo, hi):
    return max(lo, min(x, hi))

# ---------------- Constants -----------------

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


# Controller interval (s)
DT = 0.02

# Time (s) to ramp power from 0 to 100 (full forward)
POWER_RAMP_TIME = 2.0

# Maximum slew rate of power command (%/s), derived from ramp time
POWER_SLEWRATE = 100.0 / POWER_RAMP_TIME

R_WINDING   = 0.2   #ohm, winding resistance


# Stall current clamping settings
I_PEAK      = 60.0  #A, limit where clamping starts immediately
I_MAX_LIM   = 15.0  #A, limit where clamping starts after I_MAX_TIME
I_MAX_TIME  = 0.50  #s, amount of time to allow exceeding I_MAX_LIM before clamping
I_CLAMP     = 14.0  #A, current to clamp to
I_UNCLAMP   = 10.0  #A, current to stop clamping at






measurement_queue: Queue[dict[str, str | int | dict[str, float]]] = Queue(maxsize=256)


#Data from arduino
data_received = False #Indicates if at least one data point has been received
Vbat = 0.0 #V
Ileft = 0.0 #A
Iright = 0.0 #A

# Stall clamping state variables
last_valid_I_t_left = -1.0 #s, timestamp when left motor had valid current last time
last_valid_I_t_right = -1.0 #s, timestamp when left motor had valid current last time

clamping_left = False
clamping_right = False
clamp_dir_left = 0.0
clamp_dir_right = 0.0

# Controller rumble state
rumbling = False



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

        while not data_received:
            print("Waiting for data...")
            time.sleep(0.5)

        print("Data reception confirmed.")

def applyStallCurrentClamping(powerLeft, powerRight):

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


    if clamping_left:
        powerLeft = powerClamp * clamp_dir_left

    if clamping_right:
        powerRight = powerClamp * clamp_dir_right


    return powerLeft, powerRight


def set_rumble(joystick, shouldRumble):

    global rumbling

    if shouldRumble and not rumbling:
        rumbling = joystick.rumble(1.0, 1.0, 300000)
        if not rumbling:
            print("Rumbling failed")

    if rumbling and not shouldRumble:
        joystick.stop_rumble()
        rumbling = False

def control():

    ## Init controller libs
    # pygame.init()
    pygame.display.init()
    pygame.joystick.init()

    while True:

        ## Init serial
        ser = None
        if not PRINT_MODE:
            ser = connect_arduino()

        print("Waiting for controller...")
        while pygame.joystick.get_count() < 1:
            pygame.event.pump() # Must pump to detect new devices
            time.sleep(0.5)

        joystick = pygame.joystick.Joystick(0)
        joystick.init()
        print(f"Connected to: {joystick.get_name()}")
        rumbling = False

        max_power = 20
        prev_shoulder_up = False
        prev_shoulder_down = False
        prev_dpad = 0

        #Commanded, slew-rated power per motor (from -100 to +100)
        powerLeft = 0
        powerRight = 0

        while BTN_INDEX_DEMO_MODE:
            pygame.event.pump()

            axes = [joystick.get_axis(i) for i in range(joystick.get_numaxes())]
            buttons = [joystick.get_button(i) for i in range(joystick.get_numbuttons())]
            hats = [joystick.get_hat(i) for i in range(joystick.get_numhats())]
            print(f"Axes: {axes}  Buttons: {buttons}  Hats: {hats}", end='\r')


        #Startup rumble
        set_rumble(joystick, True)
        time.sleep(0.2)
        set_rumble(joystick, False)

        #Start main loop (in catchall block)
        try:
            timestamp = 0.0
            while True:
                while time.monotonic() - timestamp < DT:
                    # 1us sleep
                    time.sleep(0.001)

                timestamp = time.monotonic()
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
                max_power = clamp(max_power, 10, 100)

                # Drive and steer signals, with max power applied, in percent
                drive = round(-rightStickY * max_power)
                steer = round(leftStickX * max_power)
                
                # Power for left and right motor (-100 to 100)
                powerLeftReq = clamp(drive + steer, -100, 100)
                powerRightReq = clamp(drive - steer, -100, 100)

                # Apply a power slew rate, to gently ramp up when accelerating
                # (Prevents broken wheel parts when quickly accelerating)
                maxPowerInc = round(POWER_SLEWRATE * DT)
                powerLeft += clamp(powerLeftReq - powerLeft, -maxPowerInc, maxPowerInc)
                powerRight += clamp(powerRightReq - powerRight, -maxPowerInc, maxPowerInc)

                #Apply overcurrent clamping logic
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

                #Rumble controller if clamping
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
                    }
                }
                try:
                    measurement_queue.put_nowait(measurement_controller)
                except:
                    pass

        except RuntimeError as e:
            print(e)
            joystick.quit()
            ser.close()

def queue_serial_data(ser: serial.Serial):
    last_error_queue = None

    global Vbat, I_m1, I_m2, data_received

    while True:
        try:
            raw_bytes = ser.read_until()
            if not raw_bytes:
                continue
                
            line = raw_bytes.decode('utf-8', errors='ignore').strip()
            parts = line.split()

            Vbat = float(parts[2])
            I_m1 = float(parts[3])
            I_m2 = float(parts[4])
            data_received = True
            
            if len(parts) >= 4:
                # print(line, end='\r')
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
                        "motor_1_current": I_m1,
                        "motor_2_current": I_m2,
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
    control()