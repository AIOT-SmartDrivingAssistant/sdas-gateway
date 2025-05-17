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
    FIELD_DESCRIPTION = "description"
    FIELD_TIMESTAMP = "timestamp"

    def __init__(self, writer, uid, websocket):
        # writer: serial_asyncio.StreamWriter
        self.writer = writer

        self.fan_last_state = 1
        self.light_last_state = 1
        self.alarm_last_state_dist = 1
        self.alarm_last_state_drowisness = 1 
        self.websocket = websocket
        self.uid = uid

    async def alarm_service(self, uid, value, threshold, isDist=True):
        """
        Triggers the alarm and starts a timer to turn it off.
        Sends notification if alarm is triggered.
        """
        alarm_triggered = False
        notification_service = ""
        notification_msg = ""

        if isDist:
            if self.alarm_last_state_dist == 1 and value < threshold:
                alarm_triggered = True
                self.alarm_last_state_dist = 0
                notification_service = "distance_service"
                notification_msg = f"Proximity Alert: Object ahead is within {value} cm ahead!"
        else:
            if self.alarm_last_state_drowisness == 1:
                alarm_triggered = True
                self.alarm_last_state_drowisness = 0
                notification_service = "drowsiness_service"
                notification_msg = "Fatigue Warning: Signs of drowsiness detected!"

        if alarm_triggered:
            try:
                self.writer.write(f"!alarm:1#".encode())
                CustomLogger()._get_logger().info("Alarm triggered and turned ON.")
                asyncio.create_task(self._turn_off_alarm())
            except Exception as e:
                CustomLogger()._get_logger().exception(f"Failed to trigger alarm: {e}")

            if notification_service and notification_msg:
                await self._send_notification_to_server(notification_service, notification_msg)

    async def _turn_off_alarm(self, delay=5):
        """
        Turn off the alarm after a delay (default: 5 seconds).
        Resets alarm and light states as needed.
        """
        try:
            await asyncio.sleep(delay)
            self.writer.write(f"!alarm:0#".encode())
            CustomLogger()._get_logger().info("Alarm turned OFF after delay.")

            # Reset states
            if self.alarm_last_state_drowisness == 0:
                self.alarm_last_state_drowisness = 1
            if self.alarm_last_state_dist == 0:
                self.alarm_last_state_dist = 1

            CustomLogger()._get_logger().info("Alarm and related states reset automatically.")
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
            self.fan_last_state = 0

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

            self.light_last_state = 0

            asyncio.create_task(self.turn_off_delay("headlight"))

            await self._send_notification_to_server("headlight_service", f"Turn on headlight (level {light_level})")
        else:
            CustomLogger()._get_logger().info(f"Light not activated (value={value}, threshold={threshold}, light_last_state={self.light_last_state})")
        
    async def turn_off_delay(self, device_type, delay=5):
        """Turn off the specified device after a delay."""
        await  asyncio.sleep(delay)

        if device_type == "fan":
            self.fan_last_state = 1

        elif device_type == "headlight":
            self.light_last_state = 1
    
    async def _send_notification_to_server(self, service_type: str, description: str):
        websocket = self.websocket
        if not websocket:
            CustomLogger()._get_logger().warning("Cannot send notification: WebSocket connection not established")
            return
        
        try:
            await websocket.send(json.dumps(
                {
                    self.FIELD_DEVICE_ID: self.uid,
                    self.FIELD_SERVICE_TYPE: service_type,
                    self.FIELD_DESCRIPTION: description,
                    self.FIELD_TIMESTAMP: datetime.now().isoformat()
                }
            ))
            CustomLogger()._get_logger().info(f"Sent notification to server: {description}")

        except websockets.exceptions.ConnectionClosed:
            CustomLogger()._get_logger().warning("Cannot send notification: WebSocket connection closed")

        except Exception as e:
            CustomLogger()._get_logger().error(f"Failed to send notification: {e}")



