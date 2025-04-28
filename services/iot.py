from helpers.custom_logger import CustomLogger

import asyncio
import serial_asyncio
import serial.tools.list_ports

from services.database import Database
from services.webcam import VideoCam

WAIT_TIME = 5.0
EAR_THRESHOLD = 0.25 

FIELD_ACCESS = {
    'air_cond_service': ('humid','temp'),
    'dist_service': 'dis',
    'headlight_service': 'lux',
    'drowsiness_service': 'camera',
    'drowsiness_threshold': 'wait_time',
}

class IOTSystem:
    _instance = None

    def __new__(cls, config=None):
        if not cls._instance:
            cls._instance = super(IOTSystem, cls).__new__(cls)
            cls._instance._init_iot_system(config)
        return cls._instance

    def _init_iot_system(self, config=None):
        CustomLogger()._get_logger().info("IOT System initialized.")
        self.db = Database()._instance
        self.running = False
        self.reader = None
        self.writer = None

        port = self._get_port()
        if port != "None":
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._connect_serial(port)) 
            except RuntimeError:
                asyncio.run(self._connect_serial(port))
        else:
            # print("No serial device found.")
            CustomLogger()._get_logger().info("No serial device found.")
        
        self.states = {
            'humid': True,
            'temp': True,
            'lux': True,
            'dis': True,
            'camera': True
        }
        
        self.videocam = VideoCam()

    async def _connect_serial(self, port):
        """Async function to connect to serial device."""
        try:
            self.reader, self.writer = await serial_asyncio.open_serial_connection(url=port, baudrate=115200)
            CustomLogger()._get_logger().info(f"Connected to serial: {port}")

        except Exception as e:
            CustomLogger()._get_logger().exception(f"Failed to connect to serial: {e}")

    async def _send_serial(self, uid):
        """Sends data to the serial device."""
        while self.running:
            try:
                # Set up the change stream to watch for updates
                with Database()._instance.get_device_collection().watch() as stream:
                    for change in stream:
                        # Check if the change is relevant to the given UID
                        if change['operationType'] == 'insert':
                            doc = change['fullDocument']
                            doc["_id"] = str(doc["_id"])
                            CustomLogger()._get_logger().info(f"Data retrieved: {doc}")

                            feed = doc["device_type"]
                            payload = doc["value"]

                            message = f"!{feed}:{payload}#"
                            CustomLogger()._get_logger().info(f"Sending data: {message}")

                            if self.writer:
                                self.writer.write(message.encode())
                                CustomLogger()._get_logger().info(f"Sent: {message}")

            except asyncio.CancelledError:
                CustomLogger()._get_logger().info("sendSerial task was cancelled.")
                break

            except Exception as e:
                CustomLogger()._get_logger().exception(f"Error watching database changes: {e}")

            
    @staticmethod
    def _get_port():
        ports = serial.tools.list_ports.comports()

        for port in ports:
            if "USB-SERIAL" in str(port):
                return str(port).split(" ")[0]
            
        return "None"

    async def _read_serial(self, uid):
        """Reads and processes serial data asynchronously."""
        if not self.reader:
            CustomLogger()._get_logger().warning("No serial connection available.")
            return
        
        while self.running:
            try:
                data = await self.reader.readuntil(b"#")
                data = data.decode("UTF-8").replace("#", "").replace("!", "")

                CustomLogger()._get_logger().info(f"Received data: {data}")
                await self._process_data(data, str(uid))

                await asyncio.sleep(1)
            
            except Exception as e:
                CustomLogger()._get_logger().exception(f"Serial read error: {e}")    

    async def _process_data(self, data, uid):
        """Processes incoming serial data and stores it in DB."""
        CustomLogger()._get_logger().info(f"Processing data: {data}")
        splitData = data.split(":")

        if len(splitData) < 2:
            return
        
        sensor_type, value = splitData[0], splitData[1]

        if self.states[sensor_type]:
            CustomLogger()._get_logger().info(f"Processed: {sensor_type} = {value}")

            if self.states[sensor_type]:
                try:
                    doc: dict = {
                        'uid': str(uid),
                        'sensor_type': sensor_type.lower(), 
                        'value': float(value)
                    }

                    Database()._instance._add_doc_with_timestamp('environment_sensor', doc)

                except ValueError:
                    CustomLogger()._get_logger().exception(f"Invalid data format: {sensor_type} -> {value}")
                    Database()._instance._add_doc_with_timestamp('environment_sensor', doc)

    async def _start_webcam(self,uid):
        # call to database for user preferences
        thresholds = {'show_window': True}

        if self.videocam:
            await self.videocam.start_webcam(thresholds)
            last_alarm_state = None

            while self.videocam.running:
                await asyncio.sleep(0.1)

                if hasattr(self.videocam,'last_frame'):
                    _,play_alarm = self.videocam.last_frame

                    if play_alarm != last_alarm_state:
                        value = '1' if play_alarm else '0'
                        
                        try:
                            # TODO alarm to be update to yolobit
                            self.writer.write(f"!alarm:{value}#".encode())
                            
                            await self.write_action_history(
                                uid=uid,
                                service_type='alarm',
                                value=value
                            )

                        except Exception as e:
                            CustomLogger()._get_logger().exception(f"Failed to update alarm status: {e}")
                            raise e
                        
                        last_alarm_state = play_alarm                    
            
        else:
            CustomLogger()._get_logger().warning("Webcam not initialized.")

    async def _resolve_service(self, uid):
        try:
            services = Database()._instance.get_services_status_doc_by_id(uid, False)

            if services is None:
                CustomLogger()._get_logger().info("No services status document found for this user.")
                return None
            
            for service in services:
                convert_service = FIELD_ACCESS.get(service, None)

                if convert_service is None:
                    raise ValueError(f"Invalid service type: {service}")
                
                if isinstance(convert_service, tuple):
                    for convert in convert_service:
                        self.states[convert] = service['value']
                        
                elif convert_service in ['lux','dis','camera']:
                    self.states[convert_service] = service['value']
                    
                else:
                    self.videocam.set_time_threshold(service['value'])
            
        except Exception as e:
            CustomLogger()._get_logger().exception(f"Error resolving service: {e}")
            return None
        
    async def _start_system(self, uid):
        if not self.running:
            self.running = True

            # Start serial communication
            port = self._get_port()
            if port != "None":
                # await self._connect_serial(port)

                # asyncio.create_task(self._read_serial(uid))
                # asyncio.create_task(self._send_serial(uid))
                CustomLogger()._get_logger().info("Sensor System started.")
            
            if self.states['camera']:
                # asyncio.create_task(self._start_webcam(uid))
                CustomLogger()._get_logger().info("Webcam System started.")

        else:
            CustomLogger()._get_logger().warning("System already running.")

    async def _stop_system(self):
        self.running = False
        # self.videocam.stop()
            
        CustomLogger()._get_logger().info("IOT System stopped.")

    async def _stop_camera(self, uid):
        if self.videocam:
            self.videocam.stop()
            CustomLogger()._get_logger().info("Webcam System stopped.")

        else:
            CustomLogger()._get_logger().warning("Webcam not initialized.")

    async def _start_camera(self, uid):
        asyncio.create_task(self._start_webcam(uid))
        CustomLogger()._get_logger().info("Webcam System started.")

    async def _control_service(self, uid: str, service_type: str, value: any):
        """Controls a service state and sends commands to Arduino"""
        if not self.writer:
            CustomLogger()._get_logger().warning("No serial connection available")
            # raise Exception("No serial connection available")
            
        if service_type.startswith("air_cond"):
            convert_type = ["humid","temp"], "fan"
        elif service_type.startswith("headlight"):
            convert_type = ["lux"], None
        elif service_type.startswith("drowsiness"):
            convert_type = ["camera"], None
        elif service_type.startswith("dist"):
            convert_type = ["dis"], None
        else:
            CustomLogger()._get_logger().warning(f"Unknown service type: {service_type}")
            raise Exception(f"Unknown service type: {service_type}")

        write_type = service_type
        
        if isinstance(value, str):
            # Handle on/off states
            for cvt in convert_type[0]:
                self.states[cvt] = value.lower() == "on"
            
        elif value is not None:
            # Handle numeric values for thresholds, temperature, etc.
            if service_type.startswith('drowsiness'):
                # print(self.videocam)
                # await self.videocam.set_time_threshold(value)
                write_type = 'drowsiness_threshold'

            elif convert_type[1] is not None:
                command = f'{convert_type[1]}:{value}#'
                write_type = 'air_cond_temp'

            else:
                command = f'{convert_type[0][0]}:{value}#'
                write_type = 'headlight_brightness'

        else:
            command = f'{convert_type[0][0]}:1#'
            write_type = 'air_cond_temp' if convert_type[0][0] == 'temp' else 'headlight_brightness'
        
        try :
            if 'command' in locals():
                # self.writer.write(command.encode())
                CustomLogger()._get_logger().info(f"Execute command \"{command}\"")

        except Exception as e:
            CustomLogger()._get_logger().error(f"Failed to execute command: {e}")
            raise Exception(f"Failed to execute command")

        session = Database()._instance.client.start_session()
        try:
            # with session.start_transaction():
            #     Database()._instance.update_service_status(
            #         uid=uid,
            #         service_type=write_type,
            #         value=value if value is not None else 1,
            #         session=session
            #     )
                
            #     Database()._instance.write_action_history(
            #         uid=uid,
            #         service_type=write_type,
            #         value=value if value is not None else 1,
            #         session=session
            #     )

            CustomLogger()._get_logger().info(f"Updated service status document and action history")

        except Exception as e:
            session.abort_transaction()
            CustomLogger()._get_logger().error(f"Failed to update service status: {e}")
            raise Exception(f"Failed to update service status document")
        
if __name__ == "__main__":
    import time
    CustomLogger()._get_logger().info("IOT System: __main__")
    iotsystem = IOTSystem()._instance
    asyncio.run(iotsystem._start_system('123'))
    
    time.sleep(20)
    
    iotsystem._stop_system()
