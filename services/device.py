from datetime import datetime
from helpers.custom_logger import CustomLogger

import websockets
import asyncio
import json
# import serial_asyncio

# from services.database import Database

class Device:
    FIELD_DEVICE_ID = "device_id"
    FIELD_SERVICE_TYPE = "service_type"
    FIELD_NOTIFICATION = "notification"
    FIELD_TIMESTAMP = "timestamp"

    def __init__(self, writer, uid, websocket):
        # writer: serial_asyncio.StreamWriter
        self.writer = writer
        self.alarm_last_state = 1
        self.alarm_timer = None
        self.fan_timer = None
        self.light_timer = None
        self.fan_last_state = 1
        self.light_last_state = 1
        self.websocket = websocket
        self.uid = uid

    async def alarm_service(self, value, threshold, isDist=True):
        """Triggers the alarm and starts a timer to turn it off."""
        if(self.alarm_last_state == 1):
            if(isDist):
                if(value < threshold):
                    self.writer.write(f"!alarm:1#".encode())
                    self.alarm_last_state = 0  # Update alarm state
                    asyncio.create_task(self._turn_off_alarm())

                await self._send_notification_to_server("disttance_service",f"Proximity Alert: Object ahead is within {value} cm ahead!")
            else:    
                # Turn on the alarm
                self.writer.write(f"!alarm:1#".encode())

                self.alarm_last_state = 0  # Update alarm state
                
                asyncio.create_task(self._turn_off_alarm())

                await self._send_notification_to_server("drowsiness_service",f"Fatigue Warning: Signs of drowsiness detected!")

    async def _turn_off_alarm(self, delay=5):
        """Turn off the alarm after a delay (default: 5 seconds)."""
        try:
            await asyncio.sleep(delay)
            self.writer.write(f"!alarm:0#".encode())
            CustomLogger()._get_logger().info("Turn off alarm")

            self.alarm_last_state = 1  # Update alarm state

            # Database()._instance.write_action_history(
            #     uid=uid,
            #     service_type='alarm',
            #     value=0,
            #     session=None

            # )
            CustomLogger()._get_logger().info("Alarm turned off automatically.")
        except Exception as e:
            CustomLogger()._get_logger().exception(f"Failed to turn off alarm: {e}")

    async def fan_services(self, value, threshold, isTemp):
        """
        Control the fan based on the value.
        """
        if value > threshold and self.fan_last_state == 1:

            max_speed = 100
            min_speed = 30

            # Tính phần trăm vượt ngưỡng, giới hạn tối đa 100
            percent = min((value - threshold) / threshold, 1.0)
            speed = int(min_speed + percent * (max_speed - min_speed))

            self.writer.write(f"!fan:{speed}#".encode())

            CustomLogger()._get_logger().info(f"Turn on Fan (value={value} > threshold={threshold}, speed={speed})")

            self.fan_last_state = 0  # Update fan state
            CustomLogger()._get_logger().info("Turn on delay FAN")

            asyncio.create_task(self.turn_off_delay("fan"))
            if isTemp:
                await self._send_notification_to_server("air_cond_service", f"Decrease AC's temperature (fan speed {speed})")
            else:
                await self._send_notification_to_server("air_cond_service", f"Decrease AC's humidity (fan speed {speed})")
        else:
            CustomLogger()._get_logger().info(f"Fan not activated (value={value}, threshold={threshold}, fan_last_state={self.fan_last_state})")

    async def light_service(self, value, threshold):
        """
        Control the light based on the value and threshold.
        """
        if value < threshold and self.light_last_state == 1:
            max_light = 4
            min_light = 1

            # Tính phần trăm thiếu sáng, giới hạn tối đa 1.0
            percent = min((threshold - value) / threshold, 1.0)
            light_level = int(min_light + percent * (max_light - min_light))

            self.writer.write(f"!light:{light_level}#".encode())
            print(f"!light:{light_level}#")
            CustomLogger()._get_logger().info(f"Turn on Light (value={value} < threshold={threshold}, level={light_level})")

            self.light_last_state = 0  # Update alarm state
            CustomLogger()._get_logger().info("Turn on delay Light")

            asyncio.create_task(self.turn_off_delay("headlight"))
            await self._send_notification_to_server("headlight_service", f"Turn on headlight (level {light_level})")
        else:
            CustomLogger()._get_logger().info(f"Light not activated (value={value}, threshold={threshold}, light_last_state={self.light_last_state})")
        
    async def turn_off_delay(self, device_type, delay=5):
        """Turn off the specified device after a delay."""
        await  asyncio.sleep(delay)

        if device_type == "fan":
            # await asyncio.sleep(delay)
            CustomLogger()._get_logger().info("Turn off delay Fan")

            self.fan_last_state = 1
        elif device_type == "headlight":
            CustomLogger()._get_logger().info("Turn off delay Light")

            # await asyncio.sleep(delay)
            self.light_last_state = 1
    
    async def _send_notification_to_server(self, service_type: str, notification: str):
        websocket = self.websocket
        if not websocket:
            CustomLogger()._get_logger().warning("Cannot send notification: WebSocket connection not established")
            return
        
        try:
            await websocket.send(json.dumps(
                {
                    self.FIELD_DEVICE_ID: self.uid,
                    self.FIELD_SERVICE_TYPE: service_type,
                    self.FIELD_NOTIFICATION: notification,
                    self.FIELD_TIMESTAMP: datetime.now().isoformat()
                }
            ))
            CustomLogger()._get_logger().info(f"Sent notification to server: {notification}")

        except websockets.exceptions.ConnectionClosed:
            CustomLogger()._get_logger().warning("Cannot send notification: WebSocket connection closed")

        except Exception as e:
            CustomLogger()._get_logger().error(f"Failed to send notification: {e}")



