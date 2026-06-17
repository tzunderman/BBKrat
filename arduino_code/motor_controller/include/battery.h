#ifndef _BATTERY_H_
#define _BATTERY_H_

#include <Arduino.h>

float read_vcc();
float read_voltage(uint8_t pin, float Vref);
float read_current(uint8_t pin, float Vref);

#endif /* _BATTERY_H_ */