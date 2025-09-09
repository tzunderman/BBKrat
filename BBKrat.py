import pygame

# ---------------- Constants ----------------

# Axes
AXIS_L_STICK_X = 0
AXIS_L_STICK_Y = 1
AXIS_R_STICK_X = 2
AXIS_R_STICK_Y = 3

# D-pad buttons
BTN_DPAD_UP = 11
BTN_DPAD_DOWN = 12


#Demo mode to see which button index of the controller is what.
BTN_INDEX_DEMO_MODE = False

# ---------------- Initial variable values ----------------

# Max power
max_power = 20  # 20% start

# Prev button values
prev_dpad_up = False
prev_dpad_down = False

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
    axes = [joystick.get_axis(i) for i in range(joystick.get_numaxes())]
    buttons = [joystick.get_button(i) for i in range(joystick.get_numbuttons())]
    hats = [joystick.get_hat(i) for i in range(joystick.get_numhats())]
    print(f"Axes: {axes}  Buttons: {buttons}  Hats: {hats}") 
           

# ---------------- Main Loop ----------------
while True:
    pygame.event.pump()

    # ----- Read controller -----
    leftStickX = joystick.get_axis(AXIS_L_STICK_X)
    rightStickY = joystick.get_axis(AXIS_R_STICK_Y)
    current_dpad_up = joystick.get_button(BTN_DPAD_UP)
    current_dpad_down = joystick.get_button(BTN_DPAD_DOWN)



    # ----- Process controller inputs -----
    
    # Change max power with d-pad buttons (steps of 10%)
    if current_dpad_up and not prev_dpad_up:
        max_power += 10
    if current_dpad_down and not prev_dpad_down:
        max_power -= 10

    prev_dpad_up = current_dpad_up
    prev_dpad_down = current_dpad_down

    # Clamp max power between 10% and 100%
    max_power = max(10, min(100, max_power))

    # Drive and steer signals, with max power applied, in percent
    drive = round(-rightStickY * max_power)
    steer = round(leftStickX * max_power)
    
    # Power for left and right motor (-100 to 100)
    powerLeft = max(-100, min(100, drive + steer))
    powerRight = max(-100, min(100, drive - steer))
    
    # Map -100..100 → 0..255
    pwmLeft = round((powerLeft + 100) * 255 / 200)
    pwmRight = round((powerRight + 100) * 255 / 200)

    #TODO: write to arduino here. For now just print.
    print(
        f"Drive: {drive:>4}%  Steer: {steer:>4}%  MaxPower: {int(max_power):>3}%  "
        f"PowerL: {powerLeft:>4}%  PowerR: {powerRight:>4}%  "
        f"PWML: {pwmLeft:>5.1f}  PWMR: {pwmRight:>5.1f}",
        end="\r"
    )
