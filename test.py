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

    def __init__(self, target, dt, P, I, D) -> None:
        self.dt = dt
        self.k_p = P  # 比例系数
        self.k_i = I  # 积分系数
        self.k_d = D  # 微分系数

        self.integral = 0
        self.target = target  # 目标值
        self.pre_error = 0  # t-1 时刻误差值

    def update(self, cur_val, output=None, mode='AMP0'):
        error = self.target - cur_val
        self.integral += error

        p_change = self.k_p * error
        i_change = self.k_i * self.integral * self.dt
        d_change = self.k_d * (error - self.pre_error) / self.dt

        delta_output = p_change + i_change + d_change

#        if mode == 'AMP':
#            if delta_output > 100:
#                delta_output = 100

        output += delta_output

        if mode == 'FREQ':
            output = round(output / 6) * 6  # round to nearest 3

        self.pre_pre_error = self.pre_error

        self.pre_error = error

        return int(output)

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
#        AMP_PID = PID(targetValue, delta_t, 0.002, 0.016, 0)
#        FREQ_PID = PID(targetValue, delta_t, 0.05, 0.01, 0)
        AMP_PID = PID(targetValue, delta_t, 0.03, 0.0075, 0)
        FREQ_PID = PID(targetValue, delta_t, 0.05, 0.00725, 0)

        FREQ = FREQ_PID.update(flowrate, FREQ, mode='FREQ')
        if FREQ > 150:  # Set upper limit for Freq
            FREQ = 150
        # AMP control
        if abs(error) > 5:
            AMP = AMP_PID.update(flowrate, AMP, mode='AMP')
            if AMP > 150:  # Set upper limit for AMP
                AMP = 150

        if AMP is not None and FREQ is not None:
            setPump(FREQ, AMP)

        print(FREQ, AMP)

        current_time = time.time() - start_time

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
    #plt.plot(data["time"], data["amp"], label="amp")
    #plt.plot(data["time"], data["freq"], label="freq")

    # calculate average error and standard deviation of flowrate after 20s
    after_40s_data = data[data["time"] > 40]
    avg_error_after_40s = after_40s_data["error"].mean()
    flowrate_std = after_40s_data["feedback"].std()

    avg_amp_after_40s = after_40s_data["amp"].mean()
    avg_freq_after_40s = after_40s_data["freq"].mean()

    # plot average error after 20s
    plt.text(0.62, 0.13, f"Average error after 40s: {avg_error_after_40s:.2f}", transform=plt.gca().transAxes)

    # plot standard deviation of flowrate
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






