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
import json


class InternalProgram(object):
    """
    Defines structure for internal program on the furnace
    Each internal program has only 2 segments
        1) set point and ramp
        2) same set point as 1) and hold time of 12 hrs = 720 mins. 
    It is hashable and has a definition of == operator so can be used in a set

    Attributes
    ----------
    program_number : int
        Internal Furnace program number
    program_temp : float
        Internal Furnace set point temperature
    program_segment : list
        Internal furnace segments ( 1 -2 )
    program_ramp : list
        Internal furnace ramp rate (degrees C/ min)
    prgram_time : list 
        Internal furnace time remaining for segment completion (min)
    
    Methods
    -------
    to_json(f = file_pointer)
        Writes internal program to json file

    from_json (cls, s)
        Reads json file to create internal program
    """

    def __init__(self, program_number, program_temperature):
        """
        Parameters
        ----------
        prgram_number : int
            Internal program number of program
        program_temperature : float
            Set point of internal program
        """

        if (program_number < 0 or program_number > 50):
            raise ValueError('Program number has to be between 0 and 50')
        self.program_number = program_number
        self.program_temp = program_temperature
        self.segment_number = np.linspace(1,2, 2, endpoint=True, dtype=int)
        self.segment_ramp = np.zeros_like(self.segment_number, dtype=float)
        self.segment_time = np.zeros_like(self.segment_number,dtype=int)
        self.segment_remaining_time = np.zeros_like(self.segment_number,dtype=int)

    def __eq__(self, other):
        """
        Compares two internal programs
        program1 = program2 if progam1.program_temp == program2.program_temp

        Paramters
        ---------
        other : InternalProgram
        """

        if not instance(other, type(self)):
            return NotImplemented
            test = self.program_number == other.program_number and self.program_temp == other.program_temp
            return test

    def __hash__(self):
        """
        """
        return hash((self.program_temp))

    
    def to_json(self, f):
        """
        Writes data to json file
        Paramters
        ---------
        f : fp
            Pointer to file instance
        """

        data = {'program_number': self.program_number,
                'temperature': self.program_temp,
                'segments': self.segment_number.tolist(),
                'segment_ramp': self.segment_ramp.tolist(),
                'segment_time': self.segment_time.tolist()}
        json.dump(data,f, indent=4)
    
    @classmethod
    def from_json(cls, s):
        """
        Reads data from a json
        
        Parameters
        ----------
        s : dict
            s is a dictionary loaded from json format
        """
        # data = json.loads(s)
        mat = cls(s['program_number'], s['temperature'])

        mat.segment_number = np.array(s['segments'])
        mat.segment_ramp = np.array(s['segment_ramp'])
        mat.segment_time = np.array(s['segment_time'])
        return mat

class InternalProgramDb(InternalProgram):
    """
    This class is for a database of internal programs.
    It contains a set of unique set point temperatures. 
    
    Attributes
    ---------
    program_db : set(InternalProgram)
        Set of internal programs
    program_dict : dict(InternalProgram)
        The dict key is the temperature
    """

    def __init__(self, filename):
        """
        Parameters
        ---------
        filename : str
            Name of file to read/write program database
        """
        self.program_db = set()
        if filename:
            try:
                f = open(filename,'r')
                self.read_db(f)
                f.close()
            except FileNotFoundError:
                raise FileNotFoundError
        self.program_dict = {}
        if program_db:
            for p in self.program_db:
                self.program_dict[p.program_temp] = p

    def read_db(self, f):
        """

        :param f:
        :return:
        """
        data = json.load(f)
        for d in data["programs"]:
            p = InternalProgram.from_json(d)
            self.add_to_db(p)

    def add_to_db(self, program):
        self.program_db.add(program)
        try:
            self.program_dict[program.program_temp] = program
        execpt:
            print ('Program already exists in database {}', program.program_temp)

    def write_db(self,filename):
        pass


# TODO
class Nabertherm_program:
    """
    Defines a program from a database of other furnace programs
    This will be a descriptive dictionary of names and will be populated
    from a list of internal program numbers ??
    """

    def __init__(self, name='', temp_list=[], time_list=[], db):
        if not temp_list or not time_list:
            raise Exception('Temp list or time_list cannot be empty')
        self.name = name
        if not isinstance(db, type(InternalProgramDb)):
            raise Exception('Database type not correct')
        self.db = db
        self.program_list = []
        for temp in temp_list:
            p = db[temp]
            self.program_list.append(p)


class Nabertherm(threading.Thread):
    """
    Defines the initiation of the furnace using the ip_address of furnace

    Attributes
    ----------
    ipaddr : str
        Ip Address of furnace
    running_program : bool
        Indicates whether a program is running or not
    internal_program_db : InternalProgramDb
        Database of internal programs
    """

    def __init__(self, ipaddr, 
                    program_num_list = [], 
                    interval=1.0, 
                    filename=None):

        if not program_num_list and not filename:
            raise Exception('Both filename and program_list cannot be empty') 

        threading.Thread.__init__(self)
        self.ipaddr = ipaddr
        self.running_program = None
        self.internal_progam_db = None
        # Set the internal furnace programs

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
        
        if not program_num_list:
            self.internal_progam_db = InternalProgramDb(filename=filename)
            # --- Now create the database
        else:
            for i in program_num_list:
                p = self.read_single_internal_program(i)
                self.internal_progam_db.add_to_db(p)
                # ---- decide if we want to write this or not 

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

    def stop_internal_program(self, program_number):
        """
        Stops a currently running internal program
        :return:
        """
        self.client.write_registers(address=148, values=(2))

    def start_internal_program(self, program_number):
        self.client.write_registers(address=148, values=(1,program_number,1))

    def pause(self):
        self.alive = False

    def read_all_programs(self):
        for p in self.furnace_programs:
            p.read_program(p.program_number, self)

    def read_single_internal_program(self, program_number):
        assert program_number > -1, 'Program number has be between 0 and 50'
        assert program_number < 51,'Program number has be between 0 and 50'
        if self.connected_to_furnace:
            self.stop_run()
            result = self.start_internal_program(program_number)
            time.sleep(self.interval)
            temp = float(self.client.read_holding_registers(address=111,count=1))/10.0
            p = InternalProgram(program_number,temp)
            p.segment_time[0] = self.read_remaining_time()
            p.segment_ramp[0] = p.program_temp/float(segment_time)
            self.stop_run()
            return p

    def read_temerature(self):
        temperature = self.client.read_holding_registers(address=100, count=1)
        return float(temperature)/10.0

    def read_program_number(self):
        pno = self.client.read_holding_registers(address=126, count=1)
        return pno

    def read_segment_number(self):
        return self.client.read_holding_registers(address=127, count=1)

    def read_set_value_temperature(self):
        temperature = self.client.read_holding_registers(address=111, count=1)
        return float(temperature)/10.0

    def read_remaining_time(self):
        res = self.client.read_holding_registers(address=128, count=2) 
        decoder = BinaryPayloadDecoder(res.registers, byteorder=Endian.Little, wordorder=Ending.Little)
        time = decoder.decode_32bit_int # value in minutes
        return time

    def start_internal_program(self, program_number, segment_number=1):
        res = self.client.write_registers(address=148, values=(1,program_number,segment_number))
        return res





if __name__ == "__main__":
    
    furnace = Nabertherm(ipaddr='192.168.4.70', program_num_list=[3])

    # ---- Read all programs ----
    # Careful here --- this is long step 10 s * 50 * 80 (40000 s > 10 hrs)
    # This is there just for the future, where everything will be automated
    # while not furnace.cycle_end:
    # --- Furnace will be stopped by
    furnace.stop_run()