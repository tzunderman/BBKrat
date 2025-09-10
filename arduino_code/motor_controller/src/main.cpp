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

  // Stop Timer/Counter1
  TCCR1A = 0;  // Timer/Counter1 Control Register A
  TCCR1B = 0;  // Timer/Counter1 Control Register B
  TIMSK1 = 0;  // Timer/Counter1 Interrupt Mask Register
  // Stop Timer/Counter4
  TCCR4A = 0;  // Timer/Counter4 Control Register A
  TCCR4B = 0;  // Timer/Counter4 Control Register B
  TIMSK4 = 0;  // Timer/Counter4 Interrupt Mask Register

  // Set Timer/Counter1 to Waveform Generation Mode 8:
  // Phase and Frequency correct PWM with TOP set by ICR1
  TCCR1B |= _BV(WGM13);  // WGM=8
  TCCR1A |= _BV(COM1A1);  // Normal PWM on Pin 11
  TCCR1A |= _BV(COM1B1) | _BV(COM1B0); // Inverted PWM on Pin 12
  TCCR4B |= _BV(WGM43);  // WGM=8
  TCCR4A |= _BV(COM4A1);  // Normal PWM on Pin 6
  TCCR4A |= _BV(COM4B1) | _BV(COM4B0); // Inverted PWM on Pin 7

  ICR1 = TOP;
  ICR4 = TOP;
  // Difference between OCR1A and OCR1B is Dead Time
  OCR1A = (TOP / 2) - 1;
  OCR1B = (TOP / 2) + 1;
  OCR4A = (TOP / 2) - 1;
  OCR4B = (TOP / 2) + 1;

  // Start timer by setting the clock-select bits to non-zero
  // TODO uncomment the following lines to start them
  TCCR1B |= _BV(CS10); // prescale = 1
  TCCR4B |= _BV(CS40); // prescale = 1
}

void loop() {
  // Only read if there are three or more bytes to be read (complete message)
  // Wait for the other bytes to arrive if not the case
  while (Serial.available() >= 3) {
    // Read until the message delimiter
    String line = Serial.readStringUntil('\n');
    // Ignore the message if it contains more than three bytes
    if (line.length() != 3) {
      break;
    }

    // Calculate the new count values for the received duty cycles
    OCR1A = (uint16_t) ((float) TOP * (float) line[0] / 100.0) - 1;
    OCR1B = (uint16_t) ((float) TOP * (float) line[0] / 100.0) + 1;
    OCR4A = (uint16_t) ((float) TOP * (float) line[1] / 100.0) - 1;
    OCR4B = (uint16_t) ((float) TOP * (float) line[1] / 100.0) + 1;
    // Serial.println((float) line[0]);
    // Serial.println(((float) TOP * (float) line[0] / 100.0));
  }
}