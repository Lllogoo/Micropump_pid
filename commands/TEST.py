import numpy as np
import serial.tools.list_ports
import time

from commands import connect_flowmeter, init_flowmeter, close_flowmeter, get_measurement

# ----------------------------------------------
# Read the message coming from the board, if any
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

# -------------------------------------------
# Set the frequency and amplitude of the pump
def setPump(freq, amp):
    sendToArduino("<FREQ,1,"+str(freq)+">")
    sendToArduino("<AMP,1,"+str(amp)+">")

##-\-\-\-\-\-\-\
## INITIALISATION
##-/-/-/-/-/-/-/

# Get the list of ports
ports = serial.tools.list_ports.comports()

# Make the list
all_ports = []
for p in ports:
    print(p.device)

## ===========
## TO THE PUMP



all_data = []

for i in range(30):
    for freq, amp in [(30, 40), (50, 75), (100, 100)]:
        # Start the connection
        connection = serial.Serial()

        connection.port = 'COM5'  # Set port
        connection.baudrate = 9600  # Set baudrate

        connection.parity = serial.PARITY_NONE  # Enable parity checking
        connection.stopbits = serial.STOPBITS_ONE  # Number of stop bits
        connection.bytesize = serial.EIGHTBITS  # Number of databits

        connection.timeout = 1  # Set a timeout value
        connection.xonxoff = 0  # Disable software control
        connection.rtscts = 0

        connection.open()

        readFromArduino(connection)

        time.sleep(1)

        # Get the ID
        print('Getting pump ID')
        message = sendToArduino("<GETID,1,0>")
        print(message)

        # Turn the pump on
        print('Turning pump on')
        sendToArduino("<ON,1,0>")

        ## ================
        ## TO THE FLOWMETER

        # Open the connection
        flowm = connect_flowmeter('COM7')

        # Start the flowmeter
        init_flowmeter(flowm, 'SF06')

        ##-\-\-\-\-\-\
        ## CALIBRATION
        ##-/-/-/-/-/-/
        # Set the new values
        print('Setting freq =',freq,'Hz, amp =',amp,'V')
        setPump(freq,amp)
        time.sleep(5)

        # Read the values from the flowmeter
        all_values = []
        for i in range(100):
            value = get_measurement(flowm, 'SF06', 10)
            all_values.append(value)
            time.sleep(.05)

        all_data.append( [freq,amp,np.mean(all_values), np.std(all_values, ddof=1)] )

        print('Turning pump off')
        sendToArduino("<OFF,1,0>")
        connection.close()
        close_flowmeter(flowm, 'SF06')

        time.sleep(1)  # pause before the next run
np.savetxt('results_30-40-50-75-100-100.csv', all_data, delimiter=',',
            header='Frequency (Hz),Amplitude (V),Flow rate (uL/min),Err (uL/min)')

