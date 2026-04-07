import RPi.GPIO as GPIO
import time
import RPi.GPIO as GPIO
import time

# --- PIN CONFIGURATION ---
PUL, DIR = 17, 27
RPWM, LPWM, R_EN, L_EN = 18, 19, 23, 24

# --- SETUP ---
GPIO.setmode(GPIO.BCM)
GPIO.setup([PUL, DIR, RPWM, LPWM, R_EN, L_EN], GPIO.OUT)
GPIO.output([R_EN, L_EN], GPIO.HIGH)

actuator_extend = GPIO.PWM(RPWM, 1000)
actuator_retract = GPIO.PWM(LPWM, 1000)
actuator_extend.start(0)
actuator_retract.start(0)

# Track the "Odometer"
current_step_pos = 0

def move_to_angle(target_steps, speed=0.001):
    global current_step_pos
    
    # Calculate how many steps we need to move from beginning
    steps_to_move = target_steps - current_step_pos
    
    if steps_to_move == 0:
        return

    # Determine direction
    direction = 1 if steps_to_move > 0 else 0
    GPIO.output(DIR, direction)
    
    print(f"Moving to target... ({'CW' if direction==1 else 'CCW'})")
    for _ in range(abs(steps_to_move)):
        GPIO.output(PUL, GPIO.HIGH)
        time.sleep(speed)
        GPIO.output(PUL, GPIO.LOW)
        time.sleep(speed)
    
    current_step_pos = target_steps

def run_actuator(seconds=5):
    print(">>> Actuating: Extending...")
    actuator_extend.ChangeDutyCycle(100)
    time.sleep(seconds)
    actuator_extend.ChangeDutyCycle(0)
    
    time.sleep(2)
    
    print(">>> Actuating: Retracting...")
    actuator_retract.ChangeDutyCycle(100)
    time.sleep(seconds)
    actuator_retract.ChangeDutyCycle(0)

# --- MAIN SORTING SEQUENCE ---
try:
    # Definitions (Assuming 400 steps/rev)
    TRASH = 0
    COMPOST = 100
    RECYCLE = 200

    # 1. TRASH PHASE
    print("\n[STEP 1: TRASH]")
    move_to_angle(TRASH)
    run_actuator()

    # 2. COMPOST PHASE
    print("\n[STEP 2: COMPOST]")
    move_to_angle(COMPOST)
    time.sleep(1)
    run_actuator()

    # 3. RECYCLE PHASE
    print("\n[STEP 3: RECYCLE]")
    move_to_angle(RECYCLE)
    time.sleep(1)
    run_actuator()

    # 4. HOME PHASE
    print("\n[FINISHING: Returning to TRASH position]")
    time.sleep(1)
    move_to_angle(TRASH)

finally:
    print("\nSystem Halted. Cleaning up GPIO...")
    actuator_extend.stop()
    actuator_retract.stop()
    GPIO.cleanup()
    print("Done.")


