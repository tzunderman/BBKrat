#include <Arduino.h>

// Waves with dead time on Timer1 of an 
// Arduino UNO (Pins 9 and 10)
// Written January 23rd, 2023 by John Wasser

// frequency =  16MHz / (2 * prescaleFactor *  (TOP + 1))
// Correction, because Phase Correct PWM is used: 
// frequency =  16MHz / (2 * prescaleFactor *  TOP)
const unsigned TOP = 160;
// frequency =  16MHz / (2 * 1 *  160)
// frequency =  16MHz / 320
// frequency = 50,000

unsigned long timeout_millis = millis();
unsigned long timeout_python = 100;

void setup()
{
  Serial.begin(115200);
  delay(200);

  digitalWrite(6, LOW);
  digitalWrite(7, LOW);
  digitalWrite(11, LOW);
  digitalWrite(12, LOW);
  pinMode(6, OUTPUT);
  pinMode(7, OUTPUT);
  pinMode(11, OUTPUT);
  pinMode(12, OUTPUT);

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
}

void loop() {
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
    Serial.print(((float) TOP * (float) buf[0] / 255.0));
    Serial.print(" ");
    Serial.println(((float) TOP * (float) buf[1] / 255.0));

    // Reset the timeout
    timeout_millis = millis();
  }

  // Disable the timers if no message has been received for timeout_python milliseconds
  if (millis() - timeout_millis > timeout_python) {
    TCCR1B &= ~_BV(CS10);
    TCCR4B &= ~_BV(CS40);
  }
  else {
    // Start timer by setting the clock-select bits to non-zero (prescale = 1)
    TCCR1B |= _BV(CS10);
    TCCR4B |= _BV(CS40);
  }
}