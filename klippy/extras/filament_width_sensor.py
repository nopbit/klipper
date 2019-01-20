# Support for filament width sensor
#
# Copyright (C) 2019  Mustafa YILDIZ <mydiz(at)hotmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

ADC_REPORT_TIME = 0.500
ADC_SAMPLE_TIME = 0.001
ADC_SAMPLE_COUNT = 8
MEASUREMENT_INTERVAL_MM = 10

class FilamentWidthSensor:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.pin = config.get('pin')
        self.nominal_filament_dia = float(config.get('default_nominal_filament_dia'))
        self.measurement_delay_mm = float(config.get('measurement_delay_cm')) * 10
        self.measurement_max_difference = float(config.get('max_difference'))
        self.max_diameter = self.nominal_filament_dia + self.measurement_max_difference
        self.min_diameter = self.nominal_filament_dia - self.measurement_max_difference
        #Filament array [position, filamentWidth]
        self.filament_array = []
        self.lastFilamentWidthReading = 0
        # printer objects
        self.gcode = self.toolhead = self.ppins = self.mcu_adc = None
        self.printer.register_event_handler("klippy:ready", self.handle_ready)
        # Start adc
        self.ppins = self.printer.lookup_object('pins')
        self.mcu_adc = self.ppins.setup_pin('adc', self.pin)
        self.mcu_adc.setup_minmax(ADC_SAMPLE_TIME, ADC_SAMPLE_COUNT)
        self.mcu_adc.setup_adc_callback(ADC_REPORT_TIME, self.adc_callback)
        # extrude factor updating
        self.extrude_factor_update_timer = self.reactor.register_timer(
            self.extrude_factor_update_event)

    # Initialization
    def handle_ready(self):
        # Load printer objects
        self.gcode = self.printer.lookup_object('gcode')
        self.toolhead = self.printer.lookup_object('toolhead')
        self.heater_bed = self.printer.lookup_object('heater_bed', None)
        self.gcode.register_command('M407', self.cmd_M407)

        # Start extrude factor update timer
        self.reactor.update_timer(self.extrude_factor_update_timer, self.reactor.NOW)

    def adc_callback(self, read_time, read_value):
        # read sensor value
        self.lastFilamentWidthReading = float("{0:.2f}".format(max(.00001, min(.99999, read_value)) * 5))
        pos = self.toolhead.get_position()
        last_epos = pos[3]
        #fill array
        if len(self.filament_array) > 0:
            # Get last reading position in array & calculate next reading position
            next_reading_position = self.filament_array[-1][0] + MEASUREMENT_INTERVAL_MM
            if next_reading_position <= (last_epos + self.measurement_delay_mm):
                self.filament_array.append([last_epos + self.measurement_delay_mm, self.lastFilamentWidthReading])
        else:
            # add first item to array
            self.filament_array.append([self.measurement_delay_mm + last_epos, self.lastFilamentWidthReading])

    def extrude_factor_update_event(self, eventtime):
        # Update extrude factor
        pos = self.toolhead.get_position()
        last_epos = pos[3]
        # Does filament exists
        if self.lastFilamentWidthReading > 0.5:
            if len(self.filament_array) > 0:
                pending_position = self.filament_array[0][0]
                if pending_position <= last_epos:
                    # Get first item in filament_array queue
                    item = self.filament_array.pop(0)
                    filament_width = item[1]
                    if (filament_width <= self.max_diameter) and (filament_width >= self.min_diameter):
                        percentage = round(self.nominal_filament_dia / filament_width * 100)
                        self.gcode.cmd_M221({'S': percentage})
                    else:
                        self.gcode.cmd_M221({'S': 100})
        else:
            self.gcode.cmd_M221({'S': 100})
            self.filament_array = []
        return eventtime + 1

    def cmd_M407(self, params):
        response = ""
        if self.lastFilamentWidthReading > 0:
            response += "Filament dia (measured mm): " + str(self.lastFilamentWidthReading)
        else:
            response += "Filament NOT present"
        self.gcode.respond(response)

def load_config(config):
    return FilamentWidthSensor(config)
