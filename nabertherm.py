"""
Nabertherm class for reading and writing data from Nabertherm Furnace
Based on pymodbus that implements Modbus Protocol
"""

__author__ = "Srinath Chakravarthy"
__copyright__ = "2019"

from pymodbus.client.sync import ModbusTcpClient as tcp
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
import threading
import time
import numpy as np


class InternalProgram:
    """
    Defines structure for internal program on the furnace
    Each inter
    """

    def __init__(self, program_number):
        if (program_number < 0 or program_number > 50):
            raise ValueError('Program number has to be between 0 and 50')
        self.program_number = program_number
        self.segment_number = np.linspace(1,5, 5, endpoint=True, dtype=int)
        self.segment_temp = np.zeros_like(self.segment_number, dtype=float)
        self.segment_reserve = np.zeros_like(self.segment_number, dtype=float)
        self.segment_charge = np.zeros_like(self.segment_number, dtype=float)

    def read_program(self, program_number, furnace, sleep_interval = 1):
        if furnace.connected_to_furnace:
            furnace.stop_run()
            # Always start program number, segment 0 for initialization

            # Start the furnace
            result = furnace.client.write_registers(address=148,
                                            values=(1, self.program_number, 0))
            try:
                for index, i in enumerate(self.segment_number):                  
                    # Segment jumo
                    result = furnace.client.write_registers(address=148, values=(1,self.program_number,i))
                    # Start
                    res = furnace.client.write_registers(address = 148, values = (1))
                    time.sleep(sleep_interval)
                    # ? This needs to be verified (if this is the correct register or not)
                    res = furnace.client.read_holding_registers(address=111, count=3)
                    self.segment_temp[index] = float(res.registers[0])/10.0
                    self.segment_reserve[index] = float(res.registers[1])/10.0
                    self.segment_charge[index] = float(res.registers[2])/10.0

                    # Read remaining time for each segment 
                    # At the moment not sure how to decode this.... need a few trials
                    # Input needed from Lincoln on how to do this ?
                    res = furnace.client.read_holding_registers(address=128, count=2)
                    # Stop
                    res = furnace.client.write_registers(address=148, values=(2))
            except :
                raise
            furnace.stop_run()

class Nabertherm(threading.Thread):
    """
    Defines the initiation of the furnace using the ip_address of furnace
    """

    def __init__(self, ipaddr, interval=1.0):
        threading.Thread.__init__(self)
        self.ipaddr = ipaddr
        self.programs = {}
        self.running_program = None
        # Set the internal furnace programs
        self.furnace_program_numbers = np.linspace(0,3,4,endpoint=True, dtype=int)
        self.furnace_programs = []
        for i in self.furnace_program_numbers:
            self.furnace_programs.append(InternalProgram(i))

        # --- Counting seconds
        self.interval = interval
        self.value = 0
        self.alive = False
        self.cycle_end = False
        self.active_temp = 0
        self.logging_time = []
        self.logging_temp = []


        try:
            with tcp(self.ipaddr) as client:
                result = client.connect()
                self.client = client
                self.connected_to_furnace = True
        except:
            raise ConnectionError('Cannot Connect to furnace')
        
    def run(self, program_name, interval, log=False):
        self.start()
        self.interval = interval
        if not self.programs:
            raise ValueError('No programs stored in database, need at least on program')
        try:
            if self.running_program:
                raise ConnectionRefusedError('Cannot start one program when another is running')
            self.running_program = self.programs[program_name]
            self.alive = True
            self.start()
            # TODO go through everything in program_name and send end_cycle
            # What is below is example code MODIFY to confirm
            # result = self.client.write_registers(address=148,
            #                                      values=(1,
            #                                              self.program_number,
            #                                              self.segment_number))
            while self.alive:
                time.sleep(self.interval)
                self.value += self.interval
                if log:
                    temp = self.client.read_holding_registers(address=100, count=1)
                    self.logging_temp.append(float(temp)/10.0)
                    self.logging_time.append(self.value)

        except KeyError:
            raise KeyError('Program name not found')

    def stop_run(self):
        try:
            self.stop()
            self.alive = False
            self.client.write_registers(address=148,values=(2))
            self.running_program = None

        except:
            pass
        
    def pause(self):
        self.alive = False

    def read_all_programs(self):
        for p in self.furnace_programs:
            p.read_program(p.program_number, self)

    def read_single_internal_program(self, program_number):
        assert program_number > -1, 'Program number has be between 0 and 50'
        assert program_number < 51,'Program number has be between 0 and 50'
        p = self.furnace_programs[program_number]
        p.read_program(p.program_number, self)

# TODO
class Nabertherm_program:
    """
    Defines a program from a database of other furnace programs
    This will be a descriptive dictionary of names and will be populated
    from a list of internal program numbers ??
    """

    def __init__(self, name, program_number, segment_number = 0, time=1):
        self.name = name
        self.program_number = program_number
        self.time = time


if __name__ == "__main__":
    furnace = Nabertherm(ipaddr='192.168.4.70')
    # ---- Read all programs ----
    # Careful here --- this is long step 10 s * 50 * 80 (40000 s > 10 hrs)
    # This is there just for the future, where everything will be automated
    # while not furnace.cycle_end:
    furnace.read_single_internal_program(3)
    # --- Furnace will be stopped by
    #furnace.stop()