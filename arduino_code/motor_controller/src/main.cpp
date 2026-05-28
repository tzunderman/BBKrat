#include <Arduino.h>
#include "battery.h"

// Analog pin config for battery voltage measurement
#define BATTERY_VOLTAGE_PIN A8
#define MOTOR_1_CURRENT_PIN A13
#define MOTOR_2_CURRENT_PIN A15

#define MOTOR_1_PWM_1_PIN 10
#define MOTOR_1_PWM_2_PIN 9
#define MOTOR_1_PWM_ENABLE_PIN 8
#define MOTOR_2_PWM_1_PIN 4
#define MOTOR_2_PWM_2_PIN 3
#define MOTOR_2_PWM_ENABLE_PIN 2

// frequency =  16MHz / (2 * prescaleFactor *  (TOP + 1))
// Correction, because Phase Correct PWM is used: 
// frequency =  16MHz / (2 * prescaleFactor *  TOP)
const unsigned TOP = 160;
// frequency =  16MHz / (2 * 1 *  160)
// frequency =  16MHz / 320
// frequency = 50,000

unsigned long timeout_millis = millis();
unsigned long timeout_python = 100;
unsigned long battery_status_period = 100;
unsigned long last_battery_status = millis();
unsigned long battery_status_message_period = 1000;
unsigned long last_battery_status_message = millis();
float battery_voltage = 0;
float motor_1_current = 0;
float motor_2_current = 0;

void setup()
{
  Serial.begin(115200);
  delay(200);

  digitalWrite(MOTOR_1_PWM_1_PIN, LOW);
  digitalWrite(MOTOR_1_PWM_2_PIN, LOW);
  digitalWrite(MOTOR_1_PWM_ENABLE_PIN, HIGH);
  digitalWrite(MOTOR_2_PWM_1_PIN, LOW);
  digitalWrite(MOTOR_2_PWM_2_PIN, LOW);
  digitalWrite(MOTOR_2_PWM_ENABLE_PIN, HIGH);
  pinMode(MOTOR_1_PWM_1_PIN, OUTPUT);
  pinMode(MOTOR_1_PWM_2_PIN, OUTPUT);
  pinMode(MOTOR_1_PWM_ENABLE_PIN, OUTPUT);
  pinMode(MOTOR_2_PWM_1_PIN, OUTPUT);
  pinMode(MOTOR_2_PWM_2_PIN, OUTPUT);
  pinMode(MOTOR_2_PWM_ENABLE_PIN, OUTPUT);
  digitalWrite(MOTOR_1_PWM_ENABLE_PIN, HIGH);
  digitalWrite(MOTOR_2_PWM_ENABLE_PIN, HIGH);

  // Stop the Timer/Counter by resetting the control registers
  TCCR1A = 0;
  TCCR1B = 0;
  TCCR4A = 0;
  TCCR4B = 0;
  // Timer/Counter Interrupt Mask Register
  TIMSK1 = 0;
  TIMSK4 = 0;

  // Set Timer/Counter to Waveform Generation Mode 8:
  // Phase and Frequency correct PWM with TOP set by ICR1
  TCCR1B |= _BV(WGM13);  // WGM=8
  TCCR1A |= _BV(COM1A1);  // Normal PWM on Pin 11
  TCCR1A |= _BV(COM1B1) | _BV(COM1B0); // Inverted PWM on Pin 12
  TCCR4B |= _BV(WGM43);  // WGM=8
  TCCR4A |= _BV(COM4A1);  // Normal PWM on Pin 6
  TCCR4A |= _BV(COM4B1) | _BV(COM4B0); // Inverted PWM on Pin 7

  // Maximal count value
  ICR1 = TOP;
  ICR4 = TOP;

  // Trigger points (should be between 0 and TOP)
  OCR1A = (TOP / 2);
  OCR1B = (TOP / 2);
  OCR4A = (TOP / 2);
  OCR4B = (TOP / 2);

  battery_voltage = read_voltage(BATTERY_VOLTAGE_PIN);
  motor_1_current = read_current(MOTOR_1_CURRENT_PIN);
  motor_2_current = read_current(MOTOR_2_CURRENT_PIN);
}

void send_data(float pwmL, float pwmR, float battery_voltage, float motor_1_current, float motor_2_current) {
    Serial.print(pwmL);
    Serial.print(" ");
    Serial.print(pwmR);
    Serial.print(" ");
    Serial.print(battery_voltage);
    Serial.print(" ");
    Serial.print(motor_1_current);
    Serial.print(" ");
    Serial.println(motor_2_current);
}

void loop() {
  // Get the voltage of the battery by reading the analog pin and calculating the total voltage
  if (millis() - last_battery_status > battery_status_period) {
    battery_voltage = read_voltage(BATTERY_VOLTAGE_PIN);
    motor_1_current = read_current(MOTOR_1_CURRENT_PIN);
    motor_2_current = read_current(MOTOR_2_CURRENT_PIN);
    last_battery_status = millis();
  }

  // Only read if there are three or more bytes to be read (complete message)
  // Wait for the other bytes to arrive if not the case
  while (Serial.available() >= 3) {
    // Read until the message delimiter
    uint8_t buf[4];
    uint8_t number_of_bytes = Serial.readBytesUntil(0, buf, 4);

    // Ignore the message if it contains more than three bytes
    if (number_of_bytes != 2) {
      break;
    }

    // Calculate the new count values for the received duty cycles
    OCR1A = (uint16_t) ((float) TOP * (float) buf[0] / 255.0);
    OCR1B = (uint16_t) ((float) TOP * (float) buf[0] / 255.0);
    OCR4A = (uint16_t) ((float) TOP * (float) buf[1] / 255.0);
    OCR4B = (uint16_t) ((float) TOP * (float) buf[1] / 255.0);
    
    // Send the calculated values back to the pi
    send_data(((float) TOP * (float) buf[0] / 255.0), ((float) TOP * (float) buf[1] / 255.0), battery_voltage, motor_1_current, motor_2_current);

    // Reset the timeout
    timeout_millis = millis();
    last_battery_status_message = timeout_millis;
  }
  
  if (millis() - last_battery_status_message > battery_status_message_period) {
    send_data(-1, -1, battery_voltage, motor_1_current, motor_2_current);
    last_battery_status_message = millis();
  }

  // Disable the timers if no message has been received for timeout_python milliseconds
  if (millis() - timeout_millis > timeout_python) {
    TCCR1B &= ~_BV(CS10);
    TCCR4B &= ~_BV(CS40);
    digitalWrite(MOTOR_1_PWM_ENABLE_PIN, HIGH);
    digitalWrite(MOTOR_2_PWM_ENABLE_PIN, HIGH);
  }
  else {
    // Start timer by setting the clock-select bits to non-zero (prescale = 1)
    TCCR1B |= _BV(CS10);
    TCCR4B |= _BV(CS40);
    digitalWrite(MOTOR_1_PWM_ENABLE_PIN, LOW);
    digitalWrite(MOTOR_2_PWM_ENABLE_PIN, LOW);
  }
}