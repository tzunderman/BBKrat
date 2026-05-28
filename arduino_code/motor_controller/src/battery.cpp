#include "battery.h"

#define R1 33.2e3
#define R2 65.8e3

float read_voltage(uint8_t pin) {
    int analog_value = analogRead(pin);
    float pin_voltage = (((float) analog_value) / 1023) * 5.0;
    float battery_voltage = pin_voltage * (R1 + R2) / R1;

    return battery_voltage;
}

float read_current(uint8_t pin) {
    int analog_value = analogRead(pin);
    float pin_voltage = (((float) analog_value) / 1023.0) * 5.0;
    float battery_current = pin_voltage / 40e-3;

    return battery_current;
}