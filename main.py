import time
import numpy as np
from commands import connect_flowmeter, init_flowmeter, close_flowmeter, get_measurement
import serial.tools.list_ports
import pandas as pd
import matplotlib.pyplot as plt
import statistics

def _read_message(board, timeout=1):

    # Define the markers
    startMarker = 60 # <
    endMarker = 62 # >
    midMarker = 44 # ,

    final_string = ""
    x = "z" # Random char to start with

    # Start a timer
    start_time = time.time()
    read_arduino = True

    # Wait for the start character
    while  ord(x) != startMarker and read_arduino:
        x = board.read()

        # Check for empty character·
        try:
            test_x = ord(x)
        except:
            x = "z"

        # Check for timeout
        if timeout > 0 and time.time() - start_time >= timeout:
            read_arduino = False

    # Start the processing loop
    while ord(x) != endMarker and read_arduino:

        # Get the next character
        x = board.read()

        # Start the reading process
        if ord(x) != startMarker and ord(x) != endMarker:
            final_string += x.decode()

        # Check for timeout
        if timeout > 0 and time.time() - start_time >= timeout:
            read_arduino = False

    # Return a timeout error if needed
    if not read_arduino:
        final_string = None

    return final_string

# ----------------------------
# Send an input to the Arduino
def sendToArduino(message):

    connection.write(bytes(message, 'utf-8'))
    connection.flushInput()
    newMessage = readFromArduino(connection)

    return newMessage

# --------------------------------
# Read any output from the Arduino
def readFromArduino(board, timeout=-1):

    # Start a timer
    start_time = time.time()
    read_arduino = True

    # Start the waiting loop
    while board.inWaiting() == 0 and read_arduino:

        # Check for timeout
        if timeout > 0 and time.time() - start_time >= timeout:
            read_arduino = False

    # Read the incoming message
    if read_arduino:
        return _read_message(board)

    else:
        return None

def setPump(freq, amp):
    sendToArduino("<FREQ,0," + str(freq) + ">")
    sendToArduino("<AMP,0," + str(amp) + ">")

## ===========
## TO THE PUMP

# Start the connection
connection = serial.Serial()

connection.port = 'COM5' # Set port
connection.baudrate = 9600 # Set baudrate

connection.parity = serial.PARITY_NONE # Enable parity checking
connection.stopbits = serial.STOPBITS_ONE # Number of stop bits
connection.bytesize = serial.EIGHTBITS # Number of databits

connection.timeout = 1 # Set a timeout value
connection.xonxoff = 0 # Disable software control
connection.rtscts = 0

connection.open()

readFromArduino(connection)

time.sleep(1)

# Get the ID
print('Getting pump ID')
message = sendToArduino("<GETID,0,0>")
print(message)

# Turn the pump on
print('Turning pump on')
sendToArduino("<ON,0,0>")

## ================
## TO THE FLOWMETER

# Open the connection
flowm = connect_flowmeter('COM7')

# Start the flowmeter
init_flowmeter(flowm, 'SF06')

#PID Part
class PID(object):

    def __init__(self, target, P, I, D) -> None:
        self.k_p = P
        self.k_i = I
        self.k_d = D

        self.integral = 0
        self.target = target
        self.pre_error = 0

    def update(self, delta_t, cur_val, output=None, mode='AMP0'):
        error = self.target - cur_val
        self.integral += error

        p_change = self.k_p * error
        i_change = self.k_i * self.integral * delta_t
        d_change = self.k_d * (error - self.pre_error) / delta_t

        delta_output = p_change + i_change + d_change
        output += delta_output

        self.pre_pre_error = self.pre_error

        self.pre_error = error

        return output

AMP = 0
FREQ = 0
setPump(FREQ, AMP)

data = pd.DataFrame(columns=["time", "target", "feedback", "amp", "freq"])

while True:
    try:
        targetValue = float(input("Please enter the target flow rate (between 0 and 2000): "))  # get target value here
        if targetValue < 0 or targetValue > 2000:
            raise ValueError("The target flow rate should be a number between 0 and 2000.")
        break
    except ValueError as e:
        print("Invalid input. Please enter a number between 0 and 2000.")

start_time = time.time()  # record the start time
flag = time.time() + 0.13
delta_t = 0

try:
    start_loop = time.time()  # 记录循环开始的时间戳
    loop_duration = 120  # 循环应运行的总时间（秒），这里是两分钟

    AMP_PID = PID(targetValue, 0.065, 0, 0)
    FREQ_PID = PID(targetValue, 0.08, 0, 0)

    while True:
        # 0 control loop time
        if time.time() - start_loop > loop_duration:
            raise KeyboardInterrupt

        # 1 get current flow rate
        all_values = []
        for i in range(40):
            value = get_measurement(flowm, 'SF06', 10)
            all_values.append(value)
            time.sleep(.05)
        flowrate = np.mean(all_values)

        # 2 timer
        delta_t = time.time() - flag
        flag = time.time()
        error = targetValue - flowrate
        # 3 PID
        if abs(error) > 5:
            FREQ = FREQ_PID.update(delta_t, flowrate,FREQ, mode='FREQ')
            if FREQ > 150:  # Set upper limit for Freq
                FREQ = 150
        # AMP control
            AMP = AMP_PID.update(delta_t, flowrate, AMP, mode='AMP')
            if AMP > 150:  # Set upper limit for AMP
                AMP = 150

        if AMP is not None and FREQ is not None:
            setPump(FREQ, AMP)

        current_time = time.time() - start_time

        print(FREQ, AMP)

        data = pd.concat(
            [data, pd.DataFrame([{"time": current_time, "target": targetValue, "feedback": flowrate, "amp": AMP,
                              "freq": FREQ, "error": error}], columns=["time", "target", "feedback", "amp", "freq", "error"])],
            ignore_index=True)

        # insert this line to reset the index of data
        data.reset_index(drop=True, inplace=True)

        time.sleep(0.1)

except KeyboardInterrupt:
    data.to_csv('pump_data.csv', mode='a', index=False)

    print("Program stopped by user")

    # Turn the pump off
    print('Turning pump off')
    sendToArduino("<OFF,0,0>")

    # Stop the connection
    connection.close()
    close_flowmeter(flowm, 'SF06')

    # update figure
    plt.figure(figsize=(10, 6))  # specify figure size
    plt.plot(data["time"], data["target"], label="Target Flowrate")
    plt.plot(data["time"], data["feedback"], label="Measured Flowrate")

    # calculate average error and standard deviation of flowrate after 20s
    after_40s_data = data[data["time"] > 40]
    avg_error_after_40s = after_40s_data["error"].mean()
    flowrate_std = after_40s_data["feedback"].std()
    avg_amp_after_40s = after_40s_data["amp"].mean()
    avg_freq_after_40s = after_40s_data["freq"].mean()

    plt.text(0.62, 0.13, f"Average error after 40s: {avg_error_after_40s:.2f}", transform=plt.gca().transAxes)

    plt.text(0.62, 0.18, f"Standard deviation of flowrate: {flowrate_std:.2f}", transform=plt.gca().transAxes)

    plt.text(0.62, 0.23, f"Average amplitude after 40s: {avg_amp_after_40s:.2f} V", transform=plt.gca().transAxes)

    plt.text(0.62, 0.28, f"Average frequency after 40s: {avg_freq_after_40s:.2f} Hz", transform=plt.gca().transAxes)

    # Set x/y labels
    plt.xlabel('Time (s)')
    plt.ylabel('Flowrate (µL/min)')

    # Set plot title
    plt.title('Flowrate Over Time')

    plt.legend(loc='best')  # place legend at the best position
    plt.grid(True)  # show grid

    # Show plot
    plt.show()





