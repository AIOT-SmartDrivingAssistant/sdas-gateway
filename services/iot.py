import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from helpers.custom_logger import CustomLogger

import asyncio
import serial_asyncio
import serial.tools.list_ports

from services.database import Database
from services.webcam import VideoCam
from services.device import Device

from unittest.mock import MagicMock


WAIT_TIME = 5.0
EAR_THRESHOLD = 0.25 

FIELD_ACCESS = {
    'air_cond_service': ('humid','temp'),
    'distance_service': 'dis',
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
        self._serial_read_task = None
        CustomLogger()._get_logger().info("IOT System initialized.")
        self.db = Database()._instance
        self.running = False
        self.reader = None
        self.writer = None
        self.uid = None



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
        self.websocket = None

    async def _connect_serial(self, port):
        """Async function to connect to serial device."""
        try:
            self.reader, self.writer = await serial_asyncio.open_serial_connection(url=port, baudrate=115200)
            CustomLogger()._get_logger().info(f"Connected to serial: {port}")
            self.device = Device(self.writer, self.uid, self.websocket)

        except Exception as e:
            CustomLogger()._get_logger().exception(f"Failed to connect to serial: {e}")
            
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
        
        sensor_type, value = splitData[0].strip(), splitData[1].strip()

        if self.states[sensor_type]:
            CustomLogger()._get_logger().info(f"Processed: {sensor_type} = {value}")

            if self.states[sensor_type]:
                try:
                    doc: dict = {
                        'uid': str(uid),
                        'sensor_type': sensor_type.lower(), 
                        'value': float(value)
                    }

                    await self.preprocess_data(self.uid, sensor_type, value)

                    Database()._instance._add_doc_with_timestamp('environment_sensor', doc)

                except ValueError:
                    CustomLogger()._get_logger().exception(f"Invalid data format: {sensor_type} -> {value}")
                    Database()._instance._add_doc_with_timestamp('environment_sensor', doc)

    async def set_thresholds(self, uid, sensor_type, value):

        if value is None:
            return
        

        valid_types = {'temp_threshold', 'humid_threshold', 'distance_threshold', 'lux_threshold', 'drowsiness_threshold'}
        if sensor_type in valid_types:
            session = Database()._instance.client.start_session()
            with session:
                Database().update_service_status(uid, sensor_type, value,session )

        else:
            CustomLogger()._get_logger().warning(f"Unknown sensor_type: {sensor_type}")

    async def preprocess_data(self, uid, sensor_type, value):
        """
        Gửi giá trị sensor và threshold tới service tương ứng.
        """
        threshold_fields = [
            'temp_threshold',
            'humid_threshold',
            'distance_threshold',
            'lux_threshold'
        ]
        thresholds = Database().get_services_threshold(uid, is_one=True, fields=threshold_fields)

        
        # Map sensor_type sang key threshold
        threshold_key_map = {
            'temp': 'temp_threshold',
            'humid': 'humid_threshold',
            'dis': 'dis_threshold',
            'lux': 'lux_threshold',
        }
        actions = {
            'temp': lambda v, t: self.device.fan_services(value=float(v), threshold=t, isTemp=1),
            'humid': lambda v, t: self.device.fan_services(value=float(v), threshold=t, isTemp=0),
            'dis': lambda v, t: self.device.alarm_service(self.uid ,value=float(v), threshold=t, isDist=True),
            'lux': lambda v, t: self.device.light_service(value=float(v), threshold=t),
        }
        action = actions.get(sensor_type)
        threshold_key = threshold_key_map.get(sensor_type)
        if action and threshold_key in thresholds:
            threshold = thresholds[threshold_key]
            result = action(value, threshold)
            if asyncio.iscoroutine(result):
                await result


    async def _start_webcam(self,uid):
        # call to database for user preferences
        service_status = Database()._instance.get_services_status_doc_by_id(uid,True)
        wait_time = max(5.0,float(service_status['drowsiness_threshold']))
        if self.videocam:
            thresholds = {
                'ear_threshold': 0.18,
                'wait_time': wait_time,
                'show_window': True
            }
            await self.videocam.start_webcam(thresholds)
            last_alarm_state = False

            while self.videocam.running:
                await asyncio.sleep(0.1)

                if hasattr(self.videocam,'last_frame'):
                    _,play_alarm = self.videocam.last_frame

                    if play_alarm != last_alarm_state:

                        try:
                            # TODO alarm to be update to yolobit
                            if play_alarm is True:
                                await self.device.alarm_service(uid=uid, value=None, threshold=wait_time, isDist=False)
                            CustomLogger()._get_logger().info(f"Alarm status updated: {play_alarm}")

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

                if self._serial_read_task is None or self._serial_read_task.done():
                    self._serial_read_task = asyncio.create_task(self._read_serial(uid))
                # asyncio.create_task(self._send_serial(uid))
                CustomLogger()._get_logger().info("Sensor System started.")
            
            # if self.states['camera']:
            #     asyncio.create_task(self._start_webcam(uid))
            #     CustomLogger()._get_logger().info("Webcam System started.")

        else:
            CustomLogger()._get_logger().warning("System already running.")

    async def _stop_system(self):
        self.running = False
        self.videocam.stop()
            
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
            
        if service_type.startswith("air_cond_service"):
            convert_type = ["humid","temp"], "fan"
        elif service_type.startswith("headlight_service"):
            convert_type = ["lux"], "light"
        elif service_type.startswith("drowsiness_service"):
            convert_type = ["camera"], None
        elif service_type.startswith("distance_service"):
            convert_type = ["dis"], None
        else:
            CustomLogger()._get_logger().warning(f"Unknown service type: {service_type}")
            raise Exception(f"Unknown service type: {service_type}")

        command = None
        if value in ['on','off']:
            # Handle on/off states
            if service_type.startswith('drowsiness'):
                if value == 'on':
                    await self._start_camera(self.uid)
                    
                else:
                    self.videocam.stop()
                    
            command = ""
            for type in convert_type[0]:
                command += f'!{type}:{value}#'
            # command += f'!{convert_type[1]}:{value}#'
            
        elif value is not None:
            # Handle numeric values for thresholds, temperature, etc.
            if service_type.startswith('drowsiness'):
                # print(self.videocam)
                await self.videocam.set_time_threshold(value)

            elif convert_type[1] is not None:
                command = f'!{convert_type[1]}:{value}#'

            else:
                command = f'!{convert_type[0][0]}:{value}#'

        else:
            command = f'!{convert_type[0][0]}:1#'
        
        try :
            if (command is not None):
                self.writer.write(command.encode())
                CustomLogger()._get_logger().info(f"Execute command \"{command}\"")

        except Exception as e:
            CustomLogger()._get_logger().error(f"Failed to execute command: {e}")
            raise Exception(f"Failed to execute command")

    async def main(self):
        await self._start_camera("680fbaef3ae127ba8360f6dd")
        await asyncio.sleep(60)
        await self._stop_camera()
        print("Main function finished.") 
if __name__ == "__main__":
    import time
    CustomLogger()._get_logger().info("IOT System: __main__")
    iotsystem = IOTSystem()._instance
    asyncio.run(iotsystem.main())    
        # iotsystem._start_system("680fbaef3ae127ba8360f6dd")
        # iotsystem._stop_system()


    
