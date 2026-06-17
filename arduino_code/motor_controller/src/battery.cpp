#include "battery.h"

#define R1 33.2e3
#define R2 65.8e3

#define dVdI 40e-3

float read_vcc() {
    // Set reference to AVcc and input to internal 1.1V bandgap
    ADMUX = _BV(REFS0) | _BV(MUX4) | _BV(MUX3) | _BV(MUX2) | _BV(MUX1);
    ADCSRB &= ~_BV(MUX5);
    
    // delay(1); // Wait for voltage to settle
    
    // Dummy conversion
    ADCSRA |= _BV(ADSC);
    while (bit_is_set(ADCSRA, ADSC));
    
    // Average multiple readings
    long result = 0;
    for (int i = 0; i < 4; i++) {
        ADCSRA |= _BV(ADSC);
        while (bit_is_set(ADCSRA, ADSC));
        result += ADCW;
    }
    result /= 4;
    
    if (result > 0) {
        return 1125.3 / (float)result * 1.0132;
    }
    
    return 0.0;
}

float read_voltage(uint8_t pin, float Vref) {
    int analog_value = analogRead(pin);
    float pin_voltage = (((float) analog_value) / 1023.0) * Vref;
    // Add 48mV, since the Arduino ground is approximately 48mV higher than that of the battery
    float battery_voltage = pin_voltage * (R1 + R2) / R1 + 0.048;

    return battery_voltage;
}

float read_current(uint8_t pin, float Vref) {
    int analog_value = analogRead(pin);
    // int analog_value = 0;
    float pin_voltage = (((float) analog_value) / 1023.0) * Vref;
    float battery_current = (pin_voltage - 0.5*Vref) / dVdI;

    return battery_current;
}